"""Offline Persian intent matching.

Used (a) alongside the language-model path for automation commands, and (b) as
the primary understanding layer when no API key is available, so JASEM keeps
being useful fully offline. Every matcher works on normalized text and returns
structured arguments — raw model text is never executed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .normalize import normalize_text, normalize_digits


@dataclass
class Intent:
    name: str
    args: dict[str, object] = field(default_factory=dict)
    confidence: float = 0.0
    raw: str = ""


def _norm(text: str) -> str:
    return normalize_text(text)


def _extract_number(text: str) -> int | None:
    m = re.search(r"\d+", normalize_digits(text))
    return int(m.group(0)) if m else None


CONFIRM_YES = {"بله", "بلی", "آره", "اره", "درسته", "yes", "ok", "okay", "تایید", "انجامش بده", "بکن", "کن"}
CONFIRM_NO = {"خیر", "نه", "no", "لغو", "انصراف", "cancel", "ن", "نمیخوام", "نمی‌خوام"}


def match_confirmation(text: str) -> bool | None:
    t = _norm(text).lower().strip(" !.؟")
    if t in CONFIRM_YES:
        return True
    if t in CONFIRM_NO:
        return False
    return None


_APP_OPEN_RE = re.compile(
    r"^(?:لطفاً|لطفا|خواهش میکنم|خواهش می‌کنم\s*)?"
    r"(?P<body>.+?)\s*"
    r"(?:رو|روی|و)?\s*(?:باز|راه)\s*(?:کن|کنید|بزن|بزنید)"
    r"(?:\s*(?:کن|کنید))?$"
)

_URL_RE = re.compile(
    r"(?:سایت|وبسایت|وب\s*سایت|صفحه|لینک)?\s*(?P<url>(?:https?://|www\.)[^\s]+|[a-z0-9-]+\.(?:com|ir|org|net|io|dev|ai|me|co)(?:/[^\s]*)?)",
    re.IGNORECASE,
)


def _clean_app_name(name: str) -> str:
    name = _norm(name)
    for filler in ("برنامه", "اپلیکیشن", "نرم افزار", "اپ", "نرم‌افزار"):
        if name.startswith(filler + " "):
            name = name[len(filler) + 1:]
    return name.strip(" !.؟،")


def match_intent(text: str) -> Intent | None:
    """Best-effort offline intent detection on normalized text."""
    raw = text
    t = _norm(text).lower().strip()
    if not t:
        return None

    # --- confirmation / control -------------------------------------------
    if t in {"تکرار کن", "دوباره بگو", "تکرار", "repeat"}:
        return Intent("repeat", confidence=0.95, raw=raw)
    if any(p in t for p in ("ساکت شو", "خفه شو", "بس کن", "صداشو قطع کن", "stop talking")):
        return Intent("stop_speaking", confidence=0.9, raw=raw)
    if t in {"ایست", "توقف", "stop", "لغو همه", " emergency stop"}:
        return Intent("emergency_stop", confidence=0.9, raw=raw)

    # --- media / volume ----------------------------------------------------
    vol_up = ("صدارو ببر", "صدا رو ببر", "بلندتر", "صدارو زیاد کن", "صدا رو زیاد کن", "volume up")
    vol_down = ("صدارو ببر پایین", "صدا رو ببر پایین", "آرومتر", "کمتر", "صدارو کم کن", "صدا رو کم کن", "volume down")
    if any(p in t for p in ("بیصدا", "بی صدا", "قطع صدا", "میوت", "mute")) and "ش" not in t[-2:]:
        return Intent("volume_mute", confidence=0.9, raw=raw)
    if any(p in t for p in vol_up):
        n = _extract_number(t)
        return Intent("volume_set", {"delta": n or 10, "direction": "up"}, 0.9, raw)
    if any(p in t for p in vol_down):
        n = _extract_number(t)
        return Intent("volume_set", {"delta": n or 10, "direction": "down"}, 0.9, raw)
    m = re.search(r"صدا(?: رو)? (?:روی|بذار|بگذار|کن)?\s*(\d{1,3})", t)
    if m:
        return Intent("volume_set", {"level": int(m.group(1))}, 0.92, raw)

    # --- web ----------------------------------------------------------------
    if "مرورگر" in t and ("باز کن" in t or "بازکن" in t):
        return Intent("open_browser", confidence=0.9, raw=raw)
    m = _URL_RE.search(t)
    if m and any(k in t for k in ("باز کن", "بازکن", "برو", "برو به", "سایت", "لینک")):
        return Intent("open_url", {"url": m.group("url")}, 0.85, raw)
    m = re.search(r"(?:در گوگل|با گوگل|گوگل)?\s*(?:دنبال|برای)\s+(.+?)\s+(?:بگرد|بگردید|جستجو کن|جستجو کنید)|"
                  r"گوگل کن\s*(.+)|جستجو کن\s*(.+)", t)
    if m:
        q = next(g for g in m.groups() if g)
        return Intent("web_search", {"query": q.strip()}, 0.88, raw)

    # --- system info ---------------------------------------------------------
    if any(k in t for k in ("فضای دیسک", "فضای آزاد", "فضای هارد", "دیسک")):
        return Intent("disk_space", confidence=0.9, raw=raw)
    if any(k in t for k in ("باتری", "شارژ")):
        return Intent("battery", confidence=0.9, raw=raw)
    if any(k in t for k in ("اینترنت", "اتصال شبکه", "شبکه وصله", "آنلاینم")):
        return Intent("network_check", confidence=0.85, raw=raw)
    if any(k in t for k in ("وضعیت سیستم", "مشخصات سیستم", "سیستمم چطوره", "سیستم چطوره",
                            "رم و پردازنده", "پردازنده", "cpu")):
        return Intent("system_info", confidence=0.88, raw=raw)
    if any(k in t for k in ("برنامه های باز", "برنامه‌های باز", "پروسه ها", "پروسه‌ها",
                            "چه برنامه", "پردازش های فعال")):
        return Intent("list_processes", confidence=0.85, raw=raw)

    # --- files ----------------------------------------------------------------
    m = re.search(r"(?:فایل|پوشه|پوشهٔ|فایلی به اسم|با اسم)\s+(.+?)\s+(?:رو|روی)?\s*پیدا کن(?:ید)?", t)
    if m or re.search(r"دنبال\s+(.+?)\s+بگرد", t):
        q = m.group(1) if m else re.search(r"دنبال\s+(.+?)\s+بگرد", t).group(1)
        folder = None
        fm = re.search(r"(?:در|توی|تو)\s+(?:پوشه\s+)?(.+)$", t)
        if fm and len(fm.group(1).split()) <= 4:
            folder = fm.group(1).strip()
        return Intent("find_file", {"query": q.strip(), "folder": folder}, 0.85, raw)
    m = re.search(r"فایل\s+(.+?)\s+(?:رو|روی)?\s*(?:بخوان|بخون|بخونید|بخوانید)", t)
    if m:
        return Intent("read_file", {"path": m.group(1).strip()}, 0.85, raw)

    # --- notes -----------------------------------------------------------------
    m = re.search(r"یادداشت(?:ت|ام)?\s*(.+?)\s+(?:رو|روی)?\s*(?:بنویس|نوشتن|ثبت کن)|(?:بنویس|ثبت کن)\s*یادداشت\s*(.+)", t)
    if m:
        note = next(g for g in m.groups() if g)
        return Intent("create_note", {"text": note.strip()}, 0.85, raw)

    # --- reminders --------------------------------------------------------------
    m = re.search(r"(?:یادآوری|یاداوری) کن(?:ید)?(?: که)?\s*(.+?)\s*(?:رو)?\s*(\d+)\s*(دقیقه|ساعت|ثانیه)\s*(دیگه|دیگر)", t)
    if m:
        n = int(m.group(2))
        unit = {"دقیقه": 60, "ساعت": 3600, "ثانیه": 1}[m.group(3)]
        return Intent("reminder", {"text": m.group(1).strip(), "seconds": n * unit}, 0.85, raw)

    # --- calculator --------------------------------------------------------------
    def _calc_expr(s: str) -> str:
        return (s.replace("به علاوه", "+").replace("منفی", "-")
                 .replace("تقسیم", "/").replace("ضرب در", "*")
                 .replace("ضربدر", "*").replace("×", "*")
                 .replace("بعلامه", "+").replace("مساویه", "="))

    calc_t = _calc_expr(t)
    if re.fullmatch(r"[\d\s\+\-\*/\.\(\)%]+", calc_t) and re.search(r"[\+\-\*/]", calc_t):
        return Intent("calculate", {"expression": calc_t.strip(" =")}, 0.95, raw)
    m = re.search(r"حساب کن(?:ید)?\s*(.+)", t)
    if m and re.search(r"[\d\+\-\*/]", m.group(1)):
        return Intent("calculate", {"expression": _calc_expr(m.group(1)).strip(" =")}, 0.85, raw)

    # --- applications / folders ---------------------------------------------------
    m = _APP_OPEN_RE.match(t)
    if m:
        body = m.group("body")
        if any(k in body for k in ("سایت", "مرورگر", "لینک")) or _URL_RE.search(body):
            um = _URL_RE.search(body)
            if um:
                return Intent("open_url", {"url": um.group("url")}, 0.8, raw)
        if "پوشه" in body or re.search(r"^[a-z]:\\|\\\\|^دیسک", body):
            fm2 = re.search(r"(?:پوشه\s*)?(.+)", body)
            return Intent("open_path", {"path": (fm2.group(1) if fm2 else body).strip()}, 0.8, raw)
        name = _clean_app_name(body)
        if name:
            return Intent("open_app", {"name": name}, 0.85, raw)

    if "ساعت" in t and any(k in t for k in ("چنده", "چند شده", "وقت", "الان")):
        return Intent("time_now", confidence=0.8, raw=raw)

    return None
