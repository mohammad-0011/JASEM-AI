"""Persian text normalization and speech-text utilities.

Normalization is intentionally *light*: it folds character-variant differences
(ي/ی, ك/ک, Arabic/Persian digits) that speech recognizers frequently disagree
about, without rewriting the user's words.
"""

from __future__ import annotations

import re
import unicodedata

# Character folding: Arabic variants -> canonical Persian forms.
_CHAR_MAP = str.maketrans({
    "\u064a": "\u06cc",  # ي -> ی
    "\u0649": "\u06cc",  # ى -> ی
    "\u06d2": "\u06cc",  # ے -> ی
    "\u0643": "\u06a9",  # ك -> ک
    "\u06aa": "\u06a9",  # ڪ -> ک
    "\u0629": "\u0647",  # ة -> ه
    "\u0623": "\u0627",  # أ -> ا
    "\u0625": "\u0627",  # إ -> ا
    "\u0671": "\u0627",  # ٱ -> ا
    "\u0624": "\u0648",  # ؤ -> و
})

_DIGIT_MAP = str.maketrans({
    "\u06f0": "0", "\u06f1": "1", "\u06f2": "2", "\u06f3": "3", "\u06f4": "4",
    "\u06f5": "5", "\u06f6": "6", "\u06f7": "7", "\u06f8": "8", "\u06f9": "9",
    "\u0660": "0", "\u0661": "1", "\u0662": "2", "\u0663": "3", "\u0664": "4",
    "\u0665": "5", "\u0666": "6", "\u0667": "7", "\u0668": "8", "\u0669": "9",
})

_TASHKEEL_RE = re.compile("[\u064b-\u0652\u0670\u0640]")  # harakat + tatweel
_ZWNJ = "\u200c"
_PUNCT_RE = re.compile(r"[.!،,؟?;؛:«»\"'()<>{}\[\]]+")
_WS_RE = re.compile(r"\s+")


def fold_chars(text: str) -> str:
    return text.translate(_CHAR_MAP)


def normalize_digits(text: str) -> str:
    return text.translate(_DIGIT_MAP)


def strip_diacritics(text: str) -> str:
    return _TASHKEEL_RE.sub("", text)


def normalize_text(text: str) -> str:
    """General-purpose Persian normalization (display-safe, keeps spacing)."""
    text = unicodedata.normalize("NFKC", text)
    text = fold_chars(text)
    text = normalize_digits(text)
    text = strip_diacritics(text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def wake_normalize(text: str) -> str:
    """Aggressive normalization for wake-phrase matching: no spaces, no ZWNJ,
    no punctuation, lowercase Latin."""
    text = normalize_text(text).lower()
    text = text.replace(_ZWNJ, "")
    text = re.sub(r"[^0-9\u0600-\u06ffa-z]", "", text)
    return text


def collapse_zwnj(text: str) -> str:
    """Turn ZWNJ into a plain space for engines that mishandle it."""
    return text.replace(_ZWNJ, " ")


def strip_punctuation(text: str) -> str:
    return _PUNCT_RE.sub(" ", text).strip()


_PERSIAN_ONES = [
    "صفر", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه",
]
_PERSIAN_TEENS = [
    "ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده",
    "هجده", "نزده",
]
_PERSIAN_TENS = [
    "", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود",
]
_PERSIAN_HUNDREDS = [
    "", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد",
]


def _three_digits_to_words(n: int) -> str:
    parts: list[str] = []
    h, rest = divmod(n, 100)
    if h:
        parts.append(_PERSIAN_HUNDREDS[h])
    if rest:
        if rest < 10:
            parts.append(_PERSIAN_ONES[rest])
        elif rest < 20:
            parts.append(_PERSIAN_TEENS[rest - 10])
        else:
            t, o = divmod(rest, 10)
            parts.append(_PERSIAN_TENS[t] + (f" و {_PERSIAN_ONES[o]}" if o else ""))
    return " و ".join(parts)


def number_to_persian_words(n: int) -> str:
    """Convert an integer (up to 999,999,999) to Persian words for TTS."""
    if n < 0:
        return "منفی " + number_to_persian_words(-n)
    if n < 1000:
        return _three_digits_to_words(n) or "صفر"
    chunks: list[str] = []
    thousands, rest = divmod(n, 1000)
    if thousands:
        prefix = _three_digits_to_words(thousands)
        suffix = " هزار" if thousands < 1000 else ""
        chunks.append(prefix + suffix)
    if rest:
        chunks.append(_three_digits_to_words(rest))
    return " و ".join(chunks)


def convert_numbers_for_speech(text: str) -> str:
    """Replace ASCII/Persian digit runs with Persian words."""

    def repl(m: re.Match[str]) -> str:
        try:
            return number_to_persian_words(int(m.group(0)))
        except ValueError:
            return m.group(0)

    text = normalize_digits(text)
    return re.sub(r"\d+", repl, text)


def split_sentences(text: str, max_chars: int = 280) -> list[str]:
    """Punctuation-aware sentence split with a hard max length so each chunk
    stays in the natural prosody range of TTS engines."""
    text = _WS_RE.sub(" ", text).strip()
    if not text:
        return []
    pieces = re.split(r"(?<=[.!؟?;؛])\s+", text)
    out: list[str] = []
    for piece in pieces:
        piece = piece.strip()
        while len(piece) > max_chars:
            cut = piece.rfind("،", 0, max_chars)
            if cut < max_chars // 2:
                cut = piece.rfind(" ", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            out.append(piece[:cut].strip())
            piece = piece[cut:].strip()
        if piece:
            out.append(piece)
    return out
