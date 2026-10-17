"""Microphone capture with fan-out, level metering and device-loss recovery."""

from __future__ import annotations

import logging
import threading
from typing import Callable

import numpy as np
import sounddevice as sd

log = logging.getLogger("jasem.audio.capture")

FrameCallback = Callable[[np.ndarray], None]   # int16 mono frame
LevelCallback = Callable[[float], None]        # 0..1 RMS


class MicStream:
    """Owns the single input stream feeding wake-word, VAD and STT layers."""

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_ms: int = 30,
        device: int | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.device = device
        self._frame_samples = sample_rate * frame_ms // 1000
        self._subscribers: list[FrameCallback] = []
        self._level_cb: LevelCallback | None = None
        self._lock = threading.RLock()
        self._stream: sd.InputStream | None = None
        self._running = False
        self._retry_timer: threading.Timer | None = None
        self.on_device_error: Callable[[str], None] | None = None
        self.on_device_restored: Callable[[], None] | None = None

    # -- subscription ------------------------------------------------------
    def subscribe(self, cb: FrameCallback) -> None:
        with self._lock:
            if cb not in self._subscribers:
                self._subscribers.append(cb)

    def unsubscribe(self, cb: FrameCallback) -> None:
        with self._lock:
            if cb in self._subscribers:
                self._subscribers.remove(cb)

    def set_level_callback(self, cb: LevelCallback | None) -> None:
        self._level_cb = cb

    # -- lifecycle ----------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._running and self._stream is not None and self._stream.active

    def start(self) -> bool:
        with self._lock:
            if self._stream is not None:
                return True
            try:
                self._stream = sd.InputStream(
                    device=self.device,
                    channels=1,
                    samplerate=self.sample_rate,
                    dtype="int16",
                    blocksize=self._frame_samples,
                    callback=self._callback,
                    finished_callback=self._finished,
                )
                self._stream.start()
                self._running = True
                log.info("mic stream started (device=%s, %d Hz)", self.device, self.sample_rate)
                return True
            except Exception as exc:
                self._stream = None
                self._running = False
                log.error("mic open failed: %s", exc)
                if self.on_device_error:
                    self.on_device_error(str(exc))
                self._schedule_retry()
                return False

    def stop(self) -> None:
        with self._lock:
            self._running = False
            if self._retry_timer is not None:
                self._retry_timer.cancel()
                self._retry_timer = None
            stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop(); stream.close()
            except Exception:
                pass

    def _schedule_retry(self, delay: float = 3.0) -> None:
        """Microphone unplugged: retry with backoff until it comes back."""
        with self._lock:
            if not self._running and self._retry_timer is None:
                self._retry_timer = threading.Timer(delay, self._retry)
                self._retry_timer.daemon = True
                self._retry_timer.start()

    def _retry(self) -> None:
        with self._lock:
            self._retry_timer = None
        if self.start() and self.on_device_restored:
            self.on_device_restored()

    # -- audio path -----------------------------------------------------------
    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            log.debug("stream status: %s", status)
        frame = np.asarray(indata[:, 0], dtype=np.int16)
        with self._lock:
            subs = list(self._subscribers)
            level_cb = self._level_cb
        if level_cb is not None:
            rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2))) / 32768.0
            try:
                level_cb(min(1.0, rms * 4.0))
            except Exception:
                log.exception("level callback failed")
        for cb in subs:
            try:
                cb(frame)
            except Exception:
                log.exception("frame subscriber failed")

    def _finished(self) -> None:
        log.warning("mic stream finished (device removed?)")


def list_input_devices() -> list[dict]:
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            out.append({"index": i, "name": d["name"], "channels": d["max_input_channels"]})
    return out


def list_output_devices() -> list[dict]:
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] > 0:
            out.append({"index": i, "name": d["name"], "channels": d["max_output_channels"]})
    return out
