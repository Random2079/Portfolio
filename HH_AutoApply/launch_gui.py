"""GUI entry for launch.vbs: pythonw → hh_auto ui, crashes → _launch_error.log."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_LOG = _ROOT / "_launch_error.log"


class _Tee:
    def __init__(self, path: Path) -> None:
        self._fh = path.open("a", encoding="utf-8", errors="replace")

    def write(self, data: str) -> int:
        if not data:
            return 0
        self._fh.write(data)
        self._fh.flush()
        return len(data)

    def flush(self) -> None:
        self._fh.flush()

    def fileno(self) -> int:
        return self._fh.fileno()

    def isatty(self) -> bool:
        return False


def _install_stdio() -> None:
    tee = _Tee(_LOG)
    sys.stdout = tee  # type: ignore[assignment]
    sys.stderr = tee  # type: ignore[assignment]

    def _hook(exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        traceback.print_exception(exc_type, exc, tb, file=tee)
        tee.flush()

    sys.excepthook = _hook


def main() -> int:
    _install_stdio()
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    try:
        from hh_auto.ui import run_ui

        return int(run_ui(None))
    except SystemExit as e:
        code = e.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
