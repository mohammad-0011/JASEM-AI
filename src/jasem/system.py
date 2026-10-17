"""Windows integration: start-with-Windows (explicit opt-in only)."""

from __future__ import annotations

import logging
import sys

log = logging.getLogger("jasem.system")

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_VALUE = "JASEM"


def _launcher_command() -> str:
    """Command line for a hidden startup launch (pythonw + launch.pyw)."""
    from . import paths

    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    launcher = paths.PROJECT_ROOT / "launch.pyw"
    return f'"{pythonw}" "{launcher}"'


def autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _APP_VALUE)
        return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> bool:
    """Writes/removes HKCU Run entry. Never requests elevation."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, _APP_VALUE, 0, winreg.REG_SZ, _launcher_command())
            else:
                try:
                    winreg.DeleteValue(key, _APP_VALUE)
                except FileNotFoundError:
                    pass
        log.info("autostart %s", "enabled" if enabled else "disabled")
        return True
    except OSError:
        log.exception("failed to update autostart")
        return False
