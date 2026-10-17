"""Downloads every model JASEM needs (idempotent, resumable-ish).

- Vosk Persian + English wake models  (~71 MB)
- Piper Persian voices amir + gyro    (~127 MB)
- Whisper small via faster-whisper    (~460 MB, cached by huggingface-hub)
"""

from __future__ import annotations

import os
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"

VOSK_URLS = [
    "https://alphacephei.com/vosk/models/vosk-model-small-fa-0.42.zip",
    "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
]
PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/fa/fa_IR"
PIPER_VOICES = ["amir", "gyro"]


def download(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  exists: {dest.name}")
        return
    print(f"  downloading: {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(dest)


def main() -> int:
    vosk_dir = MODELS / "vosk"
    piper_dir = MODELS / "piper"
    vosk_dir.mkdir(parents=True, exist_ok=True)
    piper_dir.mkdir(parents=True, exist_ok=True)

    print("Vosk wake-word models:")
    for url in VOSK_URLS:
        name = url.rsplit("/", 1)[-1]
        zip_path = vosk_dir / name
        model_dir = vosk_dir / name[:-4]
        if model_dir.exists():
            print(f"  exists: {name[:-4]}")
            continue
        download(url, zip_path)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(vosk_dir)
        zip_path.unlink()

    print("Piper Persian voices:")
    for voice in PIPER_VOICES:
        for ext in (".onnx", ".onnx.json"):
            fn = f"fa_IR-{voice}-medium{ext}"
            download(f"{PIPER_BASE}/{voice}/medium/{fn}", piper_dir / fn)

    print("Whisper model (via faster-whisper):")
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    try:
        from faster_whisper import WhisperModel

        WhisperModel("small", device="cpu", compute_type="int8")
        print("  whisper small cached")
    except Exception as exc:
        print(f"  whisper download failed: {exc}")
        return 1

    print("All models ready.")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("no_proxy", "*")
    raise SystemExit(main())
