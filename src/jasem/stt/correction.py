"""Confidence-aware contextual correction.

The rule set is deliberately conservative: it only replaces a *close* variant
of a known term with its canonical spelling. It never invents words and never
restructures the sentence, so the user's intent is preserved.
"""

from __future__ import annotations

import difflib
import re

from ..nlp.normalize import fold_chars, normalize_text

# Canonical term -> common mishear / misspelling variants (all normalized).
DEFAULT_TERMS: dict[str, list[str]] = {
    "جاسم": ["جاسم", "جاسِم", "جستم", "chasem", "jasem", "jasm", "جاستم"],
    "پایتون": ["پایتون", "پایتون", "پایتون", "پایتون", "python", "پایتون"],
    "کیبورد": ["کیبورد", "کبورد", "keyboard"],
    "بلوتوث": ["بلوتوث", "بلوتوث", "بلوتوع", "bluetooth"],
    "وای‌فای": ["وایفای", "وای فای", "wifi", "وایفای"],
    "اینستاگرام": ["اینستاگرام", "اینستا", "instagram"],
    "واتساپ": ["واتساپ", "واتساب", "whatsapp"],
    "یوتیوب": ["یوتیوب", "یوتوب", "youtube"],
}


class Corrector:
    def __init__(self, extra_terms: list[str] | None = None, enabled: bool = True) -> None:
        self.enabled = enabled
        self.terms: dict[str, list[str]] = {k: list(v) for k, v in DEFAULT_TERMS.items()}
        for term in extra_terms or []:
            self.terms.setdefault(term, []).append(term)
        self._lookup: dict[str, str] = {}
        for canonical, variants in self.terms.items():
            for v in variants:
                key = re.sub(r"\s+", "", fold_chars(v.lower()))
                self._lookup[key] = canonical

    def correct(self, text: str) -> tuple[str, list[str]]:
        """Return (corrected_text, list_of_changes)."""
        if not self.enabled or not text:
            return text, []
        changes: list[str] = []
        tokens = re.findall(r"[\w\u0600-\u06ff]+", text.lower())
        out = text
        for token in tokens:
            folded = re.sub(r"\s+", "", fold_chars(token))
            if folded in self._lookup:
                canonical = self._lookup[folded]
                if token != canonical.lower():
                    pattern = re.compile(
                        rf"(?i)(?<![\w\u0600-\u06ff]){re.escape(token)}(?![\w\u0600-\u06ff])"
                    )
                    if pattern.search(out):
                        out = pattern.sub(canonical, out)
                        changes.append(f"{token} -> {canonical}")
                continue
            if token in self.terms:
                continue
            for known in self._lookup:
                # Only very close matches (edit-distance ~1 on short words,
                # ratio >= 0.88 overall) are rewritten.
                if abs(len(token) - len(known)) > 1:
                    continue
                if difflib.SequenceMatcher(None, token, known).ratio() >= 0.88:
                    canonical = self._lookup[known]
                    pattern = re.compile(rf"(?i)(?<![\w\u0600-\u06ff]){re.escape(token)}(?![\w\u0600-\u06ff])")
                    if pattern.search(out):
                        out = pattern.sub(canonical, out)
                        changes.append(f"{token} -> {canonical}")
                    break
        return out, changes


def looks_uncertain(confidence: float, threshold: float, text: str) -> bool:
    """Low confidence or very short garbage output should be treated carefully."""
    if not text.strip():
        return True
    return confidence < threshold
