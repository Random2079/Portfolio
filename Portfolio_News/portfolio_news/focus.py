"""KB — «Смотрю» / остальное.

Default = Hold. Focus = at most one ticker the user watches.
Toast/news prefer that ticker when set.
"""



from __future__ import annotations



from typing import Iterable, Optional



from sqlalchemy import select

from sqlalchemy.orm import Session



from portfolio_news.db import TickerFocus



TIER_FOCUS = "focus"

TIER_HOLD = "hold"





def list_focus_tickers(session: Session) -> list[str]:

    rows = session.scalars(select(TickerFocus.ticker_id).order_by(TickerFocus.ticker_id)).all()

    return [str(t).upper() for t in rows]





def is_focus(session: Session, ticker_id: str) -> bool:

    tid = (ticker_id or "").strip().upper()

    if not tid:

        return False

    return session.get(TickerFocus, tid) is not None





def set_focus(session: Session, ticker_id: str, *, focus: bool) -> str:
    """Mark ticker Focus or Hold. Focus is exclusive: at most one ticker."""
    tid = (ticker_id or "").strip().upper()
    if not tid:
        raise ValueError("empty ticker")

    if focus:
        for row in list(session.scalars(select(TickerFocus)).all()):
            if str(row.ticker_id).upper() != tid:
                session.delete(row)
        if session.get(TickerFocus, tid) is None:
            session.add(TickerFocus(ticker_id=tid))
        session.commit()
        return TIER_FOCUS

    row = session.get(TickerFocus, tid)
    if row is not None:
        session.delete(row)
        session.commit()
    return TIER_HOLD





def replace_focus(session: Session, tickers: Iterable[str]) -> list[str]:

    """Replace entire Focus set. Empty list = all Hold."""

    wanted = sorted({(t or "").strip().upper() for t in tickers if (t or "").strip()})

    existing = list(session.scalars(select(TickerFocus)).all())

    for row in existing:

        session.delete(row)

    for tid in wanted:

        session.add(TickerFocus(ticker_id=tid))

    session.commit()

    return wanted





def notify_allowed(ticker_id: str, focus_ids: Optional[set[str]]) -> bool:

    """If focus set non-empty, toast only for Focus; else all tickers."""

    if not focus_ids:

        return True

    return (ticker_id or "").strip().upper() in focus_ids


