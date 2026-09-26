"""Drop sports/betting/esports junk from ticker news feeds."""

from __future__ import annotations

import re

# Appended to Google News equity search (minus-operators). Bonds: lighter set.
_GOOGLE_MINUS_EQUITY = (
    "-ставки -ставка -кэф -коэффициент -букмекер -киберспорт "
    "-dota -cs2 -esports -прогноз"
)

# Title denylist: if any pattern matches → drop (case-insensitive).
# Avoid bare «ставка/прогноз» — ловят ЦБ и отчёты.
_TITLE_NOISE = re.compile(
    r"""
    (?:
        \bкэф(?:ы|а|ов)?\b
      | коэффициент\s*\d
      | букмекер\w*
      | киберспорт\w*
      | \besports?\b
      | \bdota\b
      | \bcs:?\s*2\b
      | counter[- ]?strike
      | team\s+yandex
      | \bmouz\b
      | ставка\s*тв
      | ставк\w*\s+на\s+(?:матч|игру|команду)
      | live[\s-]*ставк
      | прогноз\s*\(\s*кэф
      | \bб\.?\s*к\.?\b.{0,40}ставк
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def google_query_exclusions(kind: str) -> str:
    if (kind or "").strip().lower() == "bond":
        return "-ставки -кэф -букмекер -киберспорт"
    return _GOOGLE_MINUS_EQUITY


def is_noise_title(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return True
    return bool(_TITLE_NOISE.search(t))
