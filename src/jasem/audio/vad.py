"""WebRTC voice activity detection wrapper."""

from __future__ import annotations

import numpy as np
import webrtcvad


class Vad:
    """Binary speech/non-speech classifier over fixed-size PCM16 frames."""

    def __init__(self, aggressiveness: int = 2, sample_rate: int = 16000,
                 frame_ms: int = 30) -> None:
        if frame_ms not in (10, 20, 30):
            raise ValueError("webrtcvad supports frame_ms in {10, 20, 30}")
        self._vad = webrtcvad.Vad(int(aggressiveness))
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms

    def is_speech(self, frame: np.ndarray | bytes) -> bool:
        if isinstance(frame, np.ndarray):
            frame = frame.astype(np.int16, copy=False).tobytes()
        try:
            return bool(self._vad.is_speech(frame, self.sample_rate))
        except Exception:
            return False
