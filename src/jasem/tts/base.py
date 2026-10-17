"""Text-to-speech engine interface."""

from __future__ import annotations

from typing import Iterator, Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class TTSEngine(Protocol):
    name: str
    online: bool
    sample_rate: int

    def synthesize(self, text: str) -> Iterator[np.ndarray]:
        """Yield float32 mono PCM chunks for one sentence/chunk of text."""
        ...

    def warmup(self) -> None:
        ...

    def close(self) -> None:
        ...
