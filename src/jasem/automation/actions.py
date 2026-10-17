"""Structured action registry.

Every automation capability is a registered action with a schema validator and
an executor. The orchestrator (a) validates arguments, (b) asks the Policy for
a permission decision, (c) executes only on approval, and (d) audits the real
result. Nothing here executes raw model text.
"""

from __future__ import annotations

import logging
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .. import paths
from . import apps, files, sysinfo, volume

log = logging.getLogger("jasem.automation")


@dataclass
class ActionResult:
    ok: bool
    message: str                       # Persian, speakable summary
    data: dict[str, Any] = field(default_factory=dict)
    needs_confirmation: bool = False
    confirmation_text: str = ""


Validator = Callable[[dict], tuple[bool, str]]


def _need_str(args: dict, key: str, label: str) -> tuple[bool, str, str]:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        return False, "", f"آرگومان «{label}» لازم است."
    return True, value.strip(), ""


def _validate_open_app(args: dict) -> tuple[bool, str]:
    ok, _, err = _need_str(args, "name", "نام برنامه")
    return ok, err


def _validate_open_url(args: dict) -> tuple[bool, str]:
    ok, url, err = _need_str(args, "url", "آدرس")
    if not ok:
        return False, err
    if not url.startswith(("http://", "https://", "www.")):
        url = "https://" + url
        args["url"] = url
    return True, ""


def _validate_noop(args: dict) -> tuple[bool, str]:
    return True, ""


@dataclass
class ActionSpec:
    name: str
    validate: Validator
    execute: Callable[[dict], ActionResult]


ACTIONS: dict[str, ActionSpec] = {}

# The orchestrator installs a notifier here so reminders surface in the UI.
REMINDER_NOTIFY: Callable[[str], None] | None = None


def register(name: str, validate: Validator):
    def deco(fn: Callable[[dict], ActionResult]):
        ACTIONS[name] = ActionSpec(name=name, validate=validate, execute=fn)
        return fn

    return deco


# -- executors --------------------------------------------------------------------
@register("open_app", _validate_open_app)
def _open_app(args: dict) -> ActionResult:
    name = args["name"]
    target = apps.resolve_app(name)
    if not target:
        return ActionResult(False, f"برنامه «{name}» پیدا نشد.")
    ok, detail = apps.launch(target)
    if ok:
        return ActionResult(True, f"«{name}» باز شد.", {"target": target})
    return ActionResult(False, f"باز کردن «{name}» شکست خورد: {detail}")


@register("open_browser", _validate_noop)
def _open_browser(args: dict) -> ActionResult:
    ok = bool(webbrowser.open("about:blank"))
    return ActionResult(ok, "مرورگر باز شد." if ok else "مرورگر باز نشد.")


@register("open_url", _validate_open_url)
def _open_url(args: dict) -> ActionResult:
    url = args["url"]
    webbrowser.open(url)
    return ActionResult(True, f"آدرس {url} در مرورگر باز شد.")


@register("open_path", lambda a: (True, ""))
def _open_path(args: dict) -> ActionResult:
    p = Path(str(args.get("path", "")).strip()).expanduser()
    if not p.exists():
        hits = files.find_file(p.name, max_results=1)
        if hits:
            p = Path(hits[0])
        else:
            return ActionResult(False, "این مسیر پیدا نشد.")
    import os as _os

    _os.startfile(str(p))
    return ActionResult(True, f"«{p.name}» باز شد.")


@register("system_info", _validate_noop)
def _system_info(args: dict) -> ActionResult:
    info = sysinfo.system_info()
    msg = (f"پردازنده {info['cpu_cores']} هسته‌ای با {info['cpu_threads']} رشته، "
           f"مصرف CPU {info['cpu_percent']} درصد، رم {info['ram_total_gb']} گیگابایت "
           f"( {info['ram_used_pct']} درصد استفاده شده).")
    return ActionResult(True, msg, info)


@register("disk_space", _validate_noop)
def _disk_space(args: dict) -> ActionResult:
    disks = sysinfo.disk_space()
    if not disks:
        return ActionResult(False, "اطلاعات دیسک در دسترس نیست.")
    parts = [f"{d['drive']} حدود {d['free_gb']} گیگ آزاد از {d['total_gb']}" for d in disks[:4]]
    return ActionResult(True, "فضای آزاد دیسک‌ها: " + "؛ ".join(parts) + ".", {"disks": disks})


@register("battery", _validate_noop)
def _battery(args: dict) -> ActionResult:
    b = sysinfo.battery()
    if b is None:
        return ActionResult(True, "این دستگاه باتری نداره یا قابل شناسایی نیست.")
    state = "به برق وصله" if b["plugged"] else "با باتری کار می‌کنه"
    return ActionResult(True, f"باتری {int(b['percent'])} درصد است و {state}.", b)


@register("network_check", _validate_noop)
def _network_check(args: dict) -> ActionResult:
    net = sysinfo.network_check()
    if net["connected"]:
        lat = f" با تأخیر حدودی {net['latency_ms']} میلی‌ثانیه" if net["latency_ms"] else ""
        return ActionResult(True, f"اینترنت وصل است{lat}.", net)
    return ActionResult(True, "فعلاً به اینترنت دسترسی ندارم؛ اتصال برقرار نشد.", net)


@register("list_processes", _validate_noop)
def _list_processes(args: dict) -> ActionResult:
    procs = sysinfo.top_processes()
    names = [p["name"] for p in procs[:8] if p["name"]]
    return ActionResult(True, "پرمصرف‌ترین برنامه‌ها: " + "، ".join(names) + ".", {"processes": procs})


@register("volume_set", _validate_noop)
def _volume_set(args: dict) -> ActionResult:
    if not volume.is_available():
        return ActionResult(False, "کنترل صدا در دسترس نیست.")
    if "level" in args:
        ok = volume.set_volume(float(args["level"]) / 100.0)
        level = float(args["level"])
    else:
        delta = float(args.get("delta", 10)) * (1 if args.get("direction", "up") == "up" else -1)
        new = volume.adjust_volume(delta)
        if new is None:
            return ActionResult(False, "تنظیم صدا انجام نشد.")
        ok, level = True, round(new * 100)
    return ActionResult(ok, f"صدای سیستم روی {int(level)} درصد تنظیم شد." if ok else "تنظیم صدا انجام نشد.")


@register("volume_mute", _validate_noop)
def _volume_mute(args: dict) -> ActionResult:
    if not volume.is_available():
        return ActionResult(False, "کنترل صدا در دسترس نیست.")
    muted = volume.toggle_mute()
    if muted is None:
        return ActionResult(False, "وضعیت بی‌صدا قابل تشخیص نیست.")
    return ActionResult(True, "بی‌صدا شد." if muted else "صدا برگشت.")


@register("calculate", _validate_noop)
def _calculate(args: dict) -> ActionResult:
    expr = str(args.get("expression", ""))
    try:
        value = files.safe_eval(expr)
    except Exception:
        return ActionResult(False, "این عبارت ریاضی را نمی‌توانم حساب کنم.")
    if value == int(value):
        value = int(value)
    return ActionResult(True, f"نتیجه {value} است.", {"value": value})


@register("web_search", lambda a: _need_str(a, "query", "عبارت جستجو")[:2])
def _web_search(args: dict) -> ActionResult:
    from urllib.parse import quote_plus

    q = args["query"]
    webbrowser.open(f"https://www.google.com/search?q={quote_plus(q)}")
    return ActionResult(True, f"جستجوی «{q}» در گوگل باز شد.")


@register("create_note", lambda a: _need_str(a, "text", "متن یادداشت")[:2])
def _create_note(args: dict) -> ActionResult:
    ok, detail = files.create_note(args["text"])
    return ActionResult(ok, "یادداشت ذخیره شد." if ok else f"یادداشت ذخیره نشد: {detail}",
                        {"path": detail})


@register("reminder", lambda a: _need_str(a, "text", "متن یادآوری")[:2] if not a.get("seconds") else (True, ""))
def _reminder(args: dict) -> ActionResult:
    text = args["text"]
    seconds = float(args.get("seconds", 60))
    notify = REMINDER_NOTIFY or (lambda msg: log.info("reminder: %s", msg))
    files.set_reminder(text, seconds, notify=notify)
    minutes = max(1, round(seconds / 60))
    return ActionResult(True, f"باشه، {minutes} دقیقه دیگه یادآوری می‌کنم: {text}.",
                        {"seconds": seconds})


@register("time_now", _validate_noop)
def _time_now(args: dict) -> ActionResult:
    from datetime import datetime

    now = datetime.now()
    return ActionResult(True, f"الان {now.hour} و {now.minute} دقیقه است.",
                        {"iso": now.isoformat()})


@register("find_file", lambda a: _need_str(a, "query", "نام فایل")[:2])
def _find_file(args: dict) -> ActionResult:
    hits = files.find_file(
        args["query"], args.get("folder"),
        max_results=20,
    )
    if not hits:
        return ActionResult(True, "چیزی با این اسم پیدا نکردم.")
    preview = "؛ ".join(Path(h).name for h in hits[:5])
    return ActionResult(True, f"{len(hits)} مورد پیدا کردم، از جمله: {preview}.",
                        {"paths": hits})


@register("read_file", lambda a: _need_str(a, "path", "مسیر فایل")[:2])
def _read_file(args: dict) -> ActionResult:
    ok, content = files.read_text_file(args["path"])
    if not ok:
        return ActionResult(False, content)
    snippet = content[:1200]
    return ActionResult(True, "متن فایل را خواندم؛ خلاصه‌اش را می‌گم.", {"content": snippet})


@register("end_process", lambda a: _need_str(a, "name", "نام برنامه")[:2])
def _end_process(args: dict) -> ActionResult:
    killed, matched = sysinfo.end_process_by_name(args["name"])
    if matched == 0:
        return ActionResult(False, "چنین برنامه‌ای در حال اجرا نیست.")
    return ActionResult(True, f"{killed} برنامه «{args['name']}» بسته شد.")


def validate_action(action: dict) -> tuple[bool, str, str]:
    """Returns (valid, action_name, error)."""
    name = action.get("name")
    if not isinstance(name, str) or name not in ACTIONS:
        return False, str(name), f"عملیات ناشناخته: {name}"
    args = action.get("args") or {}
    if not isinstance(args, dict):
        return False, name, "آرگومان‌ها باید شیء باشند."
    ok, err = ACTIONS[name].validate(args)
    return ok, name, err


def execute_action(name: str, args: dict) -> ActionResult:
    try:
        return ACTIONS[name].execute(args)
    except Exception as exc:
        log.exception("action %s failed", name)
        return ActionResult(False, f"عملیات «{name}» با خطا مواجه شد: {exc}")


def audit(action: dict, result: ActionResult, actor: str = "voice") -> None:
    import json
    import time

    if not paths.audit_log_path().parent.exists():
        return
    record = {
        "ts": time.time(),
        "action": action.get("name"),
        "args": {k: (str(v)[:120]) for k, v in (action.get("args") or {}).items()},
        "ok": result.ok,
        "actor": actor,
    }
    try:
        with paths.audit_log_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        log.exception("audit write failed")
