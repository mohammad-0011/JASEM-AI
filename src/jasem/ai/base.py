"""Language-model provider interface."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator, Protocol, runtime_checkable

_ACTION_RE = re.compile(r"\[\[ACTION:(\{.*?\})\]\]", re.DOTALL)


@dataclass
class ProviderResult:
    text: str                                   # reply without action blocks
    actions: list[dict] = field(default_factory=list)
    error: str | None = None


def extract_actions(text: str) -> ProviderResult:
    """Split [[ACTION:{...}]] blocks out of a model response."""
    import json

    actions: list[dict] = []
    cleaned = text
    for m in _ACTION_RE.finditer(text):
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict) and "name" in obj:
                actions.append({"name": obj["name"], "args": obj.get("args") or {}})
        except (json.JSONDecodeError, TypeError):
            continue
    cleaned = _ACTION_RE.sub("", text).strip()
    return ProviderResult(text=cleaned, actions=actions)


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    available: bool

    def chat_stream(self, messages: list[dict]) -> Iterator[str]:
        """Yield reply text deltas. May raise; callers handle errors."""
        ...

    def chat(self, messages: list[dict]) -> str:
        ...
