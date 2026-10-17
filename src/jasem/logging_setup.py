"""Logging setup with secret redaction."""

from __future__ import annotations

import logging
import logging.handlers
import re
from typing import Iterable

from . import paths

_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|token|secret)\s*[=:]\s*([^\s\"',;]+)"
)


class RedactingFilter(logging.Filter):
    """Scrubs anything that looks like an API key/secret from log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            msg = record.getMessage()
        except Exception:
            return True
        redacted = _SECRET_RE.sub(lambda m: f"{m.group(1)}=***", msg)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def setup_logging(level: int = logging.INFO, extra_loggers: Iterable[str] = ()) -> logging.Logger:
    root = logging.getLogger("jasem")
    if root.handlers:
        return root
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"
    )
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.addFilter(RedactingFilter())
    root.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        paths.logs_dir() / "jasem.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    file_handler.addFilter(RedactingFilter())
    root.addHandler(file_handler)

    for name in extra_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)
    return root
