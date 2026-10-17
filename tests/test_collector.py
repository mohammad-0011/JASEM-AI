import numpy as np

from jasem.stt.pipeline import UtteranceCollector


class FakeVad:
    """Amplitude-threshold VAD for deterministic synthetic tests."""

    frame_ms = 30

    def __init__(self, threshold=1000):
        self.threshold = threshold

    def is_speech(self, frame):
        return float(np.max(np.abs(frame))) > self.threshold


def frame(speech: bool) -> np.ndarray:
    if speech:
        rng = np.random.default_rng(7)
        return (rng.integers(-8000, 8000, 480)).astype(np.int16)
    return np.zeros(480, dtype=np.int16)


def collect(utterances, speech_n, silence_n, gap_at=None, gap_len=0):
    c = UtteranceCollector(
        FakeVad(), on_utterance=lambda a, m: utterances.append((a, m)),
        speech_min_ms=120, silence_end_ms=240, max_utterance_s=10,
    )
    c.set_armed(True)
    for i in range(speech_n):
        c.feed(frame(True))
        if gap_at is not None and i == gap_at:
            for _ in range(gap_len):
                c.feed(frame(False))
    for _ in range(silence_n):
        c.feed(frame(False))


def test_single_utterance_collected():
    out = []
    collect(out, speech_n=20, silence_n=30)
    assert len(out) == 1
    audio, meta = out[0]
    assert meta["duration_s"] > 0.5
    assert not meta["forced"]


def test_short_noise_burst_rejected():
    out = []
    collect(out, speech_n=2, silence_n=30)  # 60 ms < speech_min_ms=120
    assert out == []


def test_mid_pause_does_not_split():
    out = []
    # pause of 90 ms (< silence_end_ms=240) inside the sentence
    collect(out, speech_n=30, silence_n=30, gap_at=10, gap_len=3)
    assert len(out) == 1


def test_long_pause_splits():
    out = []
    c = UtteranceCollector(
        FakeVad(), on_utterance=lambda a, m: out.append((a, m)),
        speech_min_ms=120, silence_end_ms=240, max_utterance_s=10,
    )
    c.set_armed(True)
    for _ in range(15):
        c.feed(frame(True))
    for _ in range(12):  # 360 ms silence -> ends first utterance
        c.feed(frame(False))
    for _ in range(15):
        c.feed(frame(True))
    for _ in range(12):
        c.feed(frame(False))
    assert len(out) == 2


def test_disarmed_collector_ignores_audio():
    out = []
    c = UtteranceCollector(FakeVad(), on_utterance=lambda a, m: out.append(a))
    c.set_armed(False)
    for _ in range(40):
        c.feed(frame(True))
    assert out == []
    c.set_armed(True)
    for _ in range(40):
        c.feed(frame(True))
    for _ in range(30):
        c.feed(frame(False))
    assert len(out) == 1


def test_max_utterance_forces_cut():
    out = []
    c = UtteranceCollector(
        FakeVad(), on_utterance=lambda a, m: out.append((a, m)),
        speech_min_ms=120, silence_end_ms=240, max_utterance_s=0.5,
    )
    c.set_armed(True)
    for _ in range(30):  # 900 ms of continuous speech > 0.5 s cap
        c.feed(frame(True))
    assert len(out) == 1 and out[0][1]["forced"] is True
