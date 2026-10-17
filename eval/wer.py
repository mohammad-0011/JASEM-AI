"""Word/Character Error Rate computation (Levenshtein alignment)."""

from __future__ import annotations

import re

from jasem.nlp.normalize import normalize_text


def _edit_distance(a: list[str], b: list[str]) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"\s+", normalize_text(text).strip()) if w]


def _chars(text: str) -> list[str]:
    return [c for c in re.sub(r"\s+", "", normalize_text(text))]


def wer(reference: str, hypothesis: str) -> float:
    r, h = _words(reference), _words(hypothesis)
    if not r:
        return 0.0 if not h else 1.0
    return _edit_distance(r, h) / len(r)


def cer(reference: str, hypothesis: str) -> float:
    r, h = _chars(reference), _chars(hypothesis)
    if not r:
        return 0.0 if not h else 1.0
    return _edit_distance(r, h) / len(r)


def aggregate(results: list[tuple[str, str]]) -> dict:
    """results: list of (reference, hypothesis). Pooled WER/CER + per-item."""
    if not results:
        return {"wer": 0.0, "cer": 0.0, "items": 0}
    total_ref_words = total_ref_chars = 0
    total_word_err = total_char_err = 0
    per_item = []
    for ref, hyp in results:
        rw, hw = _words(ref), _words(hyp)
        rc, hc = _chars(ref), _chars(hyp)
        we = _edit_distance(rw, hw)
        ce = _edit_distance(rc, hc)
        total_ref_words += len(rw) or 1
        total_ref_chars += len(rc) or 1
        total_word_err += we
        total_char_err += ce
        per_item.append({"ref": ref, "hyp": hyp, "wer": we / max(1, len(rw)),
                         "cer": ce / max(1, len(rc))})
    return {
        "wer": round(total_word_err / total_ref_words, 4),
        "cer": round(total_char_err / total_ref_chars, 4),
        "items": len(results),
        "per_item": per_item,
    }
