"""HH_AutoApply — слой A: search/score/cover; слой B: Playwright apply."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DEFAULT_CONFIG = ROOT / "config.example.json"
USER_CONFIG = ROOT / "config.json"


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path if path else (USER_CONFIG if USER_CONFIG.exists() else DEFAULT_CONFIG)
    with cfg_path.open(encoding="utf-8") as f:
        return json.load(f)


def ensure_data_dir() -> Path:
    DATA.mkdir(parents=True, exist_ok=True)
    return DATA
