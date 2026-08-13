"""Raise Discord above other windows for a clean screenshot, then restore."""
from __future__ import annotations

import ctypes
import time
from contextlib import contextmanager
from typing import Iterator

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
SW_RESTORE = 9

user32 = ctypes.windll.user32


def _set_topmost(hwnd: int, on: bool) -> None:
    insert = HWND_TOPMOST if on else HWND_NOTOPMOST
    user32.SetWindowPos(
        hwnd,
        insert,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
    )


@contextmanager
def discord_on_top(hwnd: int, settle_s: float = 0.4) -> Iterator[None]:
    """Temporarily make Discord always-on-top so mss sees it, not Cursor/Chrome."""
    if not hwnd:
        yield
        return
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        _set_topmost(hwnd, True)
        time.sleep(settle_s)
        yield
    finally:
        try:
            _set_topmost(hwnd, False)
        except Exception:
            pass
