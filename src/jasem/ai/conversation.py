"""Conversation history + optional user-controlled persistent memory."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime

from .. import paths
from ..config import ConversationConfig

log = logging.getLogger("jasem.ai.conversation")


@dataclass
class Turn:
    role: str          # user | assistant | system
    text: str
    ts: float = field(default_factory=lambda: time_now())


def time_now() -> float:
    return datetime.now().timestamp()


class Conversation:
    def __init__(self, cfg: ConversationConfig) -> None:
        self.cfg = cfg
        self._lock = threading.RLock()
        self._turns: list[Turn] = []
        self._memory: dict = {"facts": []}
        self._load()

    # -- history ----------------------------------------------------------
    def add(self, role: str, text: str) -> None:
        with self._lock:
            self._turns.append(Turn(role=role, text=text))
            max_turns = self.cfg.history_max_turns * 2
            if len(self._turns) > max_turns:
                self._turns = self._turns[-max_turns:]
        if self.cfg.persist_history:
            self._save_history()

    def messages_for_prompt(self, system_prompt: str, max_turns: int | None = None) -> list[dict]:
        with self._lock:
            turns = list(self._turns)
        n = max_turns or self.cfg.history_max_turns
        recent = turns[-n:]
        msgs = [{"role": "system", "content": system_prompt}]
        if self._memory.get("facts") and self.memory_enabled:
            facts = "؛ ".join(self._memory["facts"][-8:])
            msgs.append({"role": "system", "content": f"اطلاعاتی که کاربر قبلاً گفته: {facts}"})
        for t in recent:
            if t.role in ("user", "assistant") and t.text.strip():
                msgs.append({"role": t.role, "content": t.text})
        return msgs

    _memory_enabled: bool = False

    @property
    def memory_enabled(self) -> bool:
        return self._memory_enabled or bool(getattr(self.cfg, "memory_enabled", False))

    def set_memory_enabled(self, enabled: bool) -> None:
        self._memory_enabled = enabled

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()
        if self.cfg.persist_history:
            self._save_history()

    def last_assistant_text(self) -> str:
        with self._lock:
            for t in reversed(self._turns):
                if t.role == "assistant":
                    return t.text
        return ""

    # -- persistent memory -------------------------------------------------
    def remember(self, fact: str) -> None:
        fact = fact.strip()
        if not fact or not self.memory_enabled:
            return
        with self._lock:
            if fact not in self._memory["facts"]:
                self._memory["facts"].append(fact)
                self._memory["facts"] = self._memory["facts"][-50:]
        self._save_memory()

    def forget_all(self) -> None:
        with self._lock:
            self._memory = {"facts": []}
        self._save_memory()

    def _save_memory(self) -> None:
        try:
            paths.memory_path().write_text(
                json.dumps(self._memory, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            log.exception("failed to save memory")

    def _load(self) -> None:
        try:
            if self.cfg.persist_history and paths.history_path().exists():
                data = json.loads(paths.history_path().read_text(encoding="utf-8"))
                self._turns = [Turn(t["role"], t["text"], t.get("ts", time_now())) for t in data[-100:]]
        except Exception:
            log.warning("history file unreadable; starting fresh", exc_info=True)
        try:
            if paths.memory_path().exists():
                self._memory = json.loads(paths.memory_path().read_text(encoding="utf-8"))
                self._memory.setdefault("facts", [])
        except Exception:
            log.warning("memory file unreadable; starting fresh", exc_info=True)

    def _save_history(self) -> None:
        try:
            with self._lock:
                data = [{"role": t.role, "text": t.text, "ts": t.ts} for t in self._turns]
            paths.history_path().write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            log.exception("failed to save history")
