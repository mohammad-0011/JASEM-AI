import pytest

from jasem.hotkeys import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, parse_hotkey


def test_ctrl_alt_letter():
    assert parse_hotkey("ctrl+alt+j") == (MOD_CONTROL | MOD_ALT, ord("J"))


def test_case_insensitive():
    assert parse_hotkey("CTRL+ALT+M") == (MOD_CONTROL | MOD_ALT, ord("M"))


def test_dash_separated():
    assert parse_hotkey("alt-shift-f5") == (MOD_ALT | MOD_SHIFT, 0x74)


def test_digit_key():
    mods, vk = parse_hotkey("win+9")
    assert mods == MOD_WIN and vk == 0x39


def test_invalid_returns_none():
    assert parse_hotkey("ctrl+alt+") is None
    assert parse_hotkey("ctrl+alt+unknownkey") is None
    assert parse_hotkey("") is None
    assert parse_hotkey("j") is None  # a bare key without modifiers is refused
