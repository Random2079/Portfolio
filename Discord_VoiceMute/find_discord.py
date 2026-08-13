"""Find Discord HWND via Win32 enum (more reliable than pygetwindow coords)."""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.windll.user32

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
SW_RESTORE = 9
SW_SHOW = 5
SW_MINIMIZE = 6


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


def _title(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _rect(hwnd: int) -> dict | None:
    wr = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(wr)):
        return None
    return {
        "left": wr.left,
        "top": wr.top,
        "width": wr.right - wr.left,
        "height": wr.bottom - wr.top,
    }


def find_discord_hwnd() -> tuple[int, str, dict] | None:
    """Return (hwnd, title, rect) for Discord client (may be off-screen / mini)."""
    found: list[tuple[int, str, dict]] = []

    def callback(hwnd, _lparam):
        title = _title(hwnd)
        if not title:
            return True
        low = title.lower()
        if not low.endswith(" - discord"):
            return True
        if "zapret" in low or "overlay" in low or "проводник" in low:
            return True
        wr = _rect(hwnd)
        if not wr:
            return True
        found.append((int(hwnd), title, wr))
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    if not found:
        return None

    def score(item: tuple[int, str, dict]) -> tuple:
        _h, title, r = item
        on_screen = 1 if r["left"] > -10000 and r["top"] > -10000 else 0
        area = max(0, r["width"]) * max(0, r["height"])
        # Prefer voice titles like "⚪・16 | Server - Discord"
        import re

        voice = 1 if re.search(r"[・·•]\s*\d{1,3}\s*\|", title) else 0
        return (on_screen, voice, area)

    found.sort(key=score, reverse=True)
    return found[0]


def prepare_discord_for_capture(hwnd: int, settle_s: float = 0.5) -> dict | None:
    """Restore Discord on-screen so PrintWindow/mss get a real frame. Returns new rect."""
    if not hwnd:
        return None
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.ShowWindow(hwnd, SW_SHOW)
    # If still off-screen, nudge to primary monitor
    wr = _rect(hwnd)
    if wr and (wr["left"] < -1000 or wr["top"] < -1000 or wr["width"] < 400):
        user32.SetWindowPos(hwnd, 0, 40, 40, 1280, 800, 0x0040)  # SWP_SHOWWINDOW
    time.sleep(settle_s)
    return _rect(hwnd)
