from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol


@dataclass
class RawNews:
    title: str
    url: str
    source: str
    published_at: Optional[datetime] = None


class NewsSource(Protocol):
    name: str

    def fetch(self, ticker_id: str, search_query: str, kind: str) -> list[RawNews]:
        ...
