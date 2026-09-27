import { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { API_BASE, getJson, putJson } from "./api";
import {
  LIST_PREVIEW,
  countPapersByKind,
  fmtPosBreakdown,
  groupHoldingsByAssetClass,
  isCashHolding,
  paperId,
  sumField,
} from "./holdings";
import { fmtPct, fmtRub, pnlClass, qtyFmt } from "./format";
import TickerReview from "./TickerReview";
import "./App.css";

export default function App() {
  const [health, setHealth] = useState(null);
  const [day, setDay] = useState(null);
  const [snap, setSnap] = useState(null);
  const [focusTickers, setFocusTickers] = useState([]);
  const [selected, setSelected] = useState("");
  const [previewOpen, setPreviewOpen] = useState({});
  const [error, setError] = useState("");
  const [holdingsNote, setHoldingsNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [focusBusy, setFocusBusy] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setHoldingsNote("");
    try {
      const [h, d, holdingsSnap, focus] = await Promise.all([
        getJson("/api/health"),
        getJson("/api/day?top=5"),
        getJson("/api/holdings"),
        getJson("/api/focus").catch(() => ({ tickers: [] })),
      ]);
      setHealth(h);
      setDay(d);
      setSnap(holdingsSnap);
      setFocusTickers(
        (focus?.tickers || []).map((t) => String(t).trim().toUpperCase()).filter(Boolean)
      );

      if (!holdingsSnap?.configured) {
        setHoldingsNote("Нет BCS токена в .env");
      } else if (
        !holdingsSnap.ok &&
        !(holdingsSnap.holdings && holdingsSnap.holdings.length)
      ) {
        setHoldingsNote(
          (holdingsSnap.error || "БКС не ответил") +
            " Кэша позиций нет."
        );
      } else if (
        holdingsSnap.stale ||
        (holdingsSnap.error && holdingsSnap.holdings?.length)
      ) {
        setHoldingsNote(
          (holdingsSnap.error || "БКС недоступен") +
            " Позиции из последнего удачного ответа."
        );
      }
    } catch (e) {
      setError(String(e.message || e));
      setHealth(null);
      setDay(null);
      setSnap(null);
      setFocusTickers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const holdings = snap?.holdings || [];
  const papers = useMemo(
    () => holdings.filter((h) => !isCashHolding(h)),
    [holdings]
  );
  const groups = useMemo(() => groupHoldingsByAssetClass(papers), [papers]);
  const focusSet = useMemo(() => new Set(focusTickers), [focusTickers]);
  const focusId = focusTickers[0] || "";

  const totalPnl = useMemo(() => {
    if (snap?.pnl != null) return snap.pnl;
    return sumField(papers, "pnl");
  }, [snap, papers]);
  const totalCost = useMemo(() => sumField(papers, "cost_value"), [papers]);
  const totalPnlPct = useMemo(() => {
    if (snap?.pnl_pct != null) return snap.pnl_pct;
    if (totalPnl != null && totalCost) return (totalPnl / totalCost) * 100;
    return null;
  }, [snap, totalPnl, totalCost]);
  const breakdown = useMemo(
    () => fmtPosBreakdown(countPapersByKind(papers)),
    [papers]
  );

  const selectTicker = useCallback((tid) => {
    const id = String(tid || "")
      .trim()
      .toUpperCase();
    if (!id) return;
    setSelected(id);
  }, []);

  const toggleFocus = useCallback(
    async (ticker, wantFocus) => {
      const tid = String(ticker || "")
        .trim()
        .toUpperCase();
      if (!tid) return;
      setFocusBusy(tid);
      try {
        await putJson(`/api/focus/${encodeURIComponent(tid)}`, {
          tier: wantFocus ? "focus" : "hold",
        });
        // KB: at most one «Смотрю»
        setFocusTickers(wantFocus ? [tid] : []);
        if (wantFocus) setSelected(tid);
      } catch (e) {
        console.warn("focus toggle failed", e);
      } finally {
        setFocusBusy("");
      }
    },
    []
  );

  const apiOk = !!(health && (health.ok === true || health.ok === "true"));
  const top = (day && day.top) || [];
  const apiLabel = API_BASE || (typeof window !== "undefined" ? window.location.origin : "этот сервер");
  const apiHref = API_BASE || "/";

  return (
    <div className="shell">
      <motion.header
        className="top"
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      >
        <div>
          <p className="eyebrow">IDEA-003 · React R2</p>
          <h1 className="brand">Portfolio News</h1>
          <p className="tagline">
            Утренний терминал · API{" "}
            <a href={apiHref} target="_blank" rel="noreferrer">
              {apiLabel}
            </a>
          </p>
        </div>
        <div className="top-actions">
          <span className={"pill " + (apiOk ? "ok" : "bad")}>
            {loading ? "…" : apiOk ? "API ok" : "API down"}
          </span>
          <button type="button" className="btn" onClick={load} disabled={loading}>
            Обновить
          </button>
        </div>
      </motion.header>

      {error ? (
        <motion.div
          className="banner err"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          Нет связи с API. В{" "}
          <code>Portfolio_News</code> запусти:{" "}
          <code>python -m portfolio_news serve</code>
          <br />
          <span className="muted">{error}</span>
        </motion.div>
      ) : null}

      {!error && holdingsNote ? (
        <div className="banner warn">
          <span className="muted">{holdingsNote}</span>
        </div>
      ) : null}

      <motion.section
        className="kpi-row"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.08, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      >
        <article className="kpi">
          <h2>День</h2>
          <p className={"v " + pnlClass(day && day.day_rub)}>
            {loading ? "…" : fmtRub(day && day.day_rub, { signed: true })}
          </p>
          <p className={"s " + pnlClass(day && day.day_pct)}>
            {loading ? "" : fmtPct(day && day.day_pct)}
            {day && day.stale ? " · кэш" : ""}
          </p>
        </article>
        <article className="kpi">
          <h2>Стоимость бумаг</h2>
          <p className="v">
            {loading
              ? "…"
              : day && day.total_value != null
                ? fmtRub(day.total_value)
                : snap && snap.total_value != null
                  ? fmtRub(snap.total_value)
                  : "—"}
          </p>
          <p className="s muted">
            {day && day.missing
              ? "без котировок: " + day.missing
              : papers.length
                ? `${papers.length} поз · ${breakdown}`
                : "MOEX × BCS"}
          </p>
        </article>
        <article className="kpi wide">
          <h2>Кто двинул день</h2>
          {loading ? (
            <p className="muted">грузим…</p>
          ) : top.length ? (
            <ul className="movers">
              {top.map((r, i) => {
                const tid = String(r.ticker || "")
                  .trim()
                  .toUpperCase();
                const active = tid && tid === selected;
                return (
                  <motion.li
                    key={tid || i}
                    role="button"
                    tabIndex={0}
                    className={active ? "active" : ""}
                    title={tid ? `Выбрать ${tid} (разбор в R2)` : undefined}
                    onClick={() => selectTicker(tid)}
                    onKeyDown={(ev) => {
                      if (ev.key === "Enter" || ev.key === " ") {
                        ev.preventDefault();
                        selectTicker(tid);
                      }
                    }}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.12 + i * 0.05 }}
                  >
                    <span className="t">{r.ticker}</span>
                    <span className={"rub " + pnlClass(r.day_rub)}>
                      {fmtRub(r.day_rub, { signed: true })}
                    </span>
                    <span className="pct muted">{fmtPct(r.day_pct)}</span>
                  </motion.li>
                );
              })}
            </ul>
          ) : (
            <p className="muted">Нет топа (выходной / нет Δ)</p>
          )}
        </article>
      </motion.section>

      <motion.section
        className="holdings"
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.18, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="holdings-head">
          <div>
            <h2>Позиции</h2>
            <p className="muted">
              {loading
                ? "грузим…"
                : papers.length
                  ? `${papers.length} · ${breakdown}`
                  : "Нет позиций в ответе БКС"}
              {totalPnl != null ? (
                <>
                  {" · PnL "}
                  <span className={pnlClass(totalPnl)}>
                    {fmtRub(totalPnl, { signed: true })}
                    {totalPnlPct != null ? ` · ${fmtPct(totalPnlPct)}` : ""}
                  </span>
                </>
              ) : null}
            </p>
          </div>
          <div className="focus-chip">
            <span className="muted">Смотрю</span>
            <strong>{focusId || "—"}</strong>
            {selected && selected !== focusId ? (
              <button
                type="button"
                className="btn sm"
                disabled={!!focusBusy}
                onClick={() => toggleFocus(selected, true)}
              >
                → {selected}
              </button>
            ) : null}
            {focusId ? (
              <button
                type="button"
                className="btn sm ghost"
                disabled={!!focusBusy}
                onClick={() => toggleFocus(focusId, false)}
              >
                снять
              </button>
            ) : null}
          </div>
        </div>

        {selected ? (
          <p className="selection-bar">
            Выбрано: <strong>{selected}</strong>
            <span className="muted"> · разбор ниже</span>
          </p>
        ) : (
          <p className="selection-bar muted">
            Кликни тикер в топе дня или в списке — откроется разбор.
          </p>
        )}

        {loading ? (
          <p className="muted pad">грузим позиции…</p>
        ) : !groups.length ? (
          <p className="muted pad">Пусто.</p>
        ) : (
          <div className="asset-groups">
            {groups.map((g) => {
              const expanded = previewOpen[g.key] === true;
              const previewOn = g.rows.length > LIST_PREVIEW;
              const visible =
                !previewOn || expanded
                  ? g.rows
                  : g.rows.slice(0, LIST_PREVIEW);
              const rest = g.rows.length - LIST_PREVIEW;
              return (
                <div key={g.key} className="asset-group">
                  <h3>
                    {g.title}
                    <span className="muted"> · {g.rows.length}</span>
                  </h3>
                  <ul className="pos-list">
                    <AnimatePresence initial={false}>
                      {visible.map((h, i) => {
                        const tid = paperId(h);
                        const active = tid && tid === selected;
                        const isFocus = tid && focusSet.has(tid);
                        const title =
                          h.name || h.ticker || h.sec_code || "—";
                        return (
                          <motion.li
                            key={tid || `${g.key}-${i}`}
                            layout
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: 0.2 }}
                            className={
                              "pos-row" +
                              (active ? " active" : "") +
                              (isFocus ? " focus" : "")
                            }
                          >
                            <button
                              type="button"
                              className="pos-main"
                              onClick={() => selectTicker(tid)}
                              title={tid ? `Выбрать ${tid}` : undefined}
                            >
                              <span className="pos-id">
                                <strong>{tid || "?"}</strong>
                                {isFocus ? (
                                  <span className="badge-focus">смотрю</span>
                                ) : null}
                                <span className="name muted">{title}</span>
                              </span>
                              <span className="pos-qty muted">
                                {qtyFmt(h.quantity)}
                              </span>
                              <span className="pos-val">
                                {fmtRub(h.market_value)}
                              </span>
                              <span
                                className={
                                  "pos-pnl " + pnlClass(h.pnl)
                                }
                              >
                                {fmtRub(h.pnl, { signed: true })}
                              </span>
                            </button>
                            <button
                              type="button"
                              className={
                                "btn sm focus-btn" +
                                (isFocus ? " on" : "")
                              }
                              disabled={!!focusBusy || !tid}
                              title={
                                isFocus
                                  ? "Снять «Смотрю»"
                                  : "Поставить «Смотрю»"
                              }
                              onClick={() =>
                                toggleFocus(tid, !isFocus)
                              }
                            >
                              {isFocus ? "★" : "☆"}
                            </button>
                          </motion.li>
                        );
                      })}
                    </AnimatePresence>
                  </ul>
                  {previewOn ? (
                    <button
                      type="button"
                      className="btn sm more"
                      onClick={() =>
                        setPreviewOpen((prev) => ({
                          ...prev,
                          [g.key]: !expanded,
                        }))
                      }
                    >
                      {expanded
                        ? "Свернуть список"
                        : `Ещё ${rest} · ${g.title.toLowerCase()} ▾`}
                    </button>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </motion.section>

      {selected ? (
        <TickerReview
          ticker={selected}
          holdings={holdings}
          totalValue={snap?.total_value ?? null}
        />
      ) : null}

      <motion.footer
        className="foot"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.35 }}
      >
        <p>
          <strong>R2</strong> — разбор: карточка + LWC + KS. Бэкап ванили:{" "}
          <a href="http://127.0.0.1:8765/" target="_blank" rel="noreferrer">
            127.0.0.1:8765
          </a>
          . Дальше R3: новости.
        </p>
      </motion.footer>
    </div>
  );
}
