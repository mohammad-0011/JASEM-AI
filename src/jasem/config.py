"""Typed configuration for JASEM.

The user configuration is a JSON document stored in the per-user data
directory. Unknown keys are ignored so configs survive upgrades; missing keys
fall back to the defaults below. Secrets (API keys) never live in this file —
they are read from environment variables or the project-local ``.env``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict, fields
from pathlib import Path
from typing import Any

from . import paths


DEFAULT_WAKE_PHRASES = ["هی جاسم", "سلام جاسم", "جاسم", "hey jasem", "hi jasem"]


@dataclass
class AudioConfig:
    input_device: int | None = None      # None = system default
    output_device: int | None = None
    sample_rate: int = 16000
    frame_ms: int = 30                   # capture frame granularity (10/20/30 for webrtcvad)
    vad_aggressiveness: int = 2          # 0..3, higher = filters more noise
    speech_min_ms: int = 250             # speech must last this long to start an utterance
    silence_end_ms: int = 750            # silence that ends an utterance (anti-truncation)
    max_utterance_s: float = 30.0
    echo_gate_tail_ms: int = 350         # keep mic gated after playback stops


@dataclass
class WakeConfig:
    enabled: bool = True
    engine: str = "vosk"
    phrases: list[str] = field(default_factory=lambda: list(DEFAULT_WAKE_PHRASES))
    fa_model_dir: str = ""               # resolved against models/vosk when empty
    en_model_dir: str | None = ""        # enables English "Hey JASEM" matching when set
    match_cooldown_ms: int = 1500        # debounce between activations
    barge_in: bool = True                # wake phrase / stop command interrupts playback
    stop_phrases: list[str] = field(
        default_factory=lambda: ["ساکت شو", "بس کن", "stop", "خفه شو"]
    )


@dataclass
class STTConfig:
    engine: str = "faster-whisper"
    model_size: str = "small"            # tiny/base/small/medium/large-v3
    device: str = "cpu"                  # cpu | cuda
    compute_type: str = "int8"
    language: str = "fa"
    beam_size: int = 5
    correction_enabled: bool = True
    vocabulary: list[str] = field(default_factory=list)
    low_confidence_threshold: float = 0.55


@dataclass
class TTSConfig:
    engine: str = "edge"                 # edge | piper
    edge_voice: str = "fa-IR-DilaraNeural"
    edge_rate: str = "+0%"
    edge_pitch: str = "+0Hz"
    piper_voice: str = "gyro"               # gyro (default) | amir — both fa_IR medium
    piper_length_scale: float = 1.0      # <1 faster, >1 slower
    convert_numbers: str = "auto"        # auto | always | never (spoken Persian digits)
    sentence_max_chars: int = 280
    ack_voice: str = "short"             # short | chime | none


@dataclass
class AIConfig:
    provider: str = "openai-compatible"  # openai-compatible | local
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.8
    max_tokens: int = 400
    timeout_s: float = 45.0
    memory_enabled: bool = False


@dataclass
class PersonalityConfig:
    sarcasm: float = 0.6                 # 0..1
    humor: float = 0.6
    formality: float = 0.2
    response_length: str = "short"       # short | medium | detailed
    warmth: float = 0.8


@dataclass
class AutomationConfig:
    enabled: bool = True
    # action name -> "allow" | "confirm" | "deny"; missing entries use the default
    permissions: dict[str, str] = field(default_factory=dict)
    confirm_unknown: bool = True         # unknown action types must be confirmed
    search_roots: list[str] = field(default_factory=list)  # empty -> user home
    search_max_results: int = 20
    search_timeout_s: float = 15.0
    read_max_bytes: int = 262_144
    audit_enabled: bool = True


@dataclass
class ConversationConfig:
    session_timeout_s: float = 45.0      # silence that ends an active conversation
    history_max_turns: int = 20
    persist_history: bool = True


@dataclass
class UIConfig:
    theme: str = "dark-navy"
    accent: str = "cyan"
    always_on_top: bool = False
    start_minimized: bool = False
    close_to_tray: bool = True
    hotkey_ptt: str = "ctrl+alt+j"       # push-to-talk / conversation toggle
    hotkey_mute: str = "ctrl+alt+m"      # microphone mute toggle


@dataclass
class SystemConfig:
    autostart: bool = False              # start with Windows (explicit opt-in)
    listen_on_start: bool = True
    mic_muted_on_start: bool = False


@dataclass
class AppConfig:
    audio: AudioConfig = field(default_factory=AudioConfig)
    wake: WakeConfig = field(default_factory=WakeConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    personality: PersonalityConfig = field(default_factory=PersonalityConfig)
    automation: AutomationConfig = field(default_factory=AutomationConfig)
    conversation: ConversationConfig = field(default_factory=ConversationConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    system: SystemConfig = field(default_factory=SystemConfig)


def _apply(dc: Any, data: dict[str, Any]) -> None:
    valid = {f.name: f for f in fields(dc)}
    for key, value in data.items():
        if key not in valid:
            continue
        current = getattr(dc, key)
        if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
            _apply(current, value)
        else:
            setattr(dc, key, value)


def load_config(path: Path | None = None) -> AppConfig:
    cfg = AppConfig()
    p = path or paths.user_config_path()
    if p.exists():
        try:
            _apply(cfg, json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            # Corrupt config must not brick startup; defaults stay active.
            pass
    # The project-local .env is the documented place to switch providers, so an
    # explicit OPENAI_BASE_URL / OPENAI_MODEL there wins over the saved JSON
    # (which otherwise always carries a full ai section with the defaults).
    base = os.environ.get("OPENAI_BASE_URL", "").strip()
    if base:
        cfg.ai.base_url = base
    model = os.environ.get("OPENAI_MODEL", "").strip()
    if model:
        cfg.ai.model = model
    return cfg


def save_config(cfg: AppConfig, path: Path | None = None) -> None:
    p = path or paths.user_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader: KEY=VALUE lines, # comments, no dependency."""
    p = path or paths.ENV_FILE
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def resolve_wake_model_dirs(cfg: AppConfig) -> tuple[Path, Path | None]:
    fa = Path(cfg.wake.fa_model_dir) if cfg.wake.fa_model_dir else (
        paths.VOSK_MODELS_DIR / "vosk-model-small-fa-0.42"
    )
    en: Path | None
    if cfg.wake.en_model_dir:
        en = Path(cfg.wake.en_model_dir)
    else:
        cand = paths.VOSK_MODELS_DIR / "vosk-model-small-en-us-0.15"
        en = cand if cand.exists() else None
    return fa, en
