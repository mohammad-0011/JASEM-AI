"""Streaming PCM playback with prompt interruption.

Synthesis and playback are decoupled through a bounded queue: TTS engines push
PCM chunks, a dedicated thread owns the output stream, and ``interrupt()`` is
safe to call from any thread (UI button, wake-word barge-in, hotkey).
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Iterable, Iterator

import numpy as np
import sounddevice as sd

log = logging.getLogger("jasem.audio.playback")

_SENTINEL = object()


class AudioPlayer:
    def __init__(self, device: int | None = None) -> None:
        self.device = device
        self._queue: queue.Queue = queue.Queue(maxsize=64)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._playing = threading.Event()
        self._current_rate: int | None = None
        self._stream: sd.OutputStream | None = None
        self._generation = 0
        self.on_play_start: Callable[[], None] | None = None
        self.on_play_stop: Callable[[bool], None] | None = None  # interrupted flag
        self.on_level: Callable[[float], None] | None = None

    # -- state --------------------------------------------------------------
    @property
    def is_playing(self) -> bool:
        return self._playing.is_set()

    @property
    def generation(self) -> int:
        """Capture this before submitting a response; interrupt() invalidates it."""
        return self._generation

    # -- control --------------------------------------------------------------
    def submit(self, chunks: Iterable[np.ndarray] | Iterator[np.ndarray], sample_rate: int,
               generation: int | None = None) -> None:
        """Queue an audio stream for playback. Returns immediately."""
        gen = self._generation if generation is None else generation
        self._ensure_thread()
        self._queue.put(("stream", chunks, sample_rate, gen))

    def interrupt(self) -> None:
        """Drop everything queued and stop the current stream immediately."""
        self._generation += 1
        self._drain()
        if self._stream is not None:
            try:
                self._stream.abort()
            except Exception:
                pass
        log.debug("playback interrupted (gen=%d)", self._generation)

    def close(self) -> None:
        self.interrupt()
        self._stop_event.set()
        self._queue.put_nowait(_SENTINEL)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    def _ensure_thread(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="jasem-playback", daemon=True)
            self._thread.start()

    # -- worker ----------------------------------------------------------------
    def _run(self) -> None:
        while not self._stop_event.is_set():
            item = self._queue.get()
            if item is _SENTINEL:
                break
            _, chunks, rate, gen = item
            if gen != self._generation:
                continue  # superseded by an interrupt
            started = False
            try:
                with sd.OutputStream(
                    device=self.device, channels=1, samplerate=rate, dtype="float32",
                    blocksize=0,
                ) as stream:
                    self._stream = stream
                    for chunk in chunks:
                        if gen != self._generation or self._stop_event.is_set():
                            break
                        arr = np.asarray(chunk, dtype=np.float32)
                        if arr.ndim > 1:
                            arr = arr[:, 0]
                        if arr.size == 0:
                            continue
                        if not started:
                            started = True
                            self._playing.set()
                            if self.on_play_start:
                                try: self.on_play_start()
                                except Exception: log.exception("on_play_start failed")
                        stream.write(arr)
                        if self.on_level:
                            try:
                                self.on_level(min(1.0, float(np.sqrt(np.mean(arr ** 2))) * 4.0))
                            except Exception:
                                pass
            except Exception:
                log.exception("playback failed")
            finally:
                self._stream = None
                was_playing = self._playing.is_set()
                self._playing.clear()
                if started and was_playing and self.on_play_stop:
                    try:
                        self.on_play_stop(gen != self._generation)
                    except Exception:
                        log.exception("on_play_stop failed")


def synthesize_to_stream(engine, text_chunks: list[str]) -> tuple[Iterator[np.ndarray], int]:
    """Helper: pre-synthesize sentence chunks into one PCM iterator."""
    rate = engine.sample_rate

    def gen() -> Iterator[np.ndarray]:
        for sentence in text_chunks:
            try:
                yield from engine.synthesize(sentence)
            except Exception:
                log.exception("synthesis failed for a chunk")

    return gen(), rate


def chime(frequency: float = 880.0, duration_s: float = 0.18, rate: int = 24000) -> np.ndarray:
    t = np.linspace(0, duration_s, int(rate * duration_s), endpoint=False)
    wave = 0.25 * np.sin(2 * np.pi * frequency * t) * np.exp(-t * 6)
    return wave.astype(np.float32)
