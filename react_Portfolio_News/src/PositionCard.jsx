import { useEffect, useState } from "react";
import { getJson } from "./api";
import {
  fmtDateShort,
  fmtPct,
  fmtRub,
  moneyShow,
  pnlClass,
  qtyFmt,
  shortErr,
} from "./format";
import { isCashHolding, paperId } from "./holdings";

/** Optimistic card from holdings list while /api/position loads. */
export function posCardFromHoldings(tid, holdings, totalValue) {
  const want = String(tid || "")
    .trim()
    .toUpperCase();
  if (!want || !holdings?.length) return null;
  const h = holdings.find((x) => paperId(x) === want);
  if (!h || isCashHolding(h)) return null;

  let pf = totalValue;
  if (pf == null) {
    let s = 0;
    let ok = false;
    for (const x of holdings) {
      if (isCashHolding(x)) continue;
      if (x.market_value != null) {
        s += Number(x.market_value);
        ok = true;
      }
    }
    pf = ok ? s : null;
  }
  const mv = h.market_value != null ? Number(h.market_value) : null;
  const weight =
    mv != null && pf != null && pf > 0 ? (mv / pf) * 100 : null;
  const avg = h.avg_price != null ? Number(h.avg_price) : null;
  const cur = h.market_price != null ? Number(h.market_price) : null;
  const vs =
    avg != null && cur != null
      ? {
          diff: cur - avg,
          diff_pct: avg !== 0 ? ((cur - avg) / avg) * 100 : null,
        }
      : {};

  return {
    ok: true,
    ticker: want,
    name: h.name || "",
    qty: h.quantity,
    avg_price: avg,
    current_price: cur,
    current_price_source: cur != null ? "bcs" : "",
    avg_vs_price: vs,
    market_value: mv,
    cost_value: h.cost_value,
    unrealized_pnl: h.pnl,
    unrealized_pnl_pct: h.pnl_pct,
    first_buy: null,
    last_buy: null,
    n_buys: 0,
    weight_pct: weight,
    currency: h.currency || "RUB",
    _local: true,
  };
}

/**
 * K4 position card — /api/position/{ticker}
 * @param {{ ticker: string, holdings?: object[], totalValue?: number|null }} props
 */
export default function PositionCard({ ticker, holdings, totalValue }) {
  const tid = String(ticker || "")
    .trim()
    .toUpperCase();
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!tid) {
      setData(null);
      setErr("");
      setLoading(false);
      return;
    }
    let cancelled = false;
    const local = posCardFromHoldings(tid, holdings, totalValue);
    if (local) setData(local);
    else setData(null);
    setErr("");
    setLoading(true);

    (async () => {
      try {
        const card = await getJson(
          `/api/position/${encodeURIComponent(tid)}`
        );
        if (cancelled) return;
        setData(card);
        if (!card?.ok) setErr(shortErr(card?.error || "Нет карточки"));
        else setErr("");
      } catch (e) {
        if (cancelled) return;
        if (!local) {
          setData(null);
          setErr(shortErr(e.message || e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [tid, holdings, totalValue]);

  if (!tid) {
    return (
      <section className="pos-card">
        <h3>Карточка бумаги</h3>
        <p className="pos-empty">Кликни тикер — avg, покупки, PnL, доля.</p>
      </section>
    );
  }

  const ok = data?.ok;
  const name = data?.name ? ` · ${data.name}` : "";
  const staleBit = data?._local
    ? " · из списка…"
    : data?.stale
      ? " · кэш"
      : "";
  const vs = data?.avg_vs_price || {};

  const cells = ok
    ? [
        { k: "Кол-во", v: qtyFmt(data.qty) },
        { k: "Avg", v: moneyShow(data.avg_price) },
        {
          k: "Цена сейчас",
          v: moneyShow(data.current_price),
          s: data.current_price_source
            ? `источник: ${data.current_price_source}`
            : "",
        },
        {
          k: "Avg vs цена",
          v: fmtRub(vs.diff, { signed: true, digits: 2 }),
          s: vs.diff_pct != null ? fmtPct(vs.diff_pct) : "",
          cls: pnlClass(vs.diff),
        },
        {
          k: "Unrealized PnL",
          v: fmtRub(data.unrealized_pnl, { signed: true }),
          s:
            data.unrealized_pnl_pct != null
              ? fmtPct(data.unrealized_pnl_pct)
              : "",
          cls: pnlClass(data.unrealized_pnl),
        },
        {
          k: "Стоимость",
          v: moneyShow(data.market_value),
          s:
            data.weight_pct != null
              ? `доля ${Number(data.weight_pct).toLocaleString("ru-RU", {
                  maximumFractionDigits: 2,
                })}%`
              : "",
        },
        {
          k: "Первая покупка",
          v: fmtDateShort(data.first_buy),
          s: data.n_buys ? `покупок: ${data.n_buys}` : "",
        },
        { k: "Последняя покупка", v: fmtDateShort(data.last_buy) },
      ]
    : [];

  return (
    <section className="pos-card" aria-live="polite">
      <h3>
        Карточка · {tid}
        {name}
        {staleBit}
      </h3>
      {!ok && (err || loading) ? (
        <p className={err ? "pos-empty err" : "pos-empty"}>
          {loading && !err ? "Загрузка цифр…" : err}
        </p>
      ) : null}
      {ok ? (
        <div className="pos-grid">
          {cells.map((c) => (
            <div className="cell" key={c.k}>
              <div className="k">{c.k}</div>
              <div className={"v" + (c.cls ? ` ${c.cls}` : "")}>{c.v}</div>
              {c.s ? (
                <div className={"s" + (c.cls ? ` ${c.cls}` : "")}>{c.s}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
