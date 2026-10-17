from jasem.automation.policy import Category, Policy
from jasem.config import AutomationConfig


def test_routine_actions_run_without_confirmation():
    p = Policy(AutomationConfig())
    d = p.evaluate("open_app")
    assert d.allowed and not d.needs_confirmation


def test_consequential_requires_confirmation():
    p = Policy(AutomationConfig())
    d = p.evaluate("end_process")
    assert d.allowed and d.needs_confirmation


def test_high_risk_requires_confirmation():
    p = Policy(AutomationConfig())
    d = p.evaluate("delete_file")
    assert d.needs_confirmation and d.category == Category.HIGH_RISK


def test_unknown_action_default_confirms():
    p = Policy(AutomationConfig())
    d = p.evaluate("something_new")
    assert d.needs_confirmation


def test_user_override_allow():
    p = Policy(AutomationConfig(permissions={"end_process": "allow"}))
    d = p.evaluate("end_process")
    assert not d.needs_confirmation


def test_user_override_deny():
    p = Policy(AutomationConfig(permissions={"open_app": "deny"}))
    d = p.evaluate("open_app")
    assert not d.allowed


def test_automation_disabled_blocks_everything():
    p = Policy(AutomationConfig(enabled=False))
    d = p.evaluate("open_app")
    assert not d.allowed
