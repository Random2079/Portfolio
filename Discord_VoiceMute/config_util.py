"""Load config.json (fallback: config.example.json)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_PATH = ROOT / "config.example.json"


def load_config() -> dict[str, Any]:
    path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    data["_config_path"] = str(path)
    return data


def save_config(data: dict[str, Any]) -> None:
    payload = {k: v for k, v in data.items() if not k.startswith("_")}
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
