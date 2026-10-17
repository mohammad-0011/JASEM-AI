"""Voice-activity-gated utterance segmentation.

Turns a raw frame stream into complete utterances:

- speech must persist ``speech_min_ms`` before an utterance starts (noise
  rejection),
- an utterance only ends after ``silence_end_ms`` of continuous silence, so
  natural mid-sentence pauses do not truncate the user,
- hard cap at ``max_utterance_s`` for runaway audio,
- ``set_armed(False)`` immediately stops collection (echo gate while JASEM
  speaks, mute button, wake-monitoring mode).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import numpy as np

from ..audio.vad import Vad

log = logging.getLogger("jasem.stt.pipeline")


class UtteranceCollector:
    def __init__(
        self,
        vad: Vad,
        on_utterance: Callable[[np.ndarray, dict], None],
        on_speech_start: Callable[[], None] | None = None,
        on_speech_end: Callable[[], None] | None = None,
        sample_rate: int = 16000,
        speech_min_ms: int = 250,
        silence_end_ms: int = 750,
        max_utterance_s: float = 30.0,
    ) -> None:
        self.vad = vad
        self.sample_rate = sample_rate
        self.speech_min_frames = max(1, speech_min_ms // vad.frame_ms)
        self.silence_end_frames = max(1, silence_end_ms // vad.frame_ms)
        self.max_frames = int(max_utterance_s * 1000 / vad.frame_ms)
        self.on_utterance = on_utterance
        self.on_speech_start = on_speech_start
        self.on_speech_end = on_speech_end

        self._lock = threading.Lock()
        self._armed = False
        self._in_speech = False
        self._speech_frames = 0
        self._silence_frames = 0
        self._buffer: list[np.ndarray] = []
        self._started_at = 0.0

    # -- control -------------------------------------------------------------
    def set_armed(self, armed: bool) -> None:
        with self._lock:
            self._armed = armed
            if not armed:
                self._reset_locked()

    @property
    def armed(self) -> bool:
        with self._lock:
            return self._armed

    @property
    def in_speech(self) -> bool:
        with self._lock:
            return self._in_speech

    def reset(self) -> None:
        with self._lock:
            self._reset_locked()

    def _reset_locked(self) -> None:
        self._in_speech = False
        self._speech_frames = 0
        self._silence_frames = 0
        self._buffer.clear()

    # -- audio path ----------------------------------------------------------
    def feed(self, frame: np.ndarray) -> None:
        fire_start = False
        audio: np.ndarray | None = None
        meta: dict = {}
        with self._lock:
            if not self._armed:
                return
            is_speech = self.vad.is_speech(frame)

            if not self._in_speech:
                if is_speech:
                    self._speech_frames += 1
                    self._buffer.append(frame)
                    if self._speech_frames >= self.speech_min_frames:
                        self._in_speech = True
                        self._silence_frames = 0
                        self._started_at = time.monotonic()
                        fire_start = True
                    else:
                        return
                else:
                    self._speech_frames = 0
                    # keep only the tail of the pre-roll so the actual speech
                    # onset frames are not dropped
                    if len(self._buffer) > 3:
                        self._buffer = self._buffer[-3:]
                    return
            else:
                self._buffer.append(frame)
                self._silence_frames = 0 if is_speech else self._silence_frames + 1

            total = len(self._buffer)
            forced = total >= self.max_frames
            if self._silence_frames < self.silence_end_frames and not forced:
                return
            # Drop most trailing silence but keep a small tail for prosody.
            keep = total - max(0, self._silence_frames - 3)
            speech_frames = total - self._silence_frames
            audio = np.concatenate(self._buffer[:keep]).astype(np.float32)
            meta = {
                "duration_s": keep / self.sample_rate * (self.sample_rate / self.sample_rate),
                "forced": forced,
                "speech_ratio": speech_frames / max(1, total),
                "started_at": self._started_at,
            }
            self._reset_locked()

        if fire_start and self.on_speech_start:
            try:
                self.on_speech_start()
            except Exception:
                log.exception("on_speech_start failed")
        if audio is not None:
            meta["duration_s"] = len(audio) / self.sample_rate
            if self.on_speech_end:
                try:
                    self.on_speech_end()
                except Exception:
                    log.exception("on_speech_end failed")
            try:
                self.on_utterance(audio, meta)
            except Exception:
                log.exception("utterance handler failed")
