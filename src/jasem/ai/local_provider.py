"""Offline conversational fallback.

When no API key is configured, JASEM still answers conversationally (with a
limited, varied repertoire) and leans on the deterministic intent layer for
real work. This keeps every offline claim honest: no network, no model.
"""

from __future__ import annotations

import random
import time
from typing import Iterator

from ..config import PersonalityConfig

_GREETINGS = [
    "سلامت بدم! من جاسمم، همین‌جا نشستم و منتظرم بگی چیکار کنیم.",
    "علیک‌السلام! بالاخره سری به من زدی. بگو ببینم چه خبر.",
    "سلام! حالت چطوره؟ من که آماده‌ام، تو بگو.",
]

_TIME_REPLIES = [
    "الان {h} و {m} دقیقه است. ساعت رو خودت هم می‌تونی ببینی، ولی اشکالی نداره.",
]

_UNKNOWN = [
    "کمی مبهمه. یه جور دیگه بگو تا ببینم می‌تونم کمکت کنم.",
    "این یکی رو بدون سرویس هوش مصنوعی نمی‌تونم دقیق بفهمم. کلید API رو که تنظیم کنی، جاده‌ها باز می‌شه.",
    "همینجوری که گفتی از آب درنیومد. یه کم شفاف‌تر بگو.",
]

_THANKS = [
    "خواهش می‌کنم، هر وقت بودی در خدمتم.",
    "قابلی نداشت. رفیقیم دیگه.",
]

_NO_KEY_HINT = (
    "الان کلید سرویس هوش مصنوعی تنظیم نشده، برای همین با حالت آفلاین کار می‌کنم. "
    "اگه بخوای، می‌تونی کلید یه مدل زبانی رو توی فایل .env بذاری تا کامل‌تر جواب بدم."
)


class LocalProvider:
    """Deterministic-intent + template conversation fallback (fully offline)."""

    name = "local"

    def __init__(self, personality: PersonalityConfig) -> None:
        self.personality = personality
        self._rng = random.Random(time.time_ns())

    @property
    def available(self) -> bool:
        return True

    def _pick(self, options: list[str]) -> str:
        return self._rng.choice(options)

    def chat_stream(self, messages: list[dict]) -> Iterator[str]:
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break
        yield self._respond(last_user)

    def chat(self, messages: list[dict]) -> str:
        return "".join(self.chat_stream(messages))

    def _respond(self, text: str) -> str:
        t = (text or "").strip().lower()
        if any(k in t for k in ("سلام", "سلام", "حالت چطوره", "خبریه", "خوبی")):
            return self._pick(_GREETINGS)
        if any(k in t for k in ("ممنون", "مرسی", "متشکرم", "thanks")):
            return self._pick(_THANKS)
        if any(k in t for k in ("کی هستی", "تو کیستی", "اسمت چیه", "خودتو معرفی")):
            return ("من جاسمم؛ دستیار صوتی خودت. بیشتر از اینم که یه جملهٔ تکراری "
                    "درباره خودم بگم، الان در خدمتم.")
        if any(k in t for k in ("چه خبر", "چیکار می‌تونی", "چه کارهایی", "امکانات")):
            return ("می‌تونم برنامه‌ها و پوشه‌ها رو باز کنم، فایل پیدا کنم، وضعیت سیستم "
                    "و فضای دیسک رو بگم، صدا رو تنظیم کنم، حساب کنم و یادداشت و یادآوری "
                    "بسازم. " + _NO_KEY_HINT)
        if any(k in t for k in ("چه ساعتی", "ساعت چنده", "وقت چنده")):
            now = time.localtime()
            return self._pick(_TIME_REPLIES).format(h=now.tm_hour, m=now.tm_min)
        if any(k in t for k in ("کمک", "help")):
            return ("بگو «برنامه فلان رو باز کن»، «فضای دیسک چنده»، «صدارو ببر بالا» "
                    "یا هر چیز دیگه‌ای؛ اگه لازم باشه سوال می‌پرسم.")
        return self._pick(_UNKNOWN) + " " + _NO_KEY_HINT
