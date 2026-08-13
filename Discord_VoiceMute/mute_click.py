"""Layer B: click mute/unmute for slot N (coords from config). Dry-run safe."""
from __future__ import annotations

import time
from typing import Any

from parse_command import Action


def slot_point(cfg: dict[str, Any], slot: int) -> tuple[int, int] | None:
    """Screen coords for member row N (1-based) among others list visually."""
    slots = cfg.get("mute_slots") or {}
    key = str(slot)
    if key in slots:
        p = slots[key]
        return int(p["x"]), int(p["y"])

    base = cfg.get("mute_slot1")
    dy = cfg.get("mute_slot_dy")
    if not base or dy is None:
        return None
    x = int(base["x"])
    y = int(base["y"]) + int(dy) * (slot - 1)
    return x, y


def menu_offset(cfg: dict[str, Any], action: Action) -> tuple[int, int]:
    key = "menu_mute_offset" if action == "mute" else "menu_unmute_offset"
    off = cfg.get(key) or {"x": 80, "y": 100}
    return int(off["x"]), int(off["y"])


def perform_mute_click(
    cfg: dict[str, Any],
    action: Action,
    slot: int,
    log=None,
) -> bool:
    """Right-click member slot then click mute/unmute menu item.

    Respects cfg['dry_run'] (default True) — only logs intended clicks.
    """
    pt = slot_point(cfg, slot)
    if pt is None:
        if log:
            log.error("no coordinates for slot %s — calibrate mute_slot1 / mute_slot_dy", slot)
        return False

    ox, oy = menu_offset(cfg, action)
    mx, my = pt[0] + ox, pt[1] + oy
    dry = cfg.get("dry_run", True)
    pause = float(cfg.get("click_pause_s") or 0.15)

    msg = f"{action} slot={slot} rclick=({pt[0]},{pt[1]}) menu=({mx},{my}) dry_run={dry}"
    if log:
        log.info(msg)
    else:
        print(msg)

    if dry:
        return True

    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.rightClick(pt[0], pt[1])
    time.sleep(pause)
    pyautogui.click(mx, my)
    time.sleep(pause)
    return True
