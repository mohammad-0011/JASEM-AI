"""Display text -> speech-friendly Persian text.

The answer shown in the UI may contain Markdown, URLs, code or English
technical terms; the spoken version must sound like natural conversation.
"""

from __future__ import annotations

import re

from ..nlp.normalize import convert_numbers_for_speech, split_sentences

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]*)`")
_MD_SYMBOLS_RE = re.compile(r"[*_#>~\[\]()|]+")
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\u200d\ufe0f]+"
)
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def to_spoken(text: str, convert_numbers: str = "auto") -> str:
    """Strip formatting that should not be read aloud."""
    if not text:
        return ""
    text = _CODE_FENCE_RE.sub("، کد حذف شد، ", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _URL_RE.sub("لینک", text)
    text = _EMOJI_RE.sub("", text)
    text = _MD_SYMBOLS_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    if convert_numbers in ("auto", "always"):
        # Piper's Persian voice reads digits unreliably; edge handles them.
        text = convert_numbers_for_speech(text)
    return text


def prepare_chunks(text: str, sentence_max_chars: int = 280,
                   convert_numbers: str = "auto") -> list[str]:
    spoken = to_spoken(text, convert_numbers)
    return split_sentences(spoken, max_chars=sentence_max_chars)
