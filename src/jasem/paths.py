"""Canonical filesystem locations for JASEM.

Project-owned assets (models, .env, config example) live next to the source
tree. Mutable user data (logs, audit trail, conversation memory) lives in the
per-user application data directory.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent          # src/jasem
SRC_ROOT = PACKAGE_ROOT.parent                          # src
PROJECT_ROOT = SRC_ROOT.parent                          # project root

MODELS_DIR = PROJECT_ROOT / "models"
VOSK_MODELS_DIR = MODELS_DIR / "vosk"
PIPER_MODELS_DIR = MODELS_DIR / "piper"
QML_DIR = PACKAGE_ROOT / "ui" / "qml"

ENV_FILE = PROJECT_ROOT / ".env"
CONFIG_EXAMPLE = PROJECT_ROOT / "config.example.json"


def user_data_dir() -> Path:
    """Per-user mutable data directory (%APPDATA%/JASEM on Windows)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        root = Path(base) / "JASEM"
    else:  # pragma: no cover - development convenience
        root = Path.home() / ".config" / "jasem"
    root.mkdir(parents=True, exist_ok=True)
    return root


def user_config_path() -> Path:
    return user_data_dir() / "config.json"


def logs_dir() -> Path:
    d = user_data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def audit_log_path() -> Path:
    return user_data_dir() / "audit.log"


def memory_path() -> Path:
    return user_data_dir() / "memory.json"


def history_path() -> Path:
    return user_data_dir() / "history.json"
