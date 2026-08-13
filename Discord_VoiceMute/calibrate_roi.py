"""Задать ROI сайдбара: наведи мышь в угол1 → Enter, угол2 → Enter."""
from __future__ import annotations

import sys
import time

from config_util import load_config, save_config


def main() -> None:
    try:
        import pyautogui
    except ImportError:
        print("pip install pyautogui", file=sys.stderr)
        sys.exit(1)

    cfg = load_config()
    print("Наведи курсор на ЛЕВЫЙ ВЕРХНИЙ угол сайдбара Discord и нажми Enter…")
    input()
    x1, y1 = pyautogui.position()
    print(f"  corner1: {x1}, {y1}")
    time.sleep(0.3)
    print("Наведи на ПРАВЫЙ НИЖНИЙ угол области списка каналов/ников и Enter…")
    input()
    x2, y2 = pyautogui.position()
    print(f"  corner2: {x2}, {y2}")

    left, top = min(x1, x2), min(y1, y2)
    width, height = abs(x2 - x1), abs(y2 - y1)
    cfg["roi"] = {"left": left, "top": top, "width": width, "height": height}
    save_config(cfg)
    print(f"saved roi → config.json: {cfg['roi']}")


if __name__ == "__main__":
    main()
