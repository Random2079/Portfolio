"""Drop sports/betting/esports junk and non-news quote pages from feeds.

Cheap pre-AI layer: denylist + near-dup fingerprints so DeepSeek is not
called on Profit/tech-analysis spam or same title with different site tails.
"""

from __future__ import annotations

import re

# Appended to Google News equity search (minus-operators). Bonds: lighter set.
_GOOGLE_MINUS_EQUITY = (
    "-ставки -ставка -кэф -коэффициент -букмекер -киберспорт "
    "-dota -cs2 -esports -прогноз "
    "-форум -котировки -\"курс на сегодня\" "
    "-\"технический анализ\" -\"идея в профите\" -\"#сильный_рост\""
)

# Trailing site / product suffixes that do not change the story.
_SOURCE_TAIL = re.compile(
    r"""
    \s*[-—–|]\s*
    (?:
        бкс\s*экспресс
      | bcs\s*express
      | финам(?:\.ru)?
      | finam
      | smart[- ]?lab(?:\.ru)?
      | финансы\s*mail(?:\.ru)?
      | mail\.ru
      | рбк
      | коммерсантъ?
      | интерфакс
      | ведомости
      | тасс
      | прайм
      | profite?
      | профит(?:е)?
      | ставка\s*тв
    )
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Extra Profit / board tails glued without a clear separator.
_PROFIT_SUFFIX = re.compile(
    r"""
    \s*
    (?:
        (?:идея\s+)?в\s+профите(?:\s+по\s+[A-ZА-Я0-9._-]+)?
      | профите\s+по\s+[A-ZА-Я0-9._-]+
    )
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Title denylist: if any pattern matches → drop (case-insensitive).
# Avoid bare «ставка/прогноз» — ловят ЦБ и отчёты.
# FCF/капитализация — только dump-страницы SmartLab, не новости про отчёт.
# Futures: «Фьючерс на …» / board codes — not corporate bond news.
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
      # Smart-Lab forum / quote terminals / fundamental dump pages
      | форум\s+акци
      | страница\s+\d+
      | курс\s+на\s+сегодня
      | цена\s+и\s+котировки
      | котировки\s+онлайн
      | капитализация\s+мсфо
      | цена\s+акции\s+ап\s+мсфо
      | свободный\s+денежный\s+поток.{0,40}(?:годов|мсфо|значения)
      | \bfcf\s+мсфо\b
      # BCS Express Profit product / Finam chart spam
      | идея\s+в\s+профите
      | профите\s+по\s+
      | технический\s+анализ
      | \#сильный_рост
      | сильный_рост
      # Board / retail futures noise (not corp bonds / issuer news)
      | фьючерс\s+на\s+
      | \bфьючерс\b.{0,40}(?:si-|br-|gold-|rts-|mix-|eu-|gazp-|sbrf-)
      | (?:котировки|цена)\s+фьючерс
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


def normalize_title_for_dup(title: str) -> str:
    """Strip site/Profit tails and collapse whitespace for near-dup compare."""
    t = (title or "").strip().lower()
    if not t:
        return ""
    t = _SOURCE_TAIL.sub("", t)
    t = _PROFIT_SUFFIX.sub("", t)
    t = re.sub(r"[\"'«»„“]", "", t)
    t = re.sub(r"\s+", " ", t).strip(" \t-—–|")
    return t


def title_fingerprint(title: str) -> str:
    """Stable fingerprint for near-duplicate titles (pre-AI)."""
    return normalize_title_for_dup(title)


def is_near_duplicate_title(title: str, seen_fingerprints: set[str]) -> bool:
    """True if fingerprint already in ``seen``; empty titles count as dup."""
    fp = title_fingerprint(title)
    if not fp:
        return True
    return fp in seen_fingerprints


def remember_title_fingerprint(title: str, seen_fingerprints: set[str]) -> str:
    """Add fingerprint to ``seen``; return the fingerprint (may be empty)."""
    fp = title_fingerprint(title)
    if fp:
        seen_fingerprints.add(fp)
    return fp


def title_matches_ticker(title: str, ticker_id: str, search_query: str = "") -> bool:
    """Whether a headline is about this ticker.

    Short tickers (len ≤ 2) must see an issuer/name token (len ≥ 3) in the
    title — bare ``T`` / ``VK`` letter matches create Trump/macro false positives.
    Longer tickers keep the cheap substring token match used by SmartLab.
    """
    hay = (title or "").strip().lower()
    if not hay:
        return False
    tid = (ticker_id or "").strip().lower()
    name_tokens: list[str] = []
    for w in (search_query or "").replace(",", " ").split():
        w = w.strip().lower()
        if len(w) < 3:
            continue
        if w.startswith("ru000") and len(w) > 8:
            continue
        if w not in name_tokens:
            name_tokens.append(w)

    if tid and len(tid) <= 2:
        if name_tokens:
            return any(tok in hay for tok in name_tokens)
        # No issuer name available: only accept ticker as a whole word.
        return bool(re.search(rf"(?<!\w){re.escape(tid)}(?!\w)", hay))

    tokens: list[str] = []
    if tid:
        tokens.append(tid)
    for tok in name_tokens:
        if tok not in tokens:
            tokens.append(tok)
    if not tokens:
        return False
    return any(tok in hay for tok in tokens)
