"""Parse voice/text commands like «замуть 3» / «размуть 2 слота»."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Action = Literal["mute", "unmute"]


@dataclass
class Command:
    action: Action
    slot: int
    raw: str


_NUM_WORDS = {
    "один": 1,
    "одна": 1,
    "одно": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
}


def _to_slot(token: str) -> int | None:
    t = token.strip().lower().replace("ё", "е")
    if t.isdigit():
        n = int(t)
        return n if n >= 1 else None
    return _NUM_WORDS.get(t)


def parse_command(text: str) -> Command | None:
    """Return Command or None if not recognized."""
    if not text or not text.strip():
        return None
    raw = text.strip()
    s = raw.lower().replace("ё", "е")
    s = re.sub(r"[^\w\s]+", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()

    mute_m = re.search(
        r"\b(замуть|замьють|mute|мьют)\s+(\w+)(?:\s+слот\w*)?",
        s,
    )
    if mute_m:
        slot = _to_slot(mute_m.group(2))
        if slot:
            return Command(action="mute", slot=slot, raw=raw)

    unmute_m = re.search(
        r"\b(размуть|анмьют|unmute|сними\s+мут)\s+(\w+)(?:\s+слот\w*)?",
        s,
    )
    if unmute_m:
        slot = _to_slot(unmute_m.group(2))
        if slot:
            return Command(action="unmute", slot=slot, raw=raw)

    return None


def format_command(cmd: Command | None) -> str:
    if cmd is None:
        return "UNKNOWN"
    return f"{cmd.action.upper()} slot={cmd.slot}"
