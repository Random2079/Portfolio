"""K8: merged deal history — dedupe, kinds, filters, CSV."""

from __future__ import annotations

from portfolio_news.ops_history import (
    annotate_kinds,
    filter_rows,
    local_day,
    merge_rows,
    summarize,
    to_csv,
)
from portfolio_news.snowball_ledger import trades_from_journal


def _bcs(ticker, day_stamp, side="buy", qty=1.0, price=100.0, cc="TQBR"):
    return {
        "ticker": ticker,
        "class_code": cc,
        "side": side,
        "quantity": qty,
        "price": price,
        "volume": qty * price,
        "executed_at": day_stamp,
        "day": local_day(day_stamp),
        "source": "bcs",
    }


def _jrn(ticker, day, side="buy", qty=1.0, price=100.0):
    return {
        "ticker": ticker,
        "class_code": "",
        "side": side,
        "quantity": qty,
        "price": price,
        "volume": qty * price,
        "executed_at": f"{day}T00:00:00+05:00",
        "day": day,
        "source": "journal",
    }


def test_local_day_shifts_utc_into_yekaterinburg():
    # 2026-09-03 21:25 local is still 16:25 UTC the same day
    assert local_day("2026-09-03T16:25:43Z") == "2026-09-03"
    # late UTC evening already belongs to the next local day
    assert local_day("2026-09-03T20:10:00Z") == "2026-09-04"


def test_merge_prefers_bcs_and_drops_journal_twin():
    bcs = [_bcs("RU000A10C8C0", "2026-09-03T16:25:43Z", price=98.08)]
    # same deal in the journal: rubles instead of percent of par
    jrn = [_jrn("RU000A10C8C0", "2026-09-03", price=984.62)]
    rows = merge_rows(bcs, jrn)
    assert len(rows) == 1
    assert rows[0]["source"] == "bcs"


def test_merge_keeps_two_same_size_deals_on_one_day():
    bcs = [_bcs("SBER", "2026-05-01T09:00:00Z", qty=10.0)]
    jrn = [_jrn("SBER", "2026-05-01", qty=10.0), _jrn("SBER", "2026-05-01", qty=10.0)]
    rows = merge_rows(bcs, jrn)
    # one journal row is the BCS twin, the other is a genuine second deal
    assert len(rows) == 2
    assert sorted(r["source"] for r in rows) == ["bcs", "journal"]


def test_merge_sorts_newest_first_across_sources():
    rows = merge_rows(
        [_bcs("SBER", "2025-01-10T09:00:00Z")],
        [_jrn("LKOH", "2026-02-02"), _jrn("MOEX", "2024-03-03")],
    )
    assert [r["ticker"] for r in rows] == ["LKOH", "SBER", "MOEX"]


def test_annotate_kinds_puts_bond_price_in_rubles():
    rows = [_bcs("RU000A10C8C0", "2026-09-03T16:25:43Z", price=98.08, cc="TQCB")]
    annotate_kinds(rows, {})
    assert rows[0]["kind"] == "bond"
    assert rows[0]["price_raw"] == 98.08
    assert rows[0]["price"] == 980.8


def test_annotate_kinds_uses_db_kind_for_funds_on_tqbr():
    rows = [_bcs("BCSR", "2026-01-22T09:00:00Z")]
    annotate_kinds(rows, {"BCSR": "fund"})
    assert rows[0]["kind"] == "fund"


def test_filter_rows_by_kind_and_window():
    rows = [
        _jrn("SBER", "2024-05-05"),
        _jrn("RU000A106Y21", "2024-11-05"),
        _jrn("LKOH", "2026-01-05"),
    ]
    annotate_kinds(rows, {})
    only_2024 = filter_rows(rows, date_from="2024-01-01", date_to="2024-12-31")
    assert {r["ticker"] for r in only_2024} == {"SBER", "RU000A106Y21"}
    bonds = filter_rows(rows, kinds=["bond"])
    assert [r["ticker"] for r in bonds] == ["RU000A106Y21"]
    assert filter_rows(rows, ticker="lkoh")[0]["ticker"] == "LKOH"


def test_filter_rows_by_company_name():
    rows = [
        _jrn("SBER", "2024-05-05"),
        _jrn("LKOH", "2024-06-01"),
        _jrn("OZON", "2024-07-01"),
    ]
    annotate_kinds(rows, {})
    names = {
        "SBER": "Сбербанк России",
        "LKOH": "ЛУКОЙЛ",
        "OZON": "Озон",
    }
    hit = filter_rows(rows, ticker="сбер", names=names)
    assert [r["ticker"] for r in hit] == ["SBER"]
    hit2 = filter_rows(rows, ticker="лукой", names=names)
    assert [r["ticker"] for r in hit2] == ["LKOH"]
    # ticker substring still works
    assert filter_rows(rows, ticker="oz", names=names)[0]["ticker"] == "OZON"


def test_filter_rows_empty_kinds_means_no_filter():
    rows = [_jrn("SBER", "2024-05-05")]
    annotate_kinds(rows, {})
    assert len(filter_rows(rows, kinds=[])) == 1


def test_summarize_counts_years_and_volumes():
    rows = [
        _jrn("SBER", "2024-05-05", side="buy", qty=2.0, price=100.0),
        _jrn("SBER", "2026-05-05", side="sell", qty=1.0, price=150.0),
    ]
    annotate_kinds(rows, {})
    s = summarize(rows)
    assert s["years"] == ["2024", "2026"]
    assert s["counts"]["equity"] == 2
    assert s["bought_volume"] == 200.0
    assert s["sold_volume"] == 150.0


def test_trades_from_journal_reads_buy_sell_only():
    events = [
        {
            "Event": "BUY",
            "Date": "2024-01-05 00:00:00",
            "Symbol": "irao",
            "Price": "4,189",
            "Quantity": "200",
            "Currency": "RUB",
            "FeeTax": "0",
            "NKD": "0",
        },
        {"Event": "DIVIDEND", "Date": "2024-02-05 00:00:00", "Symbol": "IRAO"},
    ]
    rows = trades_from_journal(events)
    assert len(rows) == 1
    row = rows[0]
    assert row["ticker"] == "IRAO"
    assert row["side"] == "buy"
    assert row["day"] == "2024-01-05"
    assert row["executed_at"].endswith("+05:00")
    assert round(row["volume"], 2) == 837.80


def test_trades_from_journal_adds_nkd_to_bond_volume():
    events = [
        {
            "Event": "BUY",
            "Date": "2026-09-03 19:25:43",
            "Symbol": "RU000A10C8C0",
            "Price": "980,8",
            "Quantity": "1",
            "NKD": "3,82",
        }
    ]
    row = trades_from_journal(events)[0]
    assert round(row["volume"], 2) == 984.62
    assert row["executed_at"] == "2026-09-03T19:25:43+05:00"


def test_csv_is_semicolon_separated_with_ru_decimals():
    rows = [_jrn("SBER", "2024-05-05", qty=2.0, price=100.5)]
    annotate_kinds(rows, {})
    text = to_csv(rows)
    head, first = text.splitlines()[:2]
    assert head.startswith("Дата;Время;Тикер;Тип")
    assert "SBER" in first
    assert "100,5" in first
    assert first.count(";") == head.count(";")
