"""Automation permission policy.

Three action classes:

- routine       → executed without asking (after the user enabled automation)
- consequential → executed after an explicit confirmation
- high_risk     → executed only after an explicit confirmation that explains
                  the consequences

The user can override any classification in settings. Raw model text is never
executed directly — actions must be structured and schema-validated first.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from ..config import AutomationConfig


class Category(enum.Enum):
    ROUTINE = "routine"
    CONSEQUENTIAL = "consequential"
    HIGH_RISK = "high_risk"
    DENIED = "denied"


DEFAULT_CATEGORIES: dict[str, Category] = {
    "open_app": Category.ROUTINE,
    "open_browser": Category.ROUTINE,
    "open_url": Category.ROUTINE,
    "open_path": Category.ROUTINE,
    "system_info": Category.ROUTINE,
    "disk_space": Category.ROUTINE,
    "battery": Category.ROUTINE,
    "network_check": Category.ROUTINE,
    "list_processes": Category.ROUTINE,
    "volume_set": Category.ROUTINE,
    "volume_mute": Category.ROUTINE,
    "calculate": Category.ROUTINE,
    "web_search": Category.ROUTINE,
    "time_now": Category.ROUTINE,
    "find_file": Category.ROUTINE,
    "read_file": Category.ROUTINE,
    "create_note": Category.ROUTINE,
    "reminder": Category.ROUTINE,
    "move_file": Category.CONSEQUENTIAL,
    "copy_file": Category.CONSEQUENTIAL,
    "rename_file": Category.CONSEQUENTIAL,
    "end_process": Category.CONSEQUENTIAL,
    "delete_file": Category.HIGH_RISK,
    "delete_many": Category.HIGH_RISK,
    "run_command": Category.HIGH_RISK,
}


@dataclass
class Decision:
    category: Category
    allowed: bool
    needs_confirmation: bool
    reason: str = ""


class Policy:
    def __init__(self, cfg: AutomationConfig) -> None:
        self.cfg = cfg

    def classify(self, action_name: str) -> Category:
        override = self.cfg.permissions.get(action_name)
        if override == "allow":
            return Category.ROUTINE
        if override == "confirm":
            return Category.CONSEQUENTIAL
        if override == "deny":
            return Category.DENIED
        return DEFAULT_CATEGORIES.get(action_name,
                                      Category.CONSEQUENTIAL if self.cfg.confirm_unknown else Category.ROUTINE)

    def evaluate(self, action_name: str) -> Decision:
        if not self.cfg.enabled:
            return Decision(Category.DENIED, False, False, "automation disabled by user")
        cat = self.classify(action_name)
        if cat == Category.DENIED:
            return Decision(cat, False, False, f"action '{action_name}' is not permitted")
        if cat == Category.ROUTINE:
            return Decision(cat, True, False, "routine action")
        return Decision(cat, True, True, f"{cat.value} action requires confirmation")
