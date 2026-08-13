"""Слой A: печать lobby / me / others."""
from __future__ import annotations

import argparse
import sys
import time

from config_util import load_config
from find_discord import find_discord_hwnd, prepare_discord_for_capture
from logging_util import setup_logging
from ocr_capture import DEBUG_CAPTURE, grab_image, lobby_from_discord_title, run_ocr
from parse_lobby import format_snapshot, parse_lobby
from win_capture import grab_window_roi, sidebar_roi_from_hwnd, window_rect
from win_focus import discord_on_top


def _rect_ok(rect: dict | None) -> bool:
    if not rect:
        return False
    if rect["left"] < -10000 or rect["top"] < -10000:
        return False
    return rect["width"] >= 400 and rect["height"] >= 300


def once(cfg: dict, image_path: str | None, log) -> None:
    mode = (cfg.get("capture_mode") or "game").lower()
    discord = None
    hwnd = 0
    roi = cfg.get("roi")

    if not image_path:
        hit = find_discord_hwnd()
        if not hit:
            log.warning("Discord не найден. Открой клиент на ЭТОМ рабочем столе (не сворачивай).")
            print("lobby: None\nme: None\nothers: []\nstatus: discord_unavailable")
            return

        hwnd, title, rect = hit
        discord = {"_hwnd": hwnd, "_title": title, **rect}
        log.info("capture_mode=%s | Discord: %s %s", mode, title, rect)

        if mode == "normal" and not _rect_ok(rect):
            log.info("normal: restoring ghost Discord…")
            new_rect = prepare_discord_for_capture(hwnd, settle_s=0.55)
            if new_rect:
                discord.update(new_rect)
                rect = new_rect
        elif mode == "game" and not _rect_ok(rect):
            log.warning(
                "Discord свёрнут / на другом вирт. столе / призрак. "
                "В game-режиме не трогаем фокус — оставь окно открытым на этом столе под другими окнами."
            )
            print("lobby: None\nme: None\nothers: []\nstatus: discord_unavailable")
            return

        if not roi:
            roi = sidebar_roi_from_hwnd(hwnd)

    if roi:
        log.info("ROI: %s", roi)

    if image_path:
        img = grab_image(roi=None, image_path=image_path, save_debug=True)
    else:
        img = None
        if hwnd:
            img = grab_window_roi(hwnd, roi)
            if img is not None and img.size[0] > 100 and img.size[1] > 100:
                img.save(DEBUG_CAPTURE)
                log.info("capture via PrintWindow (no focus steal)")
            else:
                img = None

        if img is None and mode == "normal" and hwnd:
            log.info("PrintWindow weak — normal fallback: topmost + screen")
            with discord_on_top(hwnd, settle_s=0.45):
                wr = window_rect(hwnd)
                if wr and not roi:
                    roi = sidebar_roi_from_hwnd(hwnd)
                img = grab_image(roi=roi, image_path=None, save_debug=True)
        elif img is None:
            log.warning("Не удалось снять Discord без кражи фокуса (game). status=capture_failed")
            print("lobby: None\nme: None\nothers: []\nstatus: capture_failed")
            return

    log.info("capture %sx%s → %s", img.size[0], img.size[1], DEBUG_CAPTURE.name)

    lines = run_ocr(img, langs=cfg.get("ocr_lang") or ["ru", "en"])
    log.info("OCR lines: %d", len(lines))

    snap = parse_lobby(
        lines,
        my_nickname=cfg["my_nickname"],
        aliases=cfg.get("nickname_aliases") or [],
    )
    title_lobby = lobby_from_discord_title((discord or {}).get("_title"))
    if title_lobby:
        if snap.lobby != title_lobby:
            log.info("lobby from title %r overrides OCR %r", title_lobby, snap.lobby)
        snap.lobby = title_lobby

    print(format_snapshot(snap))
    print("status: ok")
    log.info("result lobby=%r me=%r others=%s", snap.lobby, snap.me, snap.others)

    print("--- OCR lines ---", file=sys.stderr)
    if not lines:
        print("  (пусто — смотри debug_last_capture.png)", file=sys.stderr)
    for L in sorted(lines, key=lambda x: (x.y, x.x)):
        print(f"  {L.conf:.2f} y={L.y:.0f} {L.text!r}", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description="IDEA-005 layer A: detect Discord lobby")
    ap.add_argument("--image", help="PNG/JPG instead of live screen")
    ap.add_argument("--once", action="store_true", help="single shot (default with --image)")
    ap.add_argument("--loop", action="store_true", help="poll until Ctrl+C")
    ap.add_argument(
        "--mode",
        choices=("game", "normal"),
        help="override config capture_mode",
    )
    args = ap.parse_args()

    log = setup_logging()
    cfg = load_config()
    if args.mode:
        cfg["capture_mode"] = args.mode
    log.info("config: %s", cfg.get("_config_path"))
    log.info("me nick: %s | capture_mode: %s", cfg["my_nickname"], cfg.get("capture_mode"))

    do_loop = args.loop or (not args.image and not args.once)
    if args.image and not args.loop:
        do_loop = False

    if not do_loop:
        once(cfg, args.image, log)
        return

    interval = float(cfg.get("poll_interval_s") or 2.0)
    log.info("polling every %ss — Ctrl+C to stop", interval)
    try:
        while True:
            print("---")
            once(cfg, args.image, log)
            time.sleep(interval)
    except KeyboardInterrupt:
        log.info("bye")


if __name__ == "__main__":
    main()
