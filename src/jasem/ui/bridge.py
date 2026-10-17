"""Qt bridge: exposes AssistantCore to QML through signals/slots.

The orchestrator's callbacks arrive from audio/worker threads; Qt queued
connections marshal them onto the GUI thread safely.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from ..config import AppConfig, save_config
from ..orchestrator import AssistantCore

log = logging.getLogger("jasem.ui.bridge")


class AppBridge(QObject):
    stateChanged = Signal(str, str, str)          # new, old, reason
    messageAdded = Signal(str, str, float)        # role, text, ts
    micLevel = Signal(float)
    playLevel = Signal(float)
    statusChanged = Signal(str, bool, str)        # service, ok, detail
    confirmationRequested = Signal(str)
    notification = Signal(str)
    wakeDetected = Signal(str)
    confirmationVisible = Signal(bool)

    def __init__(self, core: AssistantCore, cfg: AppConfig) -> None:
        super().__init__()
        self.core = core
        self.cfg = cfg
        core.callbacks.update({
            "state": self._cb_state,
            "message": self._cb_message,
            "mic_level": self.micLevel.emit,
            "play_level": self.playLevel.emit,
            "status": self._cb_status,
            "confirmation": self._cb_confirmation,
            "notification": self.notification.emit,
            "wake": self.wakeDetected.emit,
            "speech_start": lambda: None,
            "speech_end": lambda: None,
        })

    # -- callbacks (worker threads) ------------------------------------------
    def _cb_state(self, new: str, old: str, reason: str) -> None:
        self.stateChanged.emit(new, old, reason)

    def _cb_message(self, role: str, text: str, ts: float) -> None:
        self.messageAdded.emit(role, text, ts)

    def _cb_status(self, service: str, ok: bool, detail: str) -> None:
        self.statusChanged.emit(service, ok, detail)

    def _cb_confirmation(self, text: str) -> None:
        self.confirmationRequested.emit(text)
        self.confirmationVisible.emit(True)

    # -- slots (GUI thread) ---------------------------------------------------
    @Slot(str)
    def submitText(self, text: str) -> None:
        self.core.submit_text(text)

    @Slot()
    def toggleMic(self) -> None:
        muted = self.core.toggle_mute()
        self.statusChanged.emit("mic", not muted,
                                "بی‌صدا — جاسم گوش نمی‌ده" if muted else "متصل")

    @Slot()
    def stopSpeaking(self) -> None:
        self.core.stop_speaking()

    @Slot()
    def pushToTalk(self) -> None:
        self.core.push_to_talk()

    @Slot(bool)
    def confirmAction(self, approved: bool) -> None:
        self.confirmationVisible.emit(False)
        self.core.confirm_pending(approved)

    @Slot()
    def repeatLast(self) -> None:
        self.core.repeat_last()

    @Slot()
    def clearHistory(self) -> None:
        self.core.clear_history()

    @Slot()
    def emergencyStop(self) -> None:
        self.core.emergency_stop()

    @Slot(result="QVariantMap")
    def snapshot(self) -> dict[str, Any]:
        return self.core.snapshot()

    @Slot(str, "QVariant")
    def setSetting(self, key: str, value: Any) -> None:
        """Hot-applies a setting, e.g. 'tts.edge_voice', 'wake.enabled'."""
        try:
            section, _, name = key.partition(".")
            section_obj = getattr(self.cfg, section, None)
            if section_obj is None or not hasattr(section_obj, name):
                log.warning("unknown setting %s", key)
                return
            current = getattr(section_obj, name)
            if isinstance(current, bool):
                value = bool(value)
            elif isinstance(current, int) and not isinstance(current, bool):
                value = int(value)
            elif isinstance(current, float):
                value = float(value)
            setattr(section_obj, name, value)
            save_config(self.cfg)
        except Exception:
            log.exception("failed to apply setting %s", key)
            return
        self._hot_apply(key, value)

    def _hot_apply(self, key: str, value: Any) -> None:
        if key == "tts.engine":
            self.core.set_tts_engine(str(value))
        elif key == "personality.sarcasm" or key == "personality.humor" \
                or key == "personality.formality" or key == "personality.warmth" \
                or key == "personality.response_length":
            from ..ai.prompts import build_system_prompt

            self.core.system_prompt = build_system_prompt(self.cfg.personality)
        elif key == "wake.enabled":
            self.core.set_wake_enabled(bool(value))
        elif key == "ai.memory_enabled":
            self.core.conversation.set_memory_enabled(bool(value))
        elif key == "system.autostart":
            from ..system import set_autostart

            ok = set_autostart(bool(value))
            self.cfg.system.autostart = ok and bool(value)
            save_config(self.cfg)
            self.notification.emit(
                "اجرا با روشن شدن ویندوز فعال شد." if self.cfg.system.autostart
                else "اجرا با روشن شدن ویندوز غیرفعال شد.")

    @Slot(str)
    def forgetMemory(self) -> None:
        self.core.conversation.forget_all()
        self.notification.emit("حافظهٔ بلندمدت پاک شد.")
