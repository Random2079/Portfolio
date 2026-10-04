"""GUI entry for launch.vbs: keep crash stderr under pythonw (no cmd window)."""
from __future__ import annotations

import runpy
import sys
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_LOG = _ROOT / "_launch_error.log"
_APP = _ROOT / "Subtitle_App.py"


class _Tee:
    """Append-only file wrapper; tolerates pythonw where sys.stdout may be None."""

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
    if not _APP.is_file():
        _install_stdio()
        print(f"missing Subtitle_App.py: {_APP}", flush=True)
        return 1
    _install_stdio()
    try:
        runpy.run_path(str(_APP), run_name="__main__")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
