"""File, note, reminder and calculation helpers."""

from __future__ import annotations

import ast
import logging
import operator
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..nlp.normalize import normalize_text

log = logging.getLogger("jasem.automation.files")

TEXT_SUFFIXES = {".txt", ".md", ".py", ".json", ".csv", ".log", ".ini", ".cfg",
                 ".yaml", ".yml", ".toml", ".xml", ".html", ".css", ".js", ".ts",
                 ".bat", ".ps1", ".srt", ".rst"}


def _search_roots(roots: list[str] | None) -> list[Path]:
    if roots:
        return [Path(r).expanduser() for r in roots if Path(r).expanduser().exists()]
    return [Path.home()]


def find_file(query: str, folder: str | None = None, roots: list[str] | None = None,
              max_results: int = 20, timeout_s: float = 15.0) -> list[str]:
    """Bounded recursive filename search. Returns absolute paths."""
    q = normalize_text(query).lower()
    if not q:
        return []
    search_space: list[Path]
    if folder:
        cand = Path(folder).expanduser()
        if not cand.exists():
            home = Path.home() / folder
            cand = home if home.exists() else cand
        search_space = [cand] if cand.exists() else []
    else:
        search_space = _search_roots(roots)
    results: list[str] = []
    deadline = time.monotonic() + timeout_s
    for root in search_space:
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip huge/irrelevant trees.
            dirnames[:] = [d for d in dirnames if d.lower() not in
                           {"appdata", "node_modules", ".git", "__pycache__", "$recycle.bin",
                            "windows", ".venv", "venv"}]
            for fn in filenames:
                if q in normalize_text(fn).lower():
                    results.append(os.path.join(dirpath, fn))
                    if len(results) >= max_results or time.monotonic() > deadline:
                        return results
    return results


def read_text_file(path_str: str, max_bytes: int = 262_144) -> tuple[bool, str]:
    p = Path(path_str).expanduser()
    if not p.exists():
        hits = find_file(p.name, max_results=1)
        if hits:
            p = Path(hits[0])
        else:
            return False, "فایل پیدا نشد."
    if p.suffix.lower() not in TEXT_SUFFIXES:
        return False, f"فرمت {p.suffix or 'نامشخص'} پشتیبانی نمی‌شود."
    if p.stat().st_size > max_bytes:
        return False, "فایل خیلی بزرگ است."
    try:
        return True, p.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError) as exc:
        return False, str(exc)


def create_note(text: str, notes_dir: Path | None = None) -> tuple[bool, str]:
    folder = notes_dir or (Path.home() / "Documents" / "JASEM Notes")
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = folder / f"note-{stamp}.txt"
    try:
        path.write_text(text, encoding="utf-8")
        return True, str(path)
    except OSError as exc:
        return False, str(exc)


# -- safe calculator ------------------------------------------------------------
_ALLOWED_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
    ast.Mod: operator.mod,
}


def safe_eval(expression: str) -> float:
    """Evaluate arithmetic expressions only — no names, no calls, no attributes."""

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 10:
                raise ValueError("exponent too large")
            return _ALLOWED_OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
            return _ALLOWED_OPS[type(node.op)](ev(node.operand))
        raise ValueError(f"unsupported expression element: {type(node).__name__}")

    tree = ast.parse(expression, mode="eval")
    return float(ev(tree))


def set_reminder(text: str, seconds: float, notify: Callable[[str], None]) -> bool:
    """In-process timer reminder; fires through the UI/notification callback."""

    def fire() -> None:
        notify(f"یادآوری: {text}")

    timer = threading.Timer(seconds, fire)
    timer.daemon = True
    timer.start()
    return True
