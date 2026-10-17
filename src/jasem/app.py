"""Application bootstrap and CLI entry point."""

from __future__ import annotations

import argparse
import logging
import sys

from . import paths
from .config import load_config, load_dotenv
from .logging_setup import setup_logging

log = logging.getLogger("jasem.app")


def _environment_report(cfg) -> str:
    lines = ["JASEM environment check", "=" * 40]
    import platform

    lines.append(f"Python : {platform.python_version()} ({sys.executable})")
    lines.append(f"OS     : {platform.platform()}")
    try:
        import psutil

        lines.append(f"CPU    : {psutil.cpu_count(logical=False)} cores / "
                     f"{psutil.cpu_count(logical=True)} threads")
        lines.append(f"RAM    : {round(psutil.virtual_memory().total / 1024 ** 3, 1)} GB")
    except Exception as exc:
        lines.append(f"psutil : unavailable ({exc})")

    checks = [
        ("PySide6", "ui"), ("sounddevice", "audio"), ("webrtcvad", "vad"),
        ("vosk", "wake word"), ("faster_whisper", "speech recognition"),
        ("av", "audio decode"), ("edge_tts", "cloud TTS"), ("piper", "offline TTS"),
        ("onnxruntime", "offline TTS"), ("pycaw", "volume control"),
        ("httpx", "network"),
    ]
    for mod, label in checks:
        try:
            __import__(mod)
            lines.append(f"[ ok ] {label:<18} ({mod})")
        except Exception as exc:
            lines.append(f"[fail] {label:<18} ({mod}): {exc}")

    from .config import resolve_wake_model_dirs

    fa_dir, en_dir = resolve_wake_model_dirs(cfg)
    lines.append(f"wake fa model: {'FOUND' if fa_dir.exists() else 'MISSING'} ({fa_dir})")
    lines.append(f"wake en model: {'FOUND' if en_dir and en_dir.exists() else 'not set'}")

    piper_model = paths.PIPER_MODELS_DIR / f"fa_IR-{cfg.tts.piper_voice}-medium.onnx"
    lines.append(f"piper voice  : {'FOUND' if piper_model.exists() else 'MISSING'} ({piper_model.name})")

    import os

    key_set = bool(os.environ.get(cfg.ai.api_key_env))
    lines.append(f"AI key '{cfg.ai.api_key_env}': {'set' if key_set else 'NOT set (offline mode)'}")

    try:
        import sounddevice as sd

        default_in = sd.query_devices(kind="input")
        lines.append(f"default mic  : {default_in['name']}")
    except Exception as exc:
        lines.append(f"default mic  : unavailable ({exc})")

    from .automation import volume

    lines.append(f"volume ctrl  : {'available' if volume.is_available() else 'unavailable'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jasem", description="JASEM — Persian voice assistant")
    parser.add_argument("--check", action="store_true", help="print environment diagnostics and exit")
    parser.add_argument("--smoke", action="store_true",
                        help="headless smoke test: start services, run a text request, exit")
    parser.add_argument("--text", default="", help="text to process in --smoke mode")
    parser.add_argument("--no-listen", action="store_true", help="start without always-on listening")
    args = parser.parse_args(argv)

    load_dotenv()
    cfg = load_config()
    if args.no_listen:
        cfg.system.listen_on_start = False
        cfg.wake.enabled = False
    setup_logging()

    from .orchestrator import AssistantCore

    if args.check:
        print(_environment_report(cfg))
        return 0

    core = AssistantCore(cfg)

    if args.smoke:
        import time

        received: list[tuple[str, str]] = []
        core.callbacks["message"] = lambda role, text, ts: received.append((role, text))
        states: list[str] = []
        core.callbacks["state"] = lambda new, old, reason: states.append(new)
        core.start()
        text = args.text or "ساعت چنده"
        print(f"[smoke] submitting: {text}")
        core.submit_text(text)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if any(role == "assistant" for role, _ in received):
                break
            time.sleep(0.3)
        time.sleep(1.0)
        core.shutdown()
        print("[smoke] states:", " -> ".join(states))
        for role, text in received:
            print(f"[smoke] {role}: {text}")
        ok = any(role == "assistant" for role, _ in received)
        print("[smoke]", "PASS" if ok else "FAIL")
        return 0 if ok else 1

    from .ui.main import run_ui

    return run_ui(core, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
