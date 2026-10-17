"""Wake-phrase matching."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass

from ..nlp.normalize import wake_normalize


@dataclass
class WakeMatch:
    phrase: str
    transcript: str
    source: str = "fa"
    confidence: float = 1.0


class PhraseMatcher:
    """Matches wake phrases inside (possibly noisy) recognizer output.

    Matching happens on aggressively normalized text so spelling variants
    (جاسم/جاسِم, ZWNJ differences, Latin transliterations) all hit.
    Longer phrases are preferred over the bare «جاسم» to reduce false
    activations from ordinary conversation.
    """

    def __init__(self, phrases: list[str], stop_phrases: list[str] | None = None,
                 cooldown_ms: int = 1500) -> None:
        self.cooldown_s = cooldown_ms / 1000.0
        self._phrases: list[tuple[str, str]] = sorted(
            ((p, wake_normalize(p)) for p in phrases if wake_normalize(p)),
            key=lambda x: -len(x[1]),
        )
        self._stop = [wake_normalize(p) for p in (stop_phrases or []) if wake_normalize(p)]
        self._last_fire = 0.0
        self._lock = threading.Lock()

    def match(self, text: str, source: str = "fa", enforce_cooldown: bool = True) -> WakeMatch | None:
        norm = wake_normalize(text)
        if not norm:
            return None
        hit: tuple[str, str] | None = None
        for original, target in self._phrases:
            if target in norm:
                hit = (original, target)
                break
        if hit is None:
            return None
        # The bare name (a single short token) must stand alone-ish to fire,
        # otherwise any sentence merely mentioning the name would activate.
        if " " not in hit[0].strip() and len(hit[1]) <= 6 and len(norm) > len(hit[1]) + 8:
            return None
        with self._lock:
            now = time.monotonic()
            if enforce_cooldown and now - self._last_fire < self.cooldown_s:
                return None
            self._last_fire = now
        return WakeMatch(phrase=hit[0], transcript=text, source=source)

    def is_stop(self, text: str) -> bool:
        norm = wake_normalize(text)
        return bool(norm) and any(p in norm for p in self._stop)

    def reset_cooldown(self) -> None:
        with self._lock:
            self._last_fire = 0.0
