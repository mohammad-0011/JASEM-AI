"""Start-menu application index and launching."""

from __future__ import annotations

import difflib
import logging
import os
import re
import subprocess
import threading
from pathlib import Path

log = logging.getLogger("jasem.automation.apps")

# Common Persian/colloquial names -> known Windows executables.
FALLBACK_ALIASES: dict[str, str] = {
    "دفترچه یادداشت": "notepad.exe",
    "دفتر یادداشت": "notepad.exe",
    "یادداشت": "notepad.exe",
    "notepad": "notepad.exe",
    "ماشین حساب": "calc.exe",
    "ماشین‌حساب": "calc.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "کالکولیشن": "calc.exe",
    "مدیر وظایف": "taskmgr.exe",
    "task manager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "کنترل پنل": "control.exe",
    "control panel": "control.exe",
    "اکسپلورر": "explorer.exe",
    "explorer": "explorer.exe",
    "فایل اکسپلورر": "explorer.exe",
    "پاورشل": "powershell.exe",
    "powershell": "powershell.exe",
    "ترمینال": "wt.exe",
    "cmd": "cmd.exe",
    "فرمان": "cmd.exe",
    "تنظیمات": "ms-settings:",
    "settings": "ms-settings:",
    "ورده": "winword.exe",
    "اکسل": "excel.exe",
    "واتساپ": "whatsapp.exe",
    "تلگرام": "telegram.exe",
    "اسپاتیفای": "spotify.exe",
    "کروم": "chrome.exe",
    "chrome": "chrome.exe",
    "گوگل کروم": "chrome.exe",
    "فایرفاکس": "firefox.exe",
    "firefox": "firefox.exe",
    "اج": "msedge.exe",
    "edge": "msedge.exe",
    "مرورگر": "",   # resolved to default browser
}


def _norm(s: str) -> str:
    from ..nlp.normalize import normalize_text

    return re.sub(r"\s+", " ", normalize_text(s)).strip().lower()


class AppIndex:
    """Lazy fuzzy index of installed applications (.lnk in Start Menu)."""

    def __init__(self) -> None:
        self._entries: dict[str, str] = {}
        self._lock = threading.Lock()
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        roots = [
            Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        ]
        for root in roots:
            if not root.exists():
                continue
            for lnk in root.rglob("*.lnk"):
                name = lnk.stem
                self._entries[_norm(name)] = str(lnk)
        log.info("app index built: %d entries", len(self._entries))

    def refresh_async(self) -> None:
        threading.Thread(target=self._load, name="jasem-appindex", daemon=True).start()

    def resolve(self, name: str) -> str | None:
        """Return a launchable path (or shell command) for a fuzzy app name."""
        self._load()
        n = _norm(name)
        if not n:
            return None
        if n in FALLBACK_ALIASES:
            alias = FALLBACK_ALIASES[n]
            return alias if alias else self._default_browser()
        if n in self._entries:
            return self._entries[n]
        candidates = list(self._entries.keys())
        close = difflib.get_close_matches(n, candidates, n=1, cutoff=0.72)
        if close:
            return self._entries[close[0]]
        # containment match (spoken names often include extra words)
        for key, path in self._entries.items():
            if n in key or key in n:
                return path
        # direct executable name or path given by the user
        if re.fullmatch(r"[\w\-]+\.exe", n) or "\\" in name or "/" in name:
            return name
        return None

    @staticmethod
    def _default_browser() -> str | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"HTTP\shell\open\command") as key:
                cmd = winreg.QueryValueEx(key, "")[0]
                return cmd if cmd else None
        except OSError:
            return None


def launch(target: str) -> tuple[bool, str]:
    """Launch a resolved target. Never runs through a shell string."""
    try:
        if target.endswith(".lnk") or target.lower().endswith(".exe") or "ms-settings" in target:
            os.startfile(target)  # noqa: S606 - allowlisted paths only
        else:
            subprocess.Popen(target, shell=False)
        return True, target
    except FileNotFoundError:
        return False, f"executable not found: {target}"
    except Exception as exc:
        return False, str(exc)
