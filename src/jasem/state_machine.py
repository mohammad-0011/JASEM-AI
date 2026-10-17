"""Voice interaction state machine.

Explicit, validated transitions keep the audio pipeline predictable: exactly
one state owns the microphone at a time, and playback/interruption races are
resolved through the transition table rather than ad-hoc flags.
"""

from __future__ import annotations

import enum
import logging
import threading
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger("jasem.state")


class State(enum.Enum):
    IDLE = "idle"                      # initialized, nothing armed
    WAKE_MONITORING = "wake_monitoring"  # always-on wake word listening
    LISTENING = "listening"            # active conversation, collecting speech
    PROCESSING = "processing"          # transcribing / understanding
    GENERATING = "generating"          # LLM producing the answer
    SPEAKING = "speaking"              # TTS playback
    INTERRUPTED = "interrupted"        # playback cut short by the user
    CONFIRMING = "confirming"          # waiting for user confirmation
    ERROR = "error"
    SHUTDOWN = "shutdown"


ALLOWED: dict[State, set[State]] = {
    State.IDLE: {State.WAKE_MONITORING, State.LISTENING, State.ERROR, State.SHUTDOWN},
    State.WAKE_MONITORING: {State.LISTENING, State.IDLE, State.ERROR, State.SHUTDOWN},
    State.LISTENING: {State.PROCESSING, State.WAKE_MONITORING, State.IDLE, State.SPEAKING,
                      State.GENERATING, State.CONFIRMING, State.ERROR, State.SHUTDOWN},
    State.PROCESSING: {State.GENERATING, State.LISTENING, State.WAKE_MONITORING,
                       State.CONFIRMING, State.SPEAKING, State.ERROR, State.SHUTDOWN},
    State.GENERATING: {State.SPEAKING, State.LISTENING, State.WAKE_MONITORING,
                       State.INTERRUPTED, State.ERROR, State.SHUTDOWN},
    State.SPEAKING: {State.WAKE_MONITORING, State.LISTENING, State.INTERRUPTED,
                     State.PROCESSING, State.ERROR, State.SHUTDOWN},
    State.CONFIRMING: {State.PROCESSING, State.WAKE_MONITORING, State.LISTENING,
                       State.IDLE, State.ERROR, State.SHUTDOWN},
    State.INTERRUPTED: {State.WAKE_MONITORING, State.LISTENING, State.IDLE, State.ERROR,
                        State.SHUTDOWN},
    State.ERROR: {State.IDLE, State.WAKE_MONITORING, State.SHUTDOWN},
    State.SHUTDOWN: set(),
}


@dataclass
class Transition:
    old: State
    new: State
    reason: str = ""


class StateMachine:
    def __init__(self, on_transition: Callable[[Transition], None] | None = None) -> None:
        self._lock = threading.RLock()
        self._state = State.IDLE
        self._listeners: list[Callable[[Transition], None]] = []
        if on_transition:
            self._listeners.append(on_transition)

    @property
    def state(self) -> State:
        with self._lock:
            return self._state

    def add_listener(self, fn: Callable[[Transition], None]) -> None:
        self._listeners.append(fn)

    def can(self, target: State) -> bool:
        with self._lock:
            return target in ALLOWED[self._state]

    def transition(self, target: State, reason: str = "") -> bool:
        with self._lock:
            if target == self._state:
                return True
            if target not in ALLOWED[self._state]:
                log.warning("blocked transition %s -> %s (%s)", self._state.value, target.value, reason)
                return False
            old, self._state = self._state, target
        tr = Transition(old, target, reason)
        log.debug("state %s -> %s (%s)", old.value, target.value, reason)
        for fn in list(self._listeners):
            try:
                fn(tr)
            except Exception:
                log.exception("state listener failed")
        return True
