"""Application orchestrator.

Wires microphone -> wake word / VAD -> STT -> intent+LLM -> TTS -> playback,
drives the state machine, and exposes plain-Python callbacks that the UI
bridge re-emits as Qt signals. All heavy work happens on worker threads; the
capture callback itself only fans frames out.
"""

from __future__ import annotations

import logging
import queue
import re
import threading
import time
from collections import deque
from typing import Any, Callable

import numpy as np

from .ai.base import extract_actions
from .ai.conversation import Conversation
from .ai.local_provider import LocalProvider
from .ai.openai_provider import OpenAIProvider, ProviderError
from .ai.prompts import build_system_prompt
from .audio.capture import MicStream
from .audio.playback import AudioPlayer, chime
from .audio.vad import Vad
from .automation import actions as automation_actions
from .automation.apps import AppIndex
from .automation.policy import Category, Policy
from .config import AppConfig, resolve_wake_model_dirs
from .nlp.intents import Intent, match_confirmation, match_intent
from .nlp.normalize import normalize_text, wake_normalize
from .state_machine import State, StateMachine
from .stt.correction import Corrector
from .stt.faster_whisper_engine import FasterWhisperEngine
from .stt.pipeline import UtteranceCollector
from .tts.edge_engine import EdgeTTSEngine, EdgeTTSError
from .tts.piper_engine import PiperTTSEngine
from .tts.speech_text import prepare_chunks
from .wake.phrases import PhraseMatcher, WakeMatch
from .wake.vosk_detector import VoskWakeDetector

log = logging.getLogger("jasem.orchestrator")

_SENTENCE_END = re.compile(r"[.!؟?;؛]\s")


def _pop_sentence(buffer: str, max_chars: int) -> tuple[str | None, str]:
    """Streaming splitter: returns (complete_sentence_or_None, remainder).

    A sentence is complete at real punctuation; very long buffers are force-split
    so the speech pipeline never waits on a runaway sentence.
    """
    if not buffer:
        return None, buffer
    m = _SENTENCE_END.search(buffer)
    if m and m.end() >= 3:
        cut = m.end()
        return buffer[:cut].strip(), buffer[cut:]
    if len(buffer) >= max_chars:
        cut = buffer.rfind("،", 0, max_chars)
        if cut < max_chars // 3:
            cut = buffer.rfind(" ", 0, max_chars)
        if cut <= 0:
            cut = max_chars
        return buffer[:cut].strip(), buffer[cut:]
    return None, buffer


class AssistantCore:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.sm = StateMachine(on_transition=self._handle_transition)
        self.conversation = Conversation(cfg.conversation)
        self.conversation.set_memory_enabled(cfg.ai.memory_enabled)
        self.policy = Policy(cfg.automation)
        self.app_index = AppIndex()
        self.system_prompt = build_system_prompt(cfg.personality)

        # -- audio ------------------------------------------------------------
        self.player = AudioPlayer(device=cfg.audio.output_device)
        self.player.on_play_start = self._on_play_start
        self.player.on_play_stop = self._on_play_stop
        self.player.on_level = self._emit_play_level
        self.mic = MicStream(cfg.audio.sample_rate, cfg.audio.frame_ms, cfg.audio.input_device)
        self.mic.on_device_error = self._on_mic_error
        self.mic.on_device_restored = self._on_mic_restored
        self.vad = Vad(cfg.audio.vad_aggressiveness, cfg.audio.sample_rate, cfg.audio.frame_ms)
        self.collector = UtteranceCollector(
            self.vad,
            on_utterance=self._enqueue_utterance,
            on_speech_start=lambda: self.callbacks.get("speech_start") and self.callbacks["speech_start"](),
            on_speech_end=lambda: self.callbacks.get("speech_end") and self.callbacks["speech_end"](),
            sample_rate=cfg.audio.sample_rate,
            speech_min_ms=cfg.audio.speech_min_ms,
            silence_end_ms=cfg.audio.silence_end_ms,
            max_utterance_s=cfg.audio.max_utterance_s,
        )

        # -- wake word ----------------------------------------------------------
        self.wake_matcher = PhraseMatcher(
            cfg.wake.phrases, cfg.wake.stop_phrases, cfg.wake.match_cooldown_ms
        )
        fa_dir, en_dir = resolve_wake_model_dirs(cfg)
        self.wake: VoskWakeDetector | None = None
        try:
            self.wake = VoskWakeDetector(str(fa_dir), str(en_dir) if en_dir else None,
                                         self.wake_matcher, cfg.audio.sample_rate)
            self.wake.on_match = self._on_wake_match
            self.wake.on_transcript = self._on_wake_transcript
        except Exception:
            log.exception("wake detector unavailable (model missing?)")
            self._status("wake", False, "مدل تشخیص صدا موجود نیست")

        # -- engines -----------------------------------------------------------
        self.stt = FasterWhisperEngine(cfg.stt)
        self.corrector = Corrector(cfg.stt.vocabulary, cfg.stt.correction_enabled)
        self.tts = self._build_tts(cfg.tts.engine)
        self.piper_fallback: PiperTTSEngine | None = None
        self.provider = (OpenAIProvider(cfg.ai) if cfg.ai.provider == "openai-compatible"
                         else LocalProvider(cfg.personality))
        if cfg.ai.provider == "openai-compatible" and not self.provider.available:
            log.info("no API key found — falling back to local offline provider")
            self.provider = LocalProvider(cfg.personality)

        automation_actions.REMINDER_NOTIFY = self._notify

        # -- worker machinery ---------------------------------------------------
        self._utter_q: queue.Queue = queue.Queue()
        self._speak_q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._workers: list[threading.Thread] = []
        self._session_deadline = 0.0
        self._pending_action: dict | None = None
        self._last_reply = ""
        self._spoken_recent: deque[str] = deque(maxlen=24)
        self._level = 0.0
        self._level_lock = threading.Lock()
        self._speak_generation = -1
        self.mic_muted = threading.Event()
        if cfg.system.mic_muted_on_start:
            self.mic_muted.set()

        # -- callbacks (installed by the UI bridge) --------------------------------
        self.callbacks: dict[str, Callable[..., Any]] = {}

    # ========================= lifecycle =========================
    def _build_tts(self, engine_name: str):
        try:
            engine = (EdgeTTSEngine(self.cfg.tts) if engine_name == "edge"
                      else PiperTTSEngine(self.cfg.tts))
            return engine
        except Exception:
            log.exception("TTS engine '%s' failed to build; using piper", engine_name)
            return PiperTTSEngine(self.cfg.tts)

    def start(self) -> None:
        self.app_index.refresh_async()
        self._status("ai", self.provider.available,
                     "متصل" if self.provider.available else "حالت آفلاین (بدون کلید API)")
        self._status("tts", True, f"{self.tts.name} · {'آنلاین' if self.tts.online else 'آفلاین'}")
        for i in range(2):
            t = threading.Thread(target=self._worker, name=f"jasem-worker-{i}", daemon=True)
            t.start()
            self._workers.append(t)
        t = threading.Thread(target=self._speak_worker, name="jasem-speak", daemon=True)
        t.start()
        self._workers.append(t)
        t = threading.Thread(target=self._session_watch, name="jasem-session", daemon=True)
        t.start()
        self._workers.append(t)

        mic_ok = self.mic.start()
        self._status("mic", mic_ok, "متصل" if mic_ok else "میکروفن در دسترس نیست")
        self.mic.subscribe(self._on_frame)
        self.mic.set_level_callback(self._emit_mic_level)
        if self.wake and self.cfg.wake.enabled and not self.mic_muted.is_set():
            self.wake.start()
            self.sm.transition(State.WAKE_MONITORING, "started")
        else:
            self.sm.transition(State.IDLE, "started (wake disabled)")
        self._warm_engines()

    def _warm_engines(self) -> None:
        def warm() -> None:
            try:
                self.stt.warmup()
                self._status("stt", True, f"مدل {self.cfg.stt.model_size} آماده است")
            except Exception as exc:
                self._status("stt", False, str(exc))
            try:
                self.tts.warmup()
            except Exception as exc:
                log.warning("tts warmup failed: %s", exc)

        threading.Thread(target=warm, name="jasem-warmup", daemon=True).start()

    def shutdown(self) -> None:
        self._stop.set()
        self.sm.transition(State.SHUTDOWN, "shutdown")
        self.mic.stop()
        if self.wake:
            self.wake.stop()
        self.collector.set_armed(False)
        self.player.close()
        for _ in self._workers:
            self._speak_q.put_nowait(("stop",))
            self._utter_q.put_nowait(None)
        for t in self._workers:
            t.join(timeout=2.0)
        try:
            self.tts.close()
        except Exception:
            pass

    # ========================= user controls =========================
    def toggle_mute(self) -> bool:
        muted = not self.mic_muted.is_set()
        if muted:
            self.mic_muted.set()
            self.collector.set_armed(False)
            if self.wake:
                self.wake.stop()
            self._status("mic", False, "بی‌صدا — جاسم گوش نمی‌ده")
        else:
            self.mic_muted.clear()
            if self.wake and self.cfg.wake.enabled:
                self.wake.start()
            self._status("mic", True, "متصل")
            if self.sm.state in (State.IDLE, State.INTERRUPTED):
                self.sm.transition(State.WAKE_MONITORING, "unmuted")
        return muted

    def push_to_talk(self) -> None:
        """Start (or end) a manual listening session without the wake word."""
        if self.mic_muted.is_set():
            self.toggle_mute()
        if self.sm.state in (State.LISTENING, State.CONFIRMING):
            self._finish_listening()
            return
        self._enter_listening(manual=True)

    def submit_text(self, text: str) -> None:
        """Manual text input fallback — bypasses speech recognition."""
        text = (text or "").strip()
        if not text:
            return
        if self.sm.state in (State.WAKE_MONITORING, State.IDLE, State.INTERRUPTED):
            self.sm.transition(State.LISTENING, "text input")
            self._session_deadline = time.monotonic() + self.cfg.conversation.session_timeout_s
        self.conversation.add("user", text)
        self._emit_message("user", text)
        self._answer(text, match_intent(text), uncertain=False)

    def stop_speaking(self) -> None:
        self._interrupt_speech("manual stop")

    def repeat_last(self) -> None:
        last = self.conversation.last_assistant_text()
        if last:
            self._queue_speech(last)

    def clear_history(self) -> None:
        self.conversation.clear()
        self._emit_message("system", "تاریخچهٔ گفتگو پاک شد.")

    def confirm_pending(self, approved: bool) -> None:
        pending, self._pending_action = self._pending_action, None
        if pending is None:
            return
        if not approved:
            self._queue_speech("باشه، منصرف شدم. کار دیگه‌ای داشتی بگو.")
            self._resume_after_speech()
            return
        result = automation_actions.execute_action(pending["name"], pending.get("args", {}))
        automation_actions.audit(pending, result)
        self._emit_message("system", ("✅ " if result.ok else "❌ ") + result.message)
        self._queue_speech(result.message)
        self._resume_after_speech()

    def emergency_stop(self) -> None:
        self._pending_action = None
        self._drain(self._speak_q)
        self._drain(self._utter_q)
        self.collector.set_armed(False)
        self.player.interrupt()
        self._notify("همهٔ عملیات‌های در حال اجرا متوقف شد.")
        self.sm.transition(State.WAKE_MONITORING, "emergency stop")

    def set_wake_enabled(self, enabled: bool) -> None:
        self.cfg.wake.enabled = enabled
        if enabled and not self.mic_muted.is_set() and self.wake:
            self.wake.start()
            if self.sm.state == State.IDLE:
                self.sm.transition(State.WAKE_MONITORING, "wake enabled")
        elif not enabled and self.wake:
            self.wake.stop()
            if self.sm.state == State.WAKE_MONITORING:
                self.sm.transition(State.IDLE, "wake disabled")

    def set_tts_engine(self, engine_name: str) -> None:
        self.cfg.tts.engine = engine_name
        old = self.tts
        self.tts = self._build_tts(engine_name)
        threading.Thread(target=self.tts.warmup, daemon=True).start()
        try:
            old.close()
        except Exception:
            pass
        self._status("tts", True, f"{self.tts.name} · {'آنلاین' if self.tts.online else 'آفلاین'}")

    # ========================= audio path =========================
    def _on_frame(self, frame: np.ndarray) -> None:
        if self.mic_muted.is_set():
            return
        state = self.sm.state
        wake_active = (
            self.wake is not None
            and state in (State.WAKE_MONITORING, State.LISTENING, State.PROCESSING,
                          State.GENERATING, State.SPEAKING, State.CONFIRMING, State.INTERRUPTED)
            and (self.cfg.wake.barge_in or state != State.SPEAKING)
        )
        if wake_active:
            self.wake.feed(frame)
        if self.collector.armed:
            self.collector.feed(frame)

    def _emit_mic_level(self, level: float) -> None:
        with self._level_lock:
            self._level = level
        cb = self.callbacks.get("mic_level")
        if cb:
            cb(level)

    def _emit_play_level(self, level: float) -> None:
        cb = self.callbacks.get("play_level")
        if cb:
            cb(level)

    # ========================= wake word =========================
    def _on_wake_match(self, match: WakeMatch) -> None:
        if self._echoed(match):
            return
        state = self.sm.state
        log.info("wake match '%s' while %s", match.phrase, state.value)
        cb = self.callbacks.get("wake")
        if cb:
            cb(match.phrase)
        if state == State.SPEAKING:
            self._interrupt_speech("wake barge-in")
            self._enter_listening(ack=False)
        elif state in (State.LISTENING, State.CONFIRMING):
            self._session_deadline = time.monotonic() + self.cfg.conversation.session_timeout_s
        elif state in (State.WAKE_MONITORING, State.IDLE, State.INTERRUPTED):
            self._enter_listening(ack=True)

    def _on_wake_transcript(self, text: str, source: str) -> None:
        if self.sm.state != State.SPEAKING:
            return
        if self.wake_matcher.is_stop(text) and not self._echoed_text(text):
            self._interrupt_speech("stop phrase")

    def _echoed(self, match: WakeMatch) -> bool:
        """True when the 'wake phrase' is almost certainly JASEM's own voice."""
        norm = wake_normalize(match.transcript)
        if not norm:
            return False
        for spoken in self._spoken_recent:
            s = wake_normalize(spoken)
            if norm and norm in s:
                return True
        return False

    def _echoed_text(self, text: str) -> bool:
        norm = wake_normalize(text)
        return any(norm and norm in wake_normalize(s) for s in self._spoken_recent)

    # ========================= listening / utterances =========================
    def _enter_listening(self, ack: bool = True, manual: bool = False) -> None:
        self._pending_action = None
        self._session_deadline = time.monotonic() + self.cfg.conversation.session_timeout_s
        self.collector.set_armed(True)
        self.sm.transition(State.LISTENING, "wake" if not manual else "manual")
        if ack:
            mode = self.cfg.tts.ack_voice
            if mode == "chime":
                self._play_chime()
            elif mode == "short":
                self._speak_q.put(("audio", [chime(1046.5)], 24000, self.player.generation))

    def _finish_listening(self) -> None:
        self.collector.set_armed(False)
        if self.sm.state == State.LISTENING:
            self.sm.transition(State.WAKE_MONITORING, "conversation closed")

    def _session_watch(self) -> None:
        while not self._stop.is_set():
            time.sleep(0.4)
            if self.sm.state in (State.LISTENING, State.CONFIRMING) and \
                    0 < self._session_deadline < time.monotonic():
                log.info("conversation session timed out")
                self.collector.set_armed(False)
                self._pending_action = None
                if self.sm.state != State.WAKE_MONITORING:
                    self.sm.transition(State.WAKE_MONITORING, "session timeout")

    def _enqueue_utterance(self, audio: np.ndarray, meta: dict) -> None:
        self._utter_q.put((audio, meta))

    def _worker(self) -> None:
        while not self._stop.is_set():
            item = self._utter_q.get()
            if item is None:
                break
            audio, meta = item
            try:
                self._process_utterance(audio, meta)
            except Exception:
                log.exception("utterance processing failed")
                self._queue_speech("یه اشکال فنی پیش اومد؛ دوباره امتحان کن.")

    def _process_utterance(self, audio: np.ndarray, meta: dict) -> None:
        self.sm.transition(State.PROCESSING, "utterance")
        transcript = self.stt.transcribe(audio, self.cfg.audio.sample_rate)
        text, changes = self.corrector.correct(transcript.text)
        if changes:
            log.info("correction applied: %s", changes)
        if not text.strip():
            log.info("empty transcription (conf=%.2f)", transcript.confidence)
            self.sm.transition(State.LISTENING, "empty transcript")
            return
        self._emit_message("user", text)
        self.conversation.add("user", text)

        # 1) pending confirmation flow
        if self._pending_action is not None:
            answer = match_confirmation(text)
            if answer is not None:
                self.confirm_pending(answer)
            else:
                self._say_unclear()
            return

        # 2) stop / control commands
        intent = match_intent(text)
        if intent and intent.name == "stop_speaking":
            self._interrupt_speech("voice stop")
            self._resume_after_speech()
            return
        if intent and intent.name == "emergency_stop":
            self.emergency_stop()
            return
        if intent and intent.name == "repeat":
            self.repeat_last()
            return

        uncertain = transcript.confidence < self.cfg.stt.low_confidence_threshold
        if uncertain:
            self._emit_message("system", "⚠️ متن با اطمینان کم تشخیص داده شد؛ لطفاً تأیید کن.")

        self._answer(text, intent, uncertain)

    def _say_unclear(self) -> None:
        self._queue_speech("متوجه نشدم؛ ببخشید دوباره بگو.")

    # ========================= answering =========================
    def _queue_speech(self, text: str) -> None:
        """Queue assistant speech tagged with the current playback generation,
        so interrupt() invalidates everything already queued."""
        self._speak_q.put(("text", text, self.player.generation))

    def _answer(self, text: str, intent: Intent | None, uncertain: bool) -> None:
        self.sm.transition(State.GENERATING, "answer")
        use_llm = getattr(self.provider, "name", "") != "local"
        if use_llm:
            self._answer_llm(text)
        elif intent:
            self._run_intent(intent)
        else:
            reply = self.provider.chat(self.conversation.messages_for_prompt(self.system_prompt))
            self._finish_answer(reply)

    def _answer_llm(self, text: str) -> None:
        messages = self.conversation.messages_for_prompt(self.system_prompt)
        buffer = ""
        reply_parts: list[str] = []

        def stream():
            """Speak each sentence as soon as it is complete."""
            nonlocal buffer
            for delta in self.provider.chat_stream(messages):
                buffer += delta
                reply_parts.append(delta)
                while True:
                    sentence, buffer = _pop_sentence(buffer, self.cfg.tts.sentence_max_chars)
                    if sentence is None:
                        break
                    if sentence.strip():
                        self._queue_speech(sentence.strip())

        def finish():
            if buffer.strip():
                self._queue_speech(buffer.strip())
            full = "".join(reply_parts)
            result = extract_actions(full)
            if result.actions:
                self._handle_actions(result.actions)
            self._finish_answer(result.text, speak=False)

        try:
            stream()
            finish()
        except ProviderError as exc:
            log.error("LLM provider error: %s", exc)
            self._status("ai", False, "ارتباط با مدل زبانی برقرار نشد")
            fallback = LocalProvider(self.cfg.personality).chat(messages)
            self._finish_answer(fallback + " (الان سرویس هوش مصنوعی در دسترس نیست.)")
        except Exception:
            log.exception("LLM streaming failed")
            self._finish_answer("یه خطای غیرمنتظره پیش اومد هنگام ساختن جواب.")

    def _run_intent(self, intent: Intent) -> None:
        action = {"name": intent.name, "args": intent.args}
        valid, name, err = automation_actions.validate_action(action)
        if not valid:
            self._finish_answer(f"این درخواست قابل اجرا نیست: {err}")
            return
        decision = self.policy.evaluate(name)
        if not decision.allowed:
            self._finish_answer("اجرا مجاز نیست؛ توی تنظیمات غیرفعال شده.")
            return
        if decision.needs_confirmation:
            self._pending_action = action
            self.sm.transition(State.CONFIRMING, name)
            self._emit_confirmation(f"«{name}» انجام بشه؟ {decision.reason}")
            return
        result = automation_actions.execute_action(name, intent.args)
        automation_actions.audit(action, result)
        self._emit_message("system", ("✅ " if result.ok else "❌ ") + result.message)
        self._finish_answer(result.message)

    def _handle_actions(self, actions: list[dict]) -> None:
        for action in actions:
            valid, name, err = automation_actions.validate_action(action)
            if not valid:
                self._emit_message("system", f"⚠️ عملیات نامعتبر از مدل: {err}")
                continue
            decision = self.policy.evaluate(name)
            if not decision.allowed:
                self._emit_message("system", f"⛔ عملیات «{name}» مجاز نیست.")
                continue
            if decision.needs_confirmation:
                self._pending_action = action
                self.sm.transition(State.CONFIRMING, name)
                self._emit_confirmation(f"«{name}» انجام بشه؟ {decision.reason}")
                return
            result = automation_actions.execute_action(name, action.get("args", {}))
            automation_actions.audit(action, result)
            self._emit_message("system", ("✅ " if result.ok else "❌ ") + result.message)
            self._queue_speech(result.message)

    def _finish_answer(self, reply: str, speak: bool = True) -> None:
        reply = reply.strip()
        if reply:
            self._last_reply = reply
            self.conversation.add("assistant", reply)
            self._emit_message("assistant", reply)
            if speak:
                self._queue_speech(reply)
        if self._pending_action is None:
            self._resume_after_speech()

    def _resume_after_speech(self) -> None:
        deadline = time.monotonic() + self.cfg.conversation.session_timeout_s
        self._session_deadline = deadline
        if self.sm.state not in (State.LISTENING, State.CONFIRMING, State.WAKE_MONITORING):
            self.sm.transition(State.LISTENING, "keep conversation open")
        self.collector.set_armed(True)

    # ========================= speech pipeline =========================
    def _play_chime(self) -> None:
        self._speak_q.put(("audio", [chime(880.0)], 24000, self.player.generation))

    def _speak_worker(self) -> None:
        while not self._stop.is_set():
            item = self._speak_q.get()
            if item is None or item[0] == "stop":
                break
            kind = item[0]
            try:
                if kind == "audio":
                    _, chunks, rate, gen = item
                    if gen == self.player.generation:
                        self.player.submit(iter(chunks), rate, generation=gen)
                elif kind == "text":
                    _, text, gen = item
                    if gen == self.player.generation:
                        self._speak_text(text, gen)
            except Exception:
                log.exception("speech pipeline failed")
        # drain on shutdown
        self._drain(self._speak_q)

    def _speak_text(self, text: str, gen: int) -> None:
        chunks = prepare_chunks(text, self.cfg.tts.sentence_max_chars, self.cfg.tts.convert_numbers)
        for sentence in chunks:
            if gen != self.player.generation:
                return  # interrupted while synthesizing
            self._spoken_recent.append(sentence)
            audio_iter = self._synthesize_with_fallback(sentence)
            if audio_iter is None:
                continue
            self.player.submit(audio_iter, self.tts.sample_rate, generation=gen)

    def _synthesize_with_fallback(self, sentence: str):
        """Returns an iterator of float32 chunks, or None on failure."""
        try:
            return iter(list(self.tts.synthesize(sentence)))
        except Exception as exc:
            log.warning("primary TTS failed (%s); trying piper fallback", exc)
            self._status("tts", False, "سرویس صدا موقتاً در دسترس نیست؛ حالت آفلاین")
            try:
                if self.piper_fallback is None:
                    self.piper_fallback = PiperTTSEngine(self.cfg.tts)
                    self.piper_fallback.warmup()
                chunks = list(self.piper_fallback.synthesize(sentence))
                self._status("tts", True, "piper · آفلاین")
                return iter(chunks)
            except Exception:
                log.exception("fallback TTS failed too")
                return None

    def _interrupt_speech(self, reason: str) -> None:
        self.player.interrupt()
        self._drain(self._speak_q)
        self.collector.set_armed(False)
        if self.sm.state == State.SPEAKING:
            self.sm.transition(State.INTERRUPTED, reason)

    def _on_play_start(self) -> None:
        self.sm.transition(State.SPEAKING, "playback")

    def _on_play_stop(self, interrupted: bool) -> None:
        if interrupted:
            return
        state = self.sm.state
        if state == State.SPEAKING:
            if self.collector.armed:
                self.sm.transition(State.LISTENING, "back to conversation")
            else:
                self.sm.transition(State.WAKE_MONITORING, "idle after speech")

    def _drain(self, q: queue.Queue) -> None:
        try:
            while True:
                q.get_nowait()
        except queue.Empty:
            pass

    # ========================= misc helpers =========================
    def _handle_transition(self, tr) -> None:
        cb = self.callbacks.get("state")
        if cb:
            cb(tr.new.value, tr.old.value, tr.reason)

    def _emit_message(self, role: str, text: str) -> None:
        cb = self.callbacks.get("message")
        if cb:
            cb(role, text, time.time())

    def _emit_confirmation(self, text: str) -> None:
        cb = self.callbacks.get("confirmation")
        if cb:
            cb(text)

    def _notify(self, text: str) -> None:
        cb = self.callbacks.get("notification")
        if cb:
            cb(text)
        self._emit_message("system", text)

    def _status(self, service: str, ok: bool, detail: str = "") -> None:
        cb = self.callbacks.get("status")
        if cb:
            cb(service, ok, detail)

    def _on_mic_error(self, message: str) -> None:
        self._status("mic", False, f"میکروفن قطع شد: {message}")
        self._notify("میکروفن در دسترس نیست. وصلش کن تا دوباره شروع کنم.")

    def _on_mic_restored(self) -> None:
        self._status("mic", True, "دوباره وصل شد")
        self._notify("میکروفن دوباره وصل شد؛ ادامه می‌دم.")

    # -- introspection for UI ----------------------------------------------------
    @property
    def mic_level(self) -> float:
        with self._level_lock:
            return self._level

    def snapshot(self) -> dict:
        return {
            "state": self.sm.state.value,
            "muted": self.mic_muted.is_set(),
            "provider": self.provider.name,
            "ai_available": self.provider.available,
            "tts": self.tts.name,
            "tts_online": self.tts.online,
            "stt": self.stt.name,
            "wake_enabled": self.cfg.wake.enabled,
        }
