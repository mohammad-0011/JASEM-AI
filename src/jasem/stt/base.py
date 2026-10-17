"""Speech-to-text engine interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass
class Transcript:
    text: str
    confidence: float = 0.0          # 0..1, best effort
    language: str = "fa"
    duration_s: float = 0.0
    no_speech_prob: float = 0.0
    words: list[tuple[str, float]] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.text.strip()


@runtime_checkable
class STTEngine(Protocol):
    name: str

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> Transcript:
        """Transcribe mono float32/int16 audio. Must never raise for empty audio."""
        ...

    def warmup(self) -> None:
        """Load models ahead of the first real request."""
        ...
