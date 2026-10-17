"""Edge TTS engine — Azure neural Persian voices through Microsoft Edge's
online endpoint. Free (no API key), high quality, requires internet."""

from __future__ import annotations

import asyncio
import io
import logging
import threading
import time
from typing import Iterator

import av
import numpy as np

from ..config import TTSConfig

log = logging.getLogger("jasem.tts.edge")


class EdgeTTSError(RuntimeError):
    pass


class EdgeTTSEngine:
    name = "edge"
    online = True

    def __init__(self, cfg: TTSConfig) -> None:
        self.cfg = cfg
        self.sample_rate = 24000
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="edge-tts-loop", daemon=True)
        self._thread.start()

    # -- mp3 -> float32 mono -------------------------------------------------
    @staticmethod
    def _decode_mp3(data: bytes, rate: int) -> Iterator[np.ndarray]:
        with av.open(io.BytesIO(data)) as container:
            stream = container.streams.audio[0]
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=rate)
            for frame in container.decode(stream):
                frames = resampler.resample(frame)
                if not isinstance(frames, list):
                    frames = [frames]
                for f in frames:
                    arr = f.to_ndarray()
                    yield (arr[0] if arr.ndim > 1 else arr).astype(np.float32)

    # -- API ------------------------------------------------------------------
    async def _synthesize_coro(self, text: str) -> bytes:
        import edge_tts

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                communicate = edge_tts.Communicate(
                    text,
                    voice=self.cfg.edge_voice,
                    rate=self.cfg.edge_rate,
                    pitch=self.cfg.edge_pitch,
                )
                buf = bytearray()
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        buf.extend(chunk["data"])
                if buf:
                    return bytes(buf)
                last_exc = EdgeTTSError("empty audio returned")
            except Exception as exc:  # network hiccups / rate limits
                last_exc = exc
                log.warning("edge-tts attempt %d failed: %s", attempt + 1, exc)
                await asyncio.sleep(0.6 * (attempt + 1))
        raise EdgeTTSError(str(last_exc))

    def synthesize(self, text: str) -> Iterator[np.ndarray]:
        text = (text or "").strip()
        if not text:
            return
        future = asyncio.run_coroutine_threadsafe(self._synthesize_coro(text), self._loop)
        data = future.result(timeout=60)
        yield from self._decode_mp3(data, self.sample_rate)

    def warmup(self) -> None:
        t0 = time.perf_counter()
        try:
            for _ in self.synthesize("سلام"):
                pass
            log.info("edge-tts warmup ok in %.2fs", time.perf_counter() - t0)
        except Exception as exc:
            log.warning("edge-tts warmup failed: %s", exc)

    def close(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2.0)
