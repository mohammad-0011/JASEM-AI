"""Integration tests that exercise real engines and (partly) the network.

They skip themselves gracefully when a model or the network is missing, so the
unit suite stays green offline; run them directly to get real measurements.
"""

import time

import numpy as np
import pytest

from jasem.config import STTConfig, TTSConfig


# ---------------------------------------------------------------- TTS
def test_piper_offline_synthesis():
    from jasem.tts.piper_engine import PiperTTSEngine

    engine = PiperTTSEngine(TTSConfig(), noise_scale=0.0, noise_w_scale=0.0)
    chunks = list(engine.synthesize("سلام، من جاسم هستم."))
    audio = np.concatenate(chunks)
    assert audio.size > 8000  # at least ~0.3 s of speech at 22 kHz
    assert float(np.max(np.abs(audio))) > 0.05


def test_edge_online_synthesis():
    import pytest as _pytest

    from jasem.tts.edge_engine import EdgeTTSError, EdgeTTSEngine

    engine = EdgeTTSEngine(TTSConfig())
    try:
        chunks = list(engine.synthesize("سلام جاسم، این یک آزمایش است."))
    except EdgeTTSError as exc:
        engine.close()
        _pytest.skip(f"edge-tts unreachable: {exc}")
    engine.close()
    audio = np.concatenate(chunks) if chunks else np.zeros(0)
    assert audio.size > 8000


# ---------------------------------------------------------------- STT
def test_stt_roundtrip_piper_to_whisper():
    pytest.importorskip("faster_whisper")
    from jasem.tts.piper_engine import PiperTTSEngine
    from jasem.stt.faster_whisper_engine import FasterWhisperEngine

    text = "سلام جاسم حالت چطوره"
    tts = PiperTTSEngine(TTSConfig(), noise_scale=0.0, noise_w_scale=0.0)
    audio = np.concatenate(list(tts.synthesize(text)))
    stt = FasterWhisperEngine(STTConfig(model_size="small"))
    tr = stt.transcribe(audio, tts.sample_rate)
    assert tr.text.strip()
    # Require the assistant's name to survive the round trip.
    assert "جاسم" in tr.text or "اسم" in tr.text
    assert tr.confidence > 0.0


def test_stt_empty_audio_returns_empty_transcript():
    from jasem.stt.faster_whisper_engine import FasterWhisperEngine

    stt = FasterWhisperEngine(STTConfig(model_size="tiny"))
    tr = stt.transcribe(np.zeros(16000, dtype=np.float32), 16000)
    assert isinstance(tr.text, str)


# ---------------------------------------------------------------- player
def test_playback_interrupt_stops_promptly():
    from jasem.audio.playback import AudioPlayer

    player = AudioPlayer()
    stopped = {}
    player.on_play_stop = lambda interrupted: stopped.update(interrupted=interrupted)

    def slow_chunks():
        tone = (0.2 * np.sin(2 * np.pi * 440 * np.arange(4800) / 48000)).astype("float32")
        for _ in range(200):  # ~20 s of audio; must be cut much earlier
            yield tone

    t0 = time.perf_counter()
    player.submit(slow_chunks(), 48000)
    while not player.is_playing and time.perf_counter() - t0 < 3:
        time.sleep(0.02)
    assert player.is_playing, "playback never started"
    time.sleep(0.3)
    player.interrupt()
    deadline = time.perf_counter() + 1.5
    while player.is_playing and time.perf_counter() < deadline:
        time.sleep(0.02)
    elapsed = time.perf_counter() - t0
    assert not player.is_playing, "interrupt() did not stop playback"
    assert elapsed < 2.0
    player.close()


def test_interrupt_discards_queued_generation():
    from jasem.audio.playback import AudioPlayer

    player = AudioPlayer()

    def chunks():
        tone = (0.1 * np.sin(2 * np.pi * 300 * np.arange(2400) / 24000)).astype("float32")
        for _ in range(500):
            yield tone

    player.submit(chunks(), 24000)
    time.sleep(0.2)
    player.interrupt()          # invalidates the queued stream
    played_after = []
    new_gen = player.generation

    def fresh():
        tone = (0.1 * np.sin(2 * np.pi * 900 * np.arange(2400) / 24000)).astype("float32")
        for _ in range(3):
            yield tone

    player.submit(fresh(), 24000, generation=new_gen)
    time.sleep(0.4)
    assert player.generation == new_gen
    player.close()


# ---------------------------------------------------------------- wake word
def test_vosk_detects_persian_wake_phrase():
    pytest.importorskip("vosk")
    from jasem.config import resolve_wake_model_dirs, AppConfig
    from jasem.tts.piper_engine import PiperTTSEngine
    from jasem.wake.phrases import PhraseMatcher
    from jasem.wake.vosk_detector import VoskWakeDetector

    cfg = AppConfig()
    fa_dir, en_dir = resolve_wake_model_dirs(cfg)
    if not fa_dir.exists():
        pytest.skip("vosk fa model missing")

    # Zero noise → deterministic synthesis: the VITS noise seed is not
    # controllable per-process, and some realizations are inaudible to the
    # small vosk model, which made this test flaky.
    tts = PiperTTSEngine(TTSConfig(), noise_scale=0.0, noise_w_scale=0.0)
    audio = np.concatenate(list(tts.synthesize("هی جاسم")))
    lead = np.zeros(int(0.3 * tts.sample_rate), dtype="float32")
    audio = np.concatenate([lead, audio, lead])
    # resample 22050 -> 16000
    n = int(len(audio) * 16000 / tts.sample_rate)
    audio16 = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio)
    pcm = (np.clip(audio16, -1, 1) * 32767).astype("int16")

    matcher = PhraseMatcher(cfg.wake.phrases, cfg.wake.stop_phrases, cooldown_ms=0)
    det = VoskWakeDetector(str(fa_dir), None, matcher, energy_threshold=0.005)
    hits = []
    texts = []
    det.on_match = hits.append
    det.on_transcript = lambda t, s: texts.append(f"{s}:{t}")
    det.start()
    for i in range(0, len(pcm), 480):
        det.feed(pcm[i:i + 480])
        time.sleep(0.001)
    det.stop()
    import hashlib
    pcm_hash = hashlib.sha1(pcm.tobytes()).hexdigest()[:10]
    assert hits, f"wake phrase not detected; pcm={pcm_hash} transcripts={texts}"
    assert hits[0].phrase in cfg.wake.phrases
