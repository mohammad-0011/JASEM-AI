"""OpenAI-compatible chat provider (OpenAI, OpenRouter, Groq, LM Studio,
Ollama, vLLM...). Streaming is used so the first sentence can be spoken while
the rest of the answer is still being generated."""

from __future__ import annotations

import json
import logging
import os
from typing import Iterator

import httpx

from ..config import AIConfig

log = logging.getLogger("jasem.ai.openai")


class ProviderError(RuntimeError):
    pass


class OpenAIProvider:
    name = "openai-compatible"

    def __init__(self, cfg: AIConfig) -> None:
        self.cfg = cfg
        self._api_key = os.environ.get(cfg.api_key_env, "")

    @property
    def available(self) -> bool:
        # Local endpoints (LM Studio / Ollama / vLLM) usually need no key.
        local_hint = any(h in self.cfg.base_url for h in ("127.0.0.1", "localhost"))
        return bool(self._api_key) or local_hint

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _payload(self, messages: list[dict], stream: bool) -> dict:
        return {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": self.cfg.temperature,
            "max_tokens": self.cfg.max_tokens,
            "stream": stream,
        }

    def chat_stream(self, messages: list[dict]) -> Iterator[str]:
        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        try:
            with httpx.Client(timeout=httpx.Timeout(self.cfg.timeout_s, connect=10.0)) as client:
                with client.stream(
                    "POST", url, headers=self._headers(),
                    json=self._payload(messages, stream=True),
                ) as resp:
                    if resp.status_code != 200:
                        body = resp.read()[:400].decode("utf-8", "replace")
                        raise ProviderError(f"HTTP {resp.status_code}: {body}")
                    for line in resp.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        delta = obj.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content
        except httpx.HTTPError as exc:
            raise ProviderError(f"network error: {exc}") from exc

    def chat(self, messages: list[dict]) -> str:
        return "".join(self.chat_stream(messages))
