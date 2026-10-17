"""Global keyboard shortcuts via Win32 RegisterHotKey (no extra dependency).

Two configurable shortcuts:

- push-to-talk / conversation toggle (default Ctrl+Alt+J)
- microphone mute toggle             (default Ctrl+Alt+M)

A dedicated thread owns the Win32 message loop; callbacks fire on that thread
and are expected to be thread-safe (Qt slots reached through signals are).
"""

from __future__ import annotations

import ctypes
import logging
import threading
from typing import Callable

log = logging.getLogger("jasem.hotkeys")

if hasattr(ctypes, "WinDLL"):
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _user32.RegisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
    _user32.RegisterHotKey.restype = ctypes.c_bool
    _user32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _user32.UnregisterHotKey.restype = ctypes.c_bool
    _user32.GetMessageW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
    _user32.PostThreadMessageW.argtypes = [ctypes.c_ulong, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    _kernel32.GetCurrentThreadId.restype = ctypes.c_ulong
    _WIN = True
else:  # pragma: no cover - non-Windows dev environments
    _WIN = False

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

_MODIFIERS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT,
              "shift": MOD_SHIFT, "win": MOD_WIN, "super": MOD_WIN}

_VK = {  # letters and digits map to their Windows virtual keys
    **{chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)},
    **{str(d): 0x30 + d for d in range(10)},
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "space": 0x20, "esc": 0x1B, "escape": 0x1B,
}


def parse_hotkey(combo: str) -> tuple[int, int] | None:
    """'ctrl+alt+j' -> (MOD_CONTROL|MOD_ALT, VK_J). None when unparseable."""
    if not combo or not _WIN:
        return None
    mods = 0
    key = ""
    for part in combo.lower().replace("-", "+").split("+"):
        part = part.strip()
        if not part:
            continue
        if part in _MODIFIERS:
            mods |= _MODIFIERS[part]
        elif part in _VK:
            key = part
        else:
            return None
    if not key:
        return None
    if mods == 0:
        # A bare key would hijack normal typing globally; require a modifier.
        return None
    return mods, _VK[key]


class HotkeyManager:
    """Registers global hotkeys and dispatches WM_HOTKEY to callbacks."""

    def __init__(self) -> None:
        self._bindings: dict[int, Callable[[], None]] = {}
        self._registered: list[int] = []
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()

    def register(self, combo: str, callback: Callable[[], None]) -> bool:
        parsed = parse_hotkey(combo)
        if parsed is None:
            log.warning("unrecognized hotkey combo: %r", combo)
            return False
        mods, vk = parsed
        hotkey_id = len(self._bindings) + 1
        if not _user32.RegisterHotKey(None, hotkey_id, mods, vk):
            log.warning("hotkey %r already in use by another application", combo)
            return False
        self._bindings[hotkey_id] = callback
        self._registered.append(hotkey_id)
        log.info("global hotkey registered: %s", combo)
        return True

    def start(self) -> None:
        """Spins the message-loop thread (required for WM_HOTKEY delivery)."""
        if not _WIN or not self._registered:
            return
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="jasem-hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3.0)

    def _loop(self) -> None:
        self._thread_id = _kernel32.GetCurrentThreadId()
        self._ready.set()
        msg = ctypes.c_void_p()
        while True:
            res = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if res <= 0:  # WM_QUIT or error
                break
            if msg.value == WM_HOTKEY:
                # wParam carries the hotkey id (truncated to 32 bits).
                hotkey_id = ctypes.cast(msg, ctypes.POINTER(ctypes.c_int))[0].value
                callback = self._bindings.get(hotkey_id)
                if callback:
                    try:
                        callback()
                    except Exception:
                        log.exception("hotkey callback failed")
        self._thread_id = None

    def stop(self) -> None:
        for hotkey_id in self._registered:
            _user32.UnregisterHotKey(None, hotkey_id)
        self._registered.clear()
        if self._thread_id:
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, None, None)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
