"""Configurable speech-recognition evaluation suite.

Usage (from the project root, inside the venv):

    python eval/evaluate_stt.py --synth piper          # offline, uses Piper voices
    python eval/evaluate_stt.py --synth edge           # online (Azure neural voices)
    python eval/evaluate_stt.py --engines faster-whisper vosk
    python eval/evaluate_stt.py --rebuild-audio

Audio files are cached in eval/audio/*.wav so alternative engines can be
compared on exactly the same samples. Reference text is eval/corpus/fa_eval.jsonl.
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from eval.wer import aggregate  # noqa: E402

CORPUS = ROOT / "eval" / "corpus" / "fa_eval.jsonl"
AUDIO_DIR = ROOT / "eval" / "audio"


def load_corpus() -> list[dict]:
    items = []
    for line in CORPUS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            items.append(json.loads(line))
    return items


def synth_piper(text: str, out_path: Path) -> None:
    import numpy as np

    from jasem.config import TTSConfig
    from jasem.tts.piper_engine import PiperTTSEngine

    engine = PiperTTSEngine(TTSConfig())
    chunks = list(engine.synthesize(text))
    audio = np.concatenate(chunks) if chunks else np.zeros(1, dtype="float32")
    pcm = (np.clip(audio, -1, 1) * 32767).astype("int16").tobytes()
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(engine.sample_rate)
        w.writeframes(pcm)


def synth_edge(text: str, out_path: Path) -> None:
    import asyncio

    import edge_tts

    async def run():
        c = edge_tts.Communicate(text, voice="fa-IR-DilaraNeural")
        buf = bytearray()
        async for chunk in c.stream():
            if chunk["type"] == "audio":
                buf.extend(chunk["data"])
        out_path.write_bytes(bytes(buf))  # mp3

    asyncio.run(run())


def read_audio(path: Path):
    import numpy as np

    if path.suffix == ".mp3":
        import av, io

        with av.open(io.BytesIO(path.read_bytes())) as container:
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
            frames = []
            for frame in container.decode(container.streams.audio[0]):
                for f in resampler.resample(frame):
                    frames.append(f.to_ndarray()[0])
            return np.concatenate(frames).astype("float32")
    with wave.open(str(path), "rb") as w:
        assert w.getsampwidth() == 2 and w.getnchannels() == 1
        rate = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="int16").astype("float32") / 32768.0
    if rate != 16000:
        n = int(len(data) * 16000 / rate)
        data = np.interp(np.linspace(0, len(data) - 1, n), np.arange(len(data)), data).astype("float32")
    return data


class WhisperRunner:
    name = "faster-whisper-small"

    def __init__(self):
        from jasem.config import STTConfig
        from jasem.stt.faster_whisper_engine import FasterWhisperEngine

        self.engine = FasterWhisperEngine(STTConfig(model_size="small"))

    def run(self, audio) -> str:
        return self.engine.transcribe(audio, 16000).text


class VoskRunner:
    name = "vosk-small-fa"

    def __init__(self):
        import vosk

        vosk.SetLogLevel(-1)
        model_dir = ROOT / "models" / "vosk" / "vosk-model-small-fa-0.42"
        self.model = vosk.Model(str(model_dir))

    def run(self, audio) -> str:
        import json as _json
        import vosk

        rec = vosk.KaldiRecognizer(self.model, 16000)
        pcm = (audio * 32767).astype("int16").tobytes()
        text = []
        for i in range(0, len(pcm), 4800):
            if rec.AcceptWaveform(pcm[i:i + 4800]):
                text.append(_json.loads(rec.Result()).get("text", ""))
        text.append(_json.loads(rec.FinalResult()).get("text", ""))
        return " ".join(t for t in text if t)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--synth", choices=["piper", "edge"], default="piper")
    ap.add_argument("--engines", nargs="+", default=["faster-whisper", "vosk"])
    ap.add_argument("--rebuild-audio", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "eval" / "report.json"))
    args = ap.parse_args()

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    corpus = load_corpus()
    print(f"corpus: {len(corpus)} sentences, synth={args.synth}")

    for item in corpus:
        wav = AUDIO_DIR / f"{item['id']}.wav"
        mp3 = AUDIO_DIR / f"{item['id']}.mp3"
        if args.rebuild_audio:
            wav.unlink(missing_ok=True); mp3.unlink(missing_ok=True)
        if not wav.exists() and not mp3.exists():
            print(f"synthesizing {item['id']} …", flush=True)
            try:
                if args.synth == "piper":
                    synth_piper(item["text"], wav)
                else:
                    synth_edge(item["text"], mp3)
            except Exception as exc:
                print(f"  synthesis failed: {exc}")
                continue

    runners = []
    for name in args.engines:
        try:
            runners.append(WhisperRunner() if name.startswith("faster") else VoskRunner())
        except Exception as exc:
            print(f"engine {name} unavailable: {exc}")

    report = {"synth": args.synth, "corpus_size": len(corpus), "engines": {}}
    for runner in runners:
        pairs = []
        for item in corpus:
            wav = AUDIO_DIR / f"{item['id']}.wav"
            mp3 = AUDIO_DIR / f"{item['id']}.mp3"
            path = wav if wav.exists() else (mp3 if mp3.exists() else None)
            if path is None:
                continue
            audio = read_audio(path)
            hyp = runner.run(audio)
            pairs.append((item["text"], hyp))
        stats = aggregate(pairs)
        report["engines"][runner.name] = stats
        print(f"{runner.name:<22} WER={stats['wer']:.3f}  CER={stats['cer']:.3f}  n={stats['items']}")

    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
