"""faster-whisper based Persian speech recognition."""

from __future__ import annotations

import logging
import math
import threading
import time

import numpy as np

from ..config import STTConfig
from .base import Transcript

log = logging.getLogger("jasem.stt.whisper")


class FasterWhisperEngine:
    """CTranslate2 Whisper engine tuned for conversational Persian.

    - ``condition_on_previous_text=False`` avoids hallucination loops on
      silence/noise that Whisper is prone to.
    - Whisper's internal Silero VAD is enabled to skip non-speech.
    - Single model instance guarded by a lock (CTranslate2 models are not
      safe for concurrent transcription).
    """

    name = "faster-whisper"

    def __init__(self, cfg: STTConfig) -> None:
        self.cfg = cfg
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            t0 = time.perf_counter()
            log.info("loading whisper model '%s' (%s/%s)", self.cfg.model_size,
                     self.cfg.device, self.cfg.compute_type)
            self._model = WhisperModel(
                self.cfg.model_size,
                device=self.cfg.device,
                compute_type=self.cfg.compute_type,
            )
            log.info("whisper model ready in %.1fs", time.perf_counter() - t0)
        return self._model

    def warmup(self) -> None:
        try:
            with self._lock:
                self._load()
        except Exception:
            log.exception("whisper warmup failed")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> Transcript:
        if audio.size == 0:
            return Transcript("")
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if np.max(np.abs(audio)) > 1.5:  # int16-scaled input
            audio = audio / 32768.0
        if sample_rate != 16000:  # cheap linear resample (callers normally pass 16k)
            n = int(len(audio) * 16000 / sample_rate)
            audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)

        with self._lock:
            model = self._load()
            try:
                segments, info = model.transcribe(
                    audio,
                    language=self.cfg.language,
                    beam_size=self.cfg.beam_size,
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 500},
                    condition_on_previous_text=False,
                )
                texts: list[str] = []
                confidences: list[float] = []
                words: list[tuple[str, float]] = []
                no_speech = 0.0
                for seg in segments:
                    texts.append(seg.text.strip())
                    # avg_logprob sits in [-1, 0]; map to a 0..1 confidence.
                    conf = math.exp(seg.avg_logprob) if seg.avg_logprob is not None else 0.5
                    confidences.append(conf)
                    no_speech = max(no_speech, seg.no_speech_prob or 0.0)
                    if seg.words:
                        for w in seg.words:
                            words.append((w.word.strip(), math.exp(w.probability)))
            except Exception as exc:
                log.error("transcription failed: %s", exc)
                return Transcript("", confidence=0.0, no_speech_prob=1.0)

        text = " ".join(t for t in texts if t)
        conf = float(np.mean(confidences)) if confidences else 0.0
        return Transcript(
            text=text,
            confidence=conf,
            language=info.language if info else self.cfg.language,
            duration_s=len(audio) / 16000,
            no_speech_prob=no_speech,
            words=words,
        )
