"""Parse OCR lines into lobby / me / others."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class OcrLine:
    text: str
    y: float
    x: float
    conf: float


@dataclass
class LobbySnapshot:
    lobby: str | None
    me: str | None
    others: list[str]
    all_lines: list[str]


def _norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[^\w\s]+", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_me(text: str, my_nickname: str, aliases: list[str]) -> bool:
    """Match full nick, aliases, or truncated Discord/OCR fragment.

    Short crumbs ('ИщУ', 'работу' alone) do NOT count.
    """
    n = _norm(text)
    if not n:
        return False

    n_stripped = re.sub(r"[\.…]+$", "", n).strip()
    n_variants = {n, n_stripped}

    # Strong signal for this project nick even when OCR splits weirdly
    for nv in n_variants:
        if "ищу" in nv and "работ" in nv:
            return True
        if nv.startswith("ищу работ"):
            return True

    candidates = [my_nickname, *aliases]
    for c in candidates:
        cn = _norm(c)
        if not cn:
            continue
        head = cn.split("(")[0].strip()
        for nv in n_variants:
            if not nv or len(nv) < 8:
                continue
            if cn in nv or nv in cn:
                return True
            if head and len(head) >= 8 and (head in nv or (len(nv) >= 10 and nv in head)):
                return True
            if len(nv) >= 10 and (cn.startswith(nv) or head.startswith(nv)):
                return True
    return False


_UI_JUNK = re.compile(
    r"пригласить|новых упомина|новоб|голос|текстов|категор|"
    r"смени\s*ник|наблюдатель|случайная|приватная|lounge|^\d+-\d+$",
    re.IGNORECASE,
)

# OCR often writes Latin B instead of Cyrillic В
_STREAM_TAG = re.compile(
    r"\s*[BВ]\s*эфире\s*$|"
    r"\s*в\s*эфире\s*$|"
    r"\s*live\s*$",
    re.IGNORECASE,
)


def _clean_member_name(text: str) -> str:
    t = text.strip()
    t = _STREAM_TAG.sub("", t).strip()
    t = re.sub(r"\s+", " ", t)
    return t


def _is_junk_member(text: str) -> bool:
    t = _clean_member_name(text)
    if len(_norm(t)) < 2:
        return True
    if _UI_JUNK.search(t):
        return True
    if re.fullmatch(r"[\d\s/.:%]+", t):
        return True
    return False


def _merge_nearby_lines(lines: list[OcrLine], y_tol: float = 28.0) -> list[OcrLine]:
    """Glue OCR crumbs on the same row (e.g. 'Ищу' + 'работу (Python')."""
    if not lines:
        return []
    ordered = sorted(lines, key=lambda L: (L.y, L.x))
    merged: list[OcrLine] = []
    buf = ordered[0]
    for L in ordered[1:]:
        if abs(L.y - buf.y) <= y_tol and L.x >= buf.x - 5:
            buf = OcrLine(
                text=f"{buf.text} {L.text}".strip(),
                y=(buf.y + L.y) / 2,
                x=min(buf.x, L.x),
                conf=min(buf.conf, L.conf),
            )
        else:
            merged.append(buf)
            buf = L
    merged.append(buf)
    return merged


def _looks_like_channel(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    # "94", "• 94", ". 94", "· 94"
    if re.fullmatch(r"[•·.\-\s]*\d{1,3}", t):
        return True
    if re.match(r"^[•·.]\s*\d{1,3}\b", t):
        return True
    if re.match(r"^[•·]\s*\S+", t):
        return True
    if re.fullmatch(r"\d{1,3}", t):
        return True
    return False


def _channel_label(text: str) -> str:
    t = text.strip()
    m = re.search(r"\d{1,3}", t)
    if m and re.fullmatch(r"[•·.\-\s]*\d{1,3}", t):
        return m.group(0)
    if m and re.match(r"^[•·.]\s*\d{1,3}", t):
        return m.group(0)
    return t.lstrip("•·.- ").strip()


def parse_lobby(
    lines: list[OcrLine],
    my_nickname: str,
    aliases: list[str] | None = None,
) -> LobbySnapshot:
    aliases = aliases or []
    ordered = _merge_nearby_lines(lines)
    texts = [L.text.strip() for L in ordered if L.text.strip()]

    me_idx: int | None = None
    me_text: str | None = None
    best_len = -1
    for i, L in enumerate(ordered):
        if _is_me(L.text, my_nickname, aliases):
            score = len(_norm(L.text))
            if score > best_len:
                best_len = score
                me_idx = i
                me_text = L.text.strip()

    if me_idx is None:
        return LobbySnapshot(lobby=None, me=None, others=[], all_lines=texts)

    lobby: str | None = None
    lobby_idx: int | None = None
    for j in range(me_idx - 1, -1, -1):
        if _looks_like_channel(ordered[j].text):
            lobby = _channel_label(ordered[j].text)
            lobby_idx = j
            break

    others: list[str] = []
    start = (lobby_idx + 1) if lobby_idx is not None else 0
    for k in range(start, len(ordered)):
        if k == me_idx:
            continue
        t = ordered[k].text.strip()
        if _looks_like_channel(t):
            if lobby_idx is not None and k > me_idx:
                break
            if lobby_idx is None:
                continue
            break
        if _is_me(t, my_nickname, aliases):
            continue
        if _is_junk_member(t):
            continue
        cleaned = _clean_member_name(t)
        if cleaned:
            others.append(cleaned)

    return LobbySnapshot(lobby=lobby, me=me_text or my_nickname, others=others, all_lines=texts)


def format_snapshot(snap: LobbySnapshot) -> str:
    return (
        f"lobby: {snap.lobby}\n"
        f"me: {snap.me}\n"
        f"others: {snap.others}"
    )
