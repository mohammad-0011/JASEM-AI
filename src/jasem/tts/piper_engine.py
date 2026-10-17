"""Piper offline Persian TTS engine (ONNX, CPU).

Voices live in ``models/piper/fa_IR-<voice>-medium.onnx`` (+ .json). Piper
phonemizes Persian with the bundled espeak-ng data, so no system-level espeak
install is required.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Iterator

import numpy as np

from .. import paths
from ..config import TTSConfig

log = logging.getLogger("jasem.tts.piper")


class PiperTTSError(RuntimeError):
    pass


class PiperTTSEngine:
    name = "piper"
    online = False

    def __init__(self, cfg: TTSConfig, *, noise_scale: float | None = None,
                 noise_w_scale: float | None = None) -> None:
        self.cfg = cfg
        self.sample_rate = 22050
        self._voice = None
        self._lock = threading.Lock()
        # The VITS noise is drawn from an ONNX random op whose seed is not
        # controllable from outside, so each process gets one arbitrary noise
        # realization. Tests pass 0 here: with zero noise the model output is
        # fully deterministic (still intelligible), which keeps audio-based
        # assertions reproducible. Production keeps the voice's natural noise.
        self._noise_scale = noise_scale
        self._noise_w_scale = noise_w_scale
        self._model_path = paths.PIPER_MODELS_DIR / f"fa_IR-{cfg.piper_voice}-medium.onnx"
        self._config_path = paths.PIPER_MODELS_DIR / f"fa_IR-{cfg.piper_voice}-medium.onnx.json"

    def _load(self):
        if self._voice is None:
            if not self._model_path.exists():
                raise PiperTTSError(
                    f"Persian piper voice not found: {self._model_path}. "
                    "Download fa_IR voices into models/piper (see README)."
                )
            from piper import SynthesisConfig
            from piper.voice import PiperVoice

            t0 = time.perf_counter()
            self._voice = PiperVoice.load(str(self._model_path), str(self._config_path))
            self.sample_rate = self._voice.config.sample_rate
            self._synth_config = SynthesisConfig(
                length_scale=self.cfg.piper_length_scale,
                noise_scale=self._noise_scale,
                noise_w_scale=self._noise_w_scale,
            )
            log.info("piper voice '%s' ready in %.2fs", self.cfg.piper_voice, time.perf_counter() - t0)
        return self._voice

    def warmup(self) -> None:
        try:
            with self._lock:
                self._load()
        except PiperTTSError:
            raise
        except Exception:
            log.exception("piper warmup failed")

    def synthesize(self, text: str) -> Iterator[np.ndarray]:
        text = (text or "").strip()
        if not text:
            return
        with self._lock:
            voice = self._load()
            try:
                chunks = list(voice.synthesize(text, self._synth_config))
            except Exception as exc:
                raise PiperTTSError(str(exc)) from exc
        for chunk in chunks:
            arr = chunk.audio_float_array
            yield np.asarray(arr, dtype=np.float32)

    def close(self) -> None:
        self._voice = None
