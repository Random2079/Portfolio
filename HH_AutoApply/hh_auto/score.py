from __future__ import annotations

import re
from collections import Counter
from typing import Any


def _norm(s: str) -> str:
    return s.casefold()


def vacancy_blob(v: dict[str, Any]) -> str:
    parts = [
        v.get("title") or "",
        v.get("requirement") or "",
        v.get("responsibility") or "",
        v.get("company") or "",
    ]
    return " ".join(parts)


def score_vacancy(v: dict[str, Any], tags: list[str]) -> tuple[int, list[str]]:
    blob = _norm(vacancy_blob(v))
    hits: list[str] = []
    for tag in tags:
        t = tag.strip()
        if not t:
            continue
        if _norm(t) in blob:
            hits.append(t)
            continue
        if len(t) <= 3:
            if re.search(rf"\b{_norm(t)}\b", blob):
                hits.append(t)
    return len(hits), hits


def rank_vacancies(
    vacancies: list[dict[str, Any]],
    tags: list[str],
    min_score: int,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for v in vacancies:
        sc, hits = score_vacancy(v, tags)
        row = dict(v)
        row["score"] = sc
        row["hits"] = hits
        if sc >= min_score:
            ranked.append(row)
    ranked.sort(key=lambda x: (-x["score"], x.get("title") or ""))
    return ranked


def keywords_table(
    vacancies: list[dict[str, Any]],
    tags: list[str],
) -> list[tuple[str, str, int]]:
    """(фраза_из_вакансий_как_тег, инструмент/стек, частота)."""
    ctr: Counter[str] = Counter()
    for v in vacancies:
        blob = _norm(vacancy_blob(v))
        for tag in tags:
            t = tag.strip()
            if not t:
                continue
            if _norm(t) in blob or (len(t) <= 3 and re.search(rf"\b{_norm(t)}\b", blob)):
                ctr[t] += 1
    rows = [(tag, tag, n) for tag, n in ctr.most_common() if n > 0]
    return rows
