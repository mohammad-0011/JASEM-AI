"""Silent launcher for start-with-Windows (run with pythonw.exe)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from jasem.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main([]))
