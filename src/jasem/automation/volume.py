"""System volume control (pycaw / Windows Core Audio)."""

from __future__ import annotations

import logging

log = logging.getLogger("jasem.automation.volume")

try:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    _PYCAW = True
except Exception:  # pragma: no cover
    _PYCAW = False


def _endpoint():
    if not _PYCAW:
        raise RuntimeError("pycaw/comtypes unavailable")
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return interface.QueryInterface(IAudioEndpointVolume)


def is_available() -> bool:
    return _PYCAW


def get_volume() -> float | None:
    try:
        return float(_endpoint().GetMasterVolumeLevelScalar())
    except Exception as exc:
        log.warning("get_volume failed: %s", exc)
        return None


def set_volume(level: float) -> bool:
    try:
        _endpoint().SetMasterVolumeLevelScalar(max(0.0, min(1.0, level)), None)
        return True
    except Exception as exc:
        log.warning("set_volume failed: %s", exc)
        return False


def adjust_volume(delta: int) -> float | None:
    """delta in percent points (may be negative)."""
    current = get_volume()
    if current is None:
        return None
    target = max(0.0, min(1.0, current + delta / 100.0))
    return target if set_volume(target) else None


def get_mute() -> bool | None:
    try:
        return bool(_endpoint().GetMute())
    except Exception as exc:
        log.warning("get_mute failed: %s", exc)
        return None


def set_mute(muted: bool) -> bool:
    try:
        _endpoint().SetMute(1 if muted else 0, None)
        return True
    except Exception as exc:
        log.warning("set_mute failed: %s", exc)
        return False


def toggle_mute() -> bool | None:
    state = get_mute()
    if state is None:
        return None
    return set_mute(not state)
