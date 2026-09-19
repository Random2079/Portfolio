from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Ticker(Base):
    __tablename__ = "tickers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), default="")
    isin: Mapped[str] = mapped_column(String(32), default="")
    kind: Mapped[str] = mapped_column(String(16), default="equity")  # equity | bond
    category: Mapped[str] = mapped_column(String(128), default="")
    search_query: Mapped[str] = mapped_column(String(256), default="")

    news: Mapped[list["NewsItem"]] = relationship(back_populates="ticker")


class NewsItem(Base):
    __tablename__ = "news"
    __table_args__ = (UniqueConstraint("url", name="uq_news_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker_id: Mapped[str] = mapped_column(String(64), ForeignKey("tickers.id"), index=True)
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(1024))
    source: Mapped[str] = mapped_column(String(64), default="")
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notified: Mapped[int] = mapped_column(Integer, default=0)  # 0/1

    ticker: Mapped[Ticker] = relationship(back_populates="news")


class BcsOperation(Base):
    """Cached BCS deal (K2). Primary key = broker deal_id or fingerprint."""

    __tablename__ = "bcs_operations"

    deal_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(64), default="", index=True)
    class_code: Mapped[str] = mapped_column(String(32), default="")
    side: Mapped[str] = mapped_column(String(16), default="")
    quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    volume: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    commission: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(16), default="RUB")
    executed_at: Mapped[str] = mapped_column(String(64), default="", index=True)
    updated_at: Mapped[float] = mapped_column(Float, default=0.0)


class TickerFocus(Base):
    """KB: tickers marked Focus (остальные = Hold по умолчанию)."""

    __tablename__ = "ticker_focus"

    ticker_id: Mapped[str] = mapped_column(String(64), primary_key=True)


class DaySnapshot(Base):
    """KA: last computed day attribution (UI reads this; MOEX updates in background)."""

    __tablename__ = "day_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # singleton = 1
    payload_json: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[float] = mapped_column(Float, default=0.0)
    ok: Mapped[int] = mapped_column(Integer, default=0)  # 0/1


class CalendarCache(Base):
    """K7: last built payout calendar (UI reads this; MOEX only in background)."""

    __tablename__ = "calendar_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # singleton = 1
    payload_json: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[float] = mapped_column(Float, default=0.0)
    ok: Mapped[int] = mapped_column(Integer, default=0)  # 0/1


class CapitalDay(Base):
    """K6: one portfolio total per local calendar day (Asia/Yekaterinburg)."""

    __tablename__ = "capital_days"

    day: Mapped[str] = mapped_column(String(10), primary_key=True)  # YYYY-MM-DD
    total_value: Mapped[float] = mapped_column(Float, default=0.0)
    cash: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(16), default="RUB")
    updated_at: Mapped[float] = mapped_column(Float, default=0.0)


class MoexClose(Base):
    """K6: cached MOEX close per (ticker, day). Survives ISS timeouts across rebuilds."""

    __tablename__ = "moex_closes"

    ticker: Mapped[str] = mapped_column(String(64), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)  # candle date
    close: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[float] = mapped_column(Float, default=0.0)


class ChartCandleCache(Base):
    """K3: full OHLCV candle series per ticker for разбор (avoid ISS every click)."""

    __tablename__ = "chart_candle_cache"

    ticker: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[float] = mapped_column(Float, default=0.0)
    ok: Mapped[int] = mapped_column(Integer, default=0)


class ReviewCache(Base):
    """KS: last review/checkpoint payload per ticker (cache-first UI)."""

    __tablename__ = "review_cache"

    ticker: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[float] = mapped_column(Float, default=0.0)
    ok: Mapped[int] = mapped_column(Integer, default=0)


class SmartlabFundamentalsCache(Base):
    """KS: Smart-Lab fundamental table universe (singleton)."""

    __tablename__ = "smartlab_fundamentals_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # singleton = 1
    payload_json: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[float] = mapped_column(Float, default=0.0)
    ok: Mapped[int] = mapped_column(Integer, default=0)


class DohodBondCache(Base):
    """KS: Dohod getbondinfo payload per ISIN."""

    __tablename__ = "dohod_bond_cache"

    isin: Mapped[str] = mapped_column(String(32), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[float] = mapped_column(Float, default=0.0)
    ok: Mapped[int] = mapped_column(Integer, default=0)


class FundTerUniverseCache(Base):
    """KS: CBR PIF showcase Excel → TER/fees by ISIN (universe blob)."""

    __tablename__ = "fund_ter_universe_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[float] = mapped_column(Float, default=0.0)
    ok: Mapped[int] = mapped_column(Integer, default=0)
    source_as_of: Mapped[str] = mapped_column(String(128), default="")


def make_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, future=True, connect_args=connect_args)


def make_session_factory(database_url: str):
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
