"""Always-on local wake-word detection via Vosk streaming ASR.

Design notes:

- Fully local: raw microphone audio never leaves the machine for wake
  detection. A small Persian Kaldi model runs continuously; an optional
  English model covers "Hey JASEM".
- Partial results are checked too, so activation latency is roughly the
  length of the phrase itself rather than a fixed window.
- A rolling transcript deque feeds the echo guard: JASEM ignores wake
  phrases it has just spoken itself.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from typing import Callable

import numpy as np

from .phrases import PhraseMatcher, WakeMatch

log = logging.getLogger("jasem.wake.vosk")

try:
    import vosk

    vosk.SetLogLevel(-1)
    _VOSK_AVAILABLE = True
except Exception:  # pragma: no cover - vosk import failure is a hard config error
    _VOSK_AVAILABLE = False


class VoskWakeDetector:
    def __init__(
        self,
        fa_model_dir: str,
        en_model_dir: str | None,
        matcher: PhraseMatcher,
        sample_rate: int = 16000,
        energy_threshold: float = 0.012,
    ) -> None:
        if not _VOSK_AVAILABLE:
            raise RuntimeError("vosk package is not available")
        self.matcher = matcher
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.on_match: Callable[[WakeMatch], None] | None = None
        self.on_transcript: Callable[[str, str], None] | None = None  # (text, source)
        self._transcripts: deque[str] = deque(maxlen=12)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._recs: list[tuple[object, str]] = []
        self._lock = threading.Lock()

        log.info("loading vosk wake models (fa=%s en=%s)", fa_model_dir, en_model_dir)
        self._fa_model = vosk.Model(str(fa_model_dir))
        self._en_model = vosk.Model(str(en_model_dir)) if en_model_dir else None

    # -- lifecycle -------------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        # Recognizers are created *synchronously* here, not on the worker
        # thread: feed() can be called the instant start() returns (mic
        # callback / test loop), and frames delivered before the worker
        # publishes its recognizers would be silently dropped — losing the
        # onset of a wake phrase under CPU load.
        with self._lock:
            if not self._recs:
                recs: list[tuple[object, str]] = [
                    (vosk.KaldiRecognizer(self._fa_model, self.sample_rate), "fa")
                ]
                if self._en_model is not None:
                    recs.append((vosk.KaldiRecognizer(self._en_model, self.sample_rate), "en"))
                self._recs = recs
        log.info("wake detector running (%d recognizers)", len(self._recs))
        self._thread = threading.Thread(target=self._run, name="jasem-wake", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    # -- transcript helpers ------------------------------------------------------
    def recent_transcripts(self) -> list[str]:
        return list(self._transcripts)

    # -- audio path --------------------------------------------------------------
    def feed(self, frame: np.ndarray) -> None:
        """Feed one int16 mono frame.

        Below-threshold frames are *zeroed*, not dropped: Kaldi's decoder
        relies on a continuous sample timeline, and skipping frames makes it
        endpoint mid-phrase and lose the hypothesis.
        """
        if self._stop.is_set():
            return
        if float(np.sqrt(np.mean(frame.astype(np.float32) ** 2))) / 32768.0 < self.energy_threshold:
            frame = np.zeros_like(frame)
        data = frame.astype(np.int16, copy=False).tobytes()
        with self._lock:
            recs = list(self._recs)
        for rec, source in recs:
            try:
                if rec.AcceptWaveform(data):
                    text = json.loads(rec.Result()).get("text", "")
                else:
                    text = json.loads(rec.PartialResult()).get("partial", "")
            except Exception:
                continue
            if not text:
                continue
            self._transcripts.append(text)
            if self.on_transcript:
                try:
                    self.on_transcript(text, source)
                except Exception:
                    log.exception("on_transcript failed")
            match = self.matcher.match(text, source=source)
            if match and self.on_match:
                try:
                    self.on_match(match)
                except Exception:
                    log.exception("on_match failed")

    # -- worker thread (keeps the detector alive until stop()) ------------------
    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                self._stop.wait(0.25)
        finally:
            with self._lock:
                self._recs = []
