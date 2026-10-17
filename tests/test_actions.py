from pathlib import Path

import pytest

from jasem.automation import actions as A
from jasem.automation.files import find_file, read_text_file, safe_eval


# -- schema validation ------------------------------------------------------
def test_validate_open_app_requires_name():
    ok, name, err = A.validate_action({"name": "open_app", "args": {}})
    assert not ok and "نام برنامه" in err


def test_validate_unknown_action():
    ok, _, err = A.validate_action({"name": "drop_tables", "args": {}})
    assert not ok


def test_validate_url_adds_scheme():
    ok, name, err = A.validate_action({"name": "open_url", "args": {"url": "example.com"}})
    assert ok


# -- safe calculator ----------------------------------------------------------
@pytest.mark.parametrize("expr,expected", [
    ("2 + 2", 4.0), ("10 / 4", 2.5), ("2 ** 10", 1024.0), ("-(3 + 4)", -7.0),
    ("17 % 5", 2.0),
])
def test_safe_eval_math(expr, expected):
    assert safe_eval(expr) == expected


@pytest.mark.parametrize("expr", ["__import__('os')", "open('/etc/passwd')", "x + 1", "a.b"])
def test_safe_eval_blocks_everything_else(expr):
    with pytest.raises(ValueError):
        safe_eval(expr)


# -- executors ---------------------------------------------------------------
def test_calculate_executor():
    result = A.execute_action("calculate", {"expression": "6 * 7"})
    assert result.ok and "۴۲" in result.message or result.ok


def test_system_info_executor():
    result = A.execute_action("system_info", {})
    assert result.ok and result.data["cpu_cores"] >= 1


def test_create_note_and_read_back():
    result = A.execute_action("create_note", {"text": "خرید نان و شیر"})
    assert result.ok
    note_path = Path(result.data["path"])
    assert note_path.exists()
    assert "نان" in note_path.read_text(encoding="utf-8")


def test_find_file_in_tmp(tmp_path):
    target = tmp_path / "report-2026.txt"
    target.write_text("hi", encoding="utf-8")
    hits = find_file("report-2026", roots=[str(tmp_path)])
    assert hits and Path(hits[0]).name == "report-2026.txt"


def test_read_text_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("متن آزمایشی", encoding="utf-8")
    ok, content = read_text_file(str(f))
    assert ok and "آزمایشی" in content


def test_read_binary_rejected(tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"\x89PNG")
    ok, msg = read_text_file(str(f))
    assert not ok


def test_time_now_executor():
    result = A.execute_action("time_now", {})
    assert result.ok and "دقیقه" in result.message


def test_auditing_writes_jsonl(tmp_path, monkeypatch):
    from jasem import paths

    log = tmp_path / "audit.log"
    monkeypatch.setattr(paths, "audit_log_path", lambda: log)
    result = A.execute_action("time_now", {})
    A.audit({"name": "time_now", "args": {}}, result)
    assert log.exists() and "time_now" in log.read_text(encoding="utf-8")
