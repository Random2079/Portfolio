"""Screenshot + EasyOCR → OcrLine list."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from parse_lobby import OcrLine

ROOT = Path(__file__).resolve().parent
DEBUG_CAPTURE = ROOT / "debug_last_capture.png"

_reader = None


def get_reader(langs: list[str]):
    global _reader
    if _reader is None:
        import easyocr

        try:
            _reader = easyocr.Reader(langs, gpu=True, verbose=False)
        except Exception:
            _reader = easyocr.Reader(langs, gpu=False, verbose=False)
    return _reader


def find_discord_window(activate: bool = False):
    """Return mss-style monitor dict for Discord client, or None.

    Includes `_hwnd` and `_title` for focus/topmost helpers.
    """
    try:
        import pygetwindow as gw
    except ImportError:
        return None

    candidates = []
    for w in gw.getAllWindows():
        title = (w.title or "").strip()
        if not title:
            continue
        low = title.lower()
        if low.endswith(" - discord") or (
            "discord" in low and "zapret" not in low and "проводник" not in low
        ):
            candidates.append(w)
    if not candidates:
        return None

    best = None
    for w in candidates:
        if w.width < 200 or w.height < 200:
            continue
        if getattr(w, "isMinimized", False):
            continue
        best = w
        break
    if best is None:
        best = candidates[0]

    if activate:
        try:
            if best.isMinimized:
                best.restore()
            best.activate()
            import time

            time.sleep(0.2)
        except Exception:
            pass

    left, top = int(best.left), int(best.top)
    width, height = int(best.width), int(best.height)
    if width <= 0 or height <= 0:
        return None
    hwnd = int(getattr(best, "_hWnd", 0) or 0)
    return {
        "left": left,
        "top": top,
        "width": width,
        "height": height,
        "_title": best.title,
        "_hwnd": hwnd,
    }


def lobby_from_discord_title(title: str | None) -> str | None:
    """Discord voice titles often look like '🟣・94 | Lounge - Discord'."""
    if not title:
        return None
    import re

    m = re.search(r"[・·•]\s*(\d{1,3})\s*\|", title)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{1,3})\s*\|\s*\S+", title)
    if m:
        return m.group(1)
    return None


def sidebar_roi_from_window(win: dict, fraction: float = 0.36) -> dict:
    """Channel/member list: skip server icon rail on the left (~72px)."""
    rail = 72
    full_w = max(80, int(win["width"] * fraction))
    left = win["left"] + rail
    width = max(80, full_w - rail)
    return {
        "left": left,
        "top": win["top"],
        "width": width,
        "height": win["height"],
    }


def resolve_roi(cfg_roi: dict | None, prefer_discord: bool = True) -> tuple[dict | None, dict | None]:
    """Return (roi, discord_win). Does not topmost by itself."""
    if cfg_roi:
        win = find_discord_window(activate=False) if prefer_discord else None
        return cfg_roi, win
    if prefer_discord:
        win = find_discord_window(activate=False)
        if win:
            return sidebar_roi_from_window(win), win
    return None, None


def grab_image(
    roi: dict | None = None,
    image_path: str | Path | None = None,
    save_debug: bool = True,
) -> Image.Image:
    if image_path:
        img = Image.open(image_path).convert("RGB")
        if save_debug:
            img.save(DEBUG_CAPTURE)
        return img

    import mss

    with mss.mss() as sct:
        if roi:
            mon = {
                "left": int(roi["left"]),
                "top": int(roi["top"]),
                "width": int(roi["width"]),
                "height": int(roi["height"]),
            }
        else:
            m = sct.monitors[1]
            w = int(m["width"] * 0.28)
            mon = {
                "left": m["left"],
                "top": m["top"],
                "width": w,
                "height": m["height"],
            }
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        if save_debug:
            img.save(DEBUG_CAPTURE)
        return img


def run_ocr(img: Image.Image, langs: list[str], min_conf: float = 0.2) -> list[OcrLine]:
    reader = get_reader(langs)
    # Upscale — helps tiny / truncated Discord fonts
    w, h = img.size
    scale = max(1.0, 700 / w)
    if scale > 1.01:
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    arr = np.array(img)
    raw = reader.readtext(arr, paragraph=False)
    lines: list[OcrLine] = []
    for box, text, conf in raw:
        if float(conf) < min_conf:
            continue
        text = str(text).strip()
        if not text:
            continue
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        lines.append(
            OcrLine(
                text=text,
                y=float(sum(ys) / len(ys)),
                x=float(min(xs)),
                conf=float(conf),
            )
        )
    return lines
