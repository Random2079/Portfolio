"""Capture pixels from a window HWND even if another app is in front."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

PW_RENDERFULLCONTENT = 2
SRCCOPY = 0x00CC0020


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def window_rect(hwnd: int) -> dict | None:
    wr = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(wr)):
        return None
    w = wr.right - wr.left
    h = wr.bottom - wr.top
    if w <= 1 or h <= 1:
        return None
    return {"left": wr.left, "top": wr.top, "width": w, "height": h}


def sidebar_roi_from_hwnd(hwnd: int, fraction: float = 0.36, rail: int = 72) -> dict | None:
    """Screen-coord ROI for channel list, derived only from Win32 rect."""
    wr = window_rect(hwnd)
    if not wr:
        return None
    full_w = max(120, int(wr["width"] * fraction))
    return {
        "left": wr["left"] + rail,
        "top": wr["top"],
        "width": max(100, full_w - rail),
        "height": wr["height"],
    }


def grab_window_image(hwnd: int) -> Image.Image | None:
    """Full window bitmap via PrintWindow (works when occluded)."""
    wr = window_rect(hwnd)
    if not wr:
        return None
    win_w, win_h = wr["width"], wr["height"]

    hwnd_dc = user32.GetWindowDC(hwnd)
    if not hwnd_dc:
        return None
    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    bmp = gdi32.CreateCompatibleBitmap(hwnd_dc, win_w, win_h)
    old = gdi32.SelectObject(mem_dc, bmp)

    ok = user32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT)
    if not ok:
        ok = gdi32.BitBlt(mem_dc, 0, 0, win_w, win_h, hwnd_dc, 0, 0, SRCCOPY)

    img = None
    if ok:
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = win_w
        bmi.bmiHeader.biHeight = -win_h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0
        buf = ctypes.create_string_buffer(win_w * win_h * 4)
        bits = gdi32.GetDIBits(mem_dc, bmp, 0, win_h, buf, ctypes.byref(bmi), 0)
        if bits:
            img = Image.frombuffer("RGB", (win_w, win_h), bytes(buf), "raw", "BGRX", 0, 1).copy()

    gdi32.SelectObject(mem_dc, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, hwnd_dc)
    return img


def grab_window_roi(hwnd: int, roi_screen: dict | None = None) -> Image.Image | None:
    full = grab_window_image(hwnd)
    if full is None:
        return None
    wr = window_rect(hwnd)
    if wr is None:
        return full
    if roi_screen is None:
        roi_screen = sidebar_roi_from_hwnd(hwnd)
    if not roi_screen:
        return full

    left = int(roi_screen["left"]) - wr["left"]
    top = int(roi_screen["top"]) - wr["top"]
    width = int(roi_screen["width"])
    height = int(roi_screen["height"])
    left = max(0, left)
    top = max(0, top)
    right = min(full.size[0], left + width)
    bottom = min(full.size[1], top + height)
    if right <= left or bottom <= top:
        return full
    return full.crop((left, top, right, bottom))
