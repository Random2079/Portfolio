"""Logging to file next to the app."""
from __future__ import annotations

import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_PATH = ROOT / "voicemute.log"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("voicemute")
    if logger.handlers:
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger
