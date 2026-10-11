"""In-memory diagnostics for one news poll (no SQLite schema).

Layer 1 (poller): counts per source×ticker call —
successful fetch, ``returned`` = ``len(fetch())`` (already post-source-filters;
not raw upstream items), empty-ok vs error, insert / noise / URL-dup / near-dup.

``raw_seen`` / source-filter drop helpers exist for a later layer; inactive when
no diagnostics bound. Helpers are no-ops outside ``bind_diagnostics``.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

# Poller-level outcomes (one per returned item, or call-level error).
IS_NOISE_TITLE = "is_noise_title"
URL_DUPLICATE = "url_duplicate"
NEAR_DUPLICATE = "near_duplicate"
INTEGRITY_ERROR = "integrity_error"

# Reserved for source instrumentation (later layers); safe to import early.
EMPTY_TITLE_OR_LINK = "empty_title_or_link"
TITLE_MATCHES_TICKER = "title_matches_ticker"
PULSE_TARGET_TITLE = "pulse_target_title"
PULSE_BROAD_DIGEST = "pulse_broad_digest"
PULSE_STATUS = "pulse_status"
PULSE_DROP_NICK = "pulse_drop_nick"
PULSE_TICKER_NOT_IN_INSTRUMENTS = "pulse_ticker_not_in_instruments"
PULSE_NO_POST_ID = "pulse_no_post_id"
OUTPUT_LIMIT = "output_limit"
KIND_SKIPPED = "kind_skipped"
NO_ISSUER_MAP = "no_issuer_map"
NO_MATCHING_EVENTS = "no_matching_events"

_POLLER_ITEM_REASONS = frozenset(
    {IS_NOISE_TITLE, URL_DUPLICATE, NEAR_DUPLICATE, INTEGRITY_ERROR}
)

_active: ContextVar[Optional["PollDiagnostics"]] = ContextVar(
    "portfolio_news_poll_diag", default=None
)


@dataclass
class SourceCallStats:
    source: str
    ticker_id: str
    ok: bool = True
    error_kind: str = ""
    error: str = ""
    # Layer 1: items returned by fetch() (opaque upstream).
    returned: int = 0
    # Alias kept for summaries / later layers (= returned at layer 1).
    passed: int = 0
    # Later layer: pre-filter items inside a source (0 until instrumented).
    raw_seen: int = 0
    feed_total: int = 0
    inserted: int = 0
    drops: dict[str, int] = field(default_factory=dict)
    limit_cap: int | None = None
    limit_hit: bool = False

    def add_drop(self, reason: str, n: int = 1) -> None:
        if n <= 0:
            return
        key = (reason or "other").strip() or "other"
        self.drops[key] = self.drops.get(key, 0) + n

    @property
    def dropped(self) -> int:
        return sum(self.drops.values())

    @property
    def poller_dropped(self) -> int:
        return sum(self.drops.get(r, 0) for r in _POLLER_ITEM_REASONS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "ticker_id": self.ticker_id,
            "ok": self.ok,
            "error_kind": self.error_kind,
            "error": self.error,
            "returned": self.returned,
            "passed": self.passed,
            "raw_seen": self.raw_seen,
            "feed_total": self.feed_total,
            "inserted": self.inserted,
            "dropped": self.dropped,
            "drops": dict(sorted(self.drops.items())),
            "limit_cap": self.limit_cap,
            "limit_hit": self.limit_hit,
            "empty_ok": bool(self.ok and self.returned == 0 and not self.error_kind),
        }


@dataclass
class PollDiagnostics:
    calls: list[SourceCallStats] = field(default_factory=list)
    _current: SourceCallStats | None = field(default=None, repr=False)

    def begin_call(self, source: str, ticker_id: str) -> SourceCallStats:
        call = SourceCallStats(
            source=(source or "").strip(),
            ticker_id=(ticker_id or "").strip().upper(),
        )
        self.calls.append(call)
        self._current = call
        return call

    def end_call(self) -> None:
        self._current = None

    def current(self) -> SourceCallStats | None:
        return self._current

    def to_dict(self) -> dict[str, Any]:
        by_source: dict[str, dict[str, Any]] = {}
        by_ticker: dict[str, dict[str, Any]] = {}
        drops_all: dict[str, int] = {}
        source_errors = 0
        empty_ok_calls = 0
        ok_calls = 0
        for c in self.calls:
            if c.ok:
                ok_calls += 1
                if c.returned == 0 and not c.error_kind:
                    empty_ok_calls += 1
            else:
                source_errors += 1
            for reason, n in c.drops.items():
                drops_all[reason] = drops_all.get(reason, 0) + n

            bs = by_source.setdefault(
                c.source,
                {
                    "source": c.source,
                    "returned": 0,
                    "passed": 0,
                    "raw_seen": 0,
                    "inserted": 0,
                    "dropped": 0,
                    "drops": {},
                    "errors": 0,
                    "empty_ok_calls": 0,
                    "ok_calls": 0,
                    "limit_hit": False,
                    "limit_cap": c.limit_cap,
                    "calls": 0,
                },
            )
            bs["returned"] += c.returned
            bs["passed"] += c.passed
            bs["raw_seen"] += c.raw_seen
            bs["inserted"] += c.inserted
            bs["dropped"] += c.dropped
            bs["calls"] += 1
            if c.ok:
                bs["ok_calls"] += 1
                if c.returned == 0 and not c.error_kind:
                    bs["empty_ok_calls"] += 1
            else:
                bs["errors"] += 1
            if c.limit_hit:
                bs["limit_hit"] = True
            if c.limit_cap is not None:
                bs["limit_cap"] = c.limit_cap
            for reason, n in c.drops.items():
                bs["drops"][reason] = bs["drops"].get(reason, 0) + n

            tid = c.ticker_id or "?"
            bt = by_ticker.setdefault(
                tid,
                {
                    "ticker_id": tid,
                    "returned": 0,
                    "passed": 0,
                    "raw_seen": 0,
                    "inserted": 0,
                    "dropped": 0,
                    "drops": {},
                    "errors": 0,
                    "sources": [],
                },
            )
            bt["returned"] += c.returned
            bt["passed"] += c.passed
            bt["raw_seen"] += c.raw_seen
            bt["inserted"] += c.inserted
            bt["dropped"] += c.dropped
            if not c.ok:
                bt["errors"] += 1
            for reason, n in c.drops.items():
                bt["drops"][reason] = bt["drops"].get(reason, 0) + n
            bt["sources"].append(c.to_dict())

        tickers = sorted({c.ticker_id for c in self.calls if c.ticker_id}, key=str)
        summary = {
            "tickers": len(tickers),
            "ok_calls": ok_calls,
            "empty_ok_calls": empty_ok_calls,
            "source_errors": source_errors,
            # returned from fetch(); not raw upstream publications
            "returned": sum(c.returned for c in self.calls),
            "passed_filters": sum(c.passed for c in self.calls),
            "raw_seen": sum(c.raw_seen for c in self.calls),
            "dropped": sum(c.dropped for c in self.calls),
            "inserted": sum(c.inserted for c in self.calls),
            "drops_by_reason": dict(sorted(drops_all.items())),
        }
        return {
            "summary": summary,
            "by_source": sorted(by_source.values(), key=lambda x: x["source"]),
            "by_ticker": by_ticker,
        }


def get_active_diagnostics() -> PollDiagnostics | None:
    return _active.get()


@contextmanager
def bind_diagnostics(diag: PollDiagnostics | None) -> Iterator[PollDiagnostics | None]:
    token = _active.set(diag)
    try:
        yield diag
    finally:
        _active.reset(token)


def _cur() -> SourceCallStats | None:
    diag = _active.get()
    if diag is None:
        return None
    return diag.current()


def diag_feed_total(n: int) -> None:
    call = _cur()
    if call is not None and n > 0:
        call.feed_total = int(n)


def diag_raw_seen(n: int = 1) -> None:
    call = _cur()
    if call is not None and n:
        call.raw_seen += int(n)


def diag_drop(reason: str, n: int = 1) -> None:
    call = _cur()
    if call is not None:
        call.add_drop(reason, n)


def diag_passed(n: int = 1) -> None:
    """Later-layer helper; layer 1 poller overwrites ``passed`` from ``len(fetch())``."""
    call = _cur()
    if call is not None and n:
        call.passed += int(n)


def diag_inserted(n: int = 1) -> None:
    call = _cur()
    if call is not None and n:
        call.inserted += int(n)


def diag_limit(cap: int | None, *, hit: bool) -> None:
    call = _cur()
    if call is None:
        return
    if cap is not None:
        call.limit_cap = int(cap)
    if hit:
        call.limit_hit = True


def diag_error(kind: str, message: str = "") -> None:
    call = _cur()
    if call is None:
        return
    call.ok = False
    call.error_kind = (kind or "error").strip() or "error"
    call.error = (message or "")[:500]


def diag_skip(reason: str, message: str = "") -> None:
    """Successful no-op path (e.g. source N/A for bond) — not an HTTP error."""
    call = _cur()
    if call is None:
        return
    call.ok = True
    call.error_kind = (reason or "").strip()
    call.error = (message or "")[:500]
