import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { getJson } from "./api";
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
import { navHash, navKey, parseNavHash, viewFromState } from "./navHistory";
import TickerLogo from "./TickerLogo";
import TickerReview from "./TickerReview";
import CapitalChart from "./CapitalChart";
import NewsFeed from "./NewsFeed";
import OpsPanel from "./OpsPanel";
import CalendarPanel from "./CalendarPanel";
import "./App.css";

export default function App() {
  const [tab, setTab] = useState(() => parseNavHash().tab);
  const [day, setDay] = useState(null);
  const [snap, setSnap] = useState(null);
  const [selected, setSelected] = useState(() => parseNavHash().selected);
  const [previewOpen, setPreviewOpen] = useState({});
  const [error, setError] = useState("");
  const [holdingsNote, setHoldingsNote] = useState("");
  const [loading, setLoading] = useState(true);
  const reviewRef = useRef(null);
  const scrollAfterSelect = useRef(false);
  const navBoot = useRef(true);
  const navFromPop = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setHoldingsNote("");
    try {
      const [d, holdingsSnap] = await Promise.all([
        getJson("/api/day?top=5"),
        getJson("/api/holdings"),
      ]);
      setDay(d);
      setSnap(holdingsSnap);

      if (!holdingsSnap?.configured) {
        setHoldingsNote("Нет BCS токена в .env");
      } else if (
        !holdingsSnap.ok &&
        !(holdingsSnap.holdings && holdingsSnap.holdings.length)
      ) {
        setHoldingsNote(
          (holdingsSnap.error || "БКС не ответил") + " Кэша позиций нет."
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
      setDay(null);
      setSnap(null);
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
  const cashRows = useMemo(
    () => holdings.filter((h) => isCashHolding(h)),
    [holdings]
  );
  const groups = useMemo(() => groupHoldingsByAssetClass(papers), [papers]);

  /** KPI totals — same as vanilla applyDashboard (holdings snap, not day.total_value). */
  const totalValue = useMemo(() => {
    if (snap?.total_value != null) return snap.total_value;
    return sumField(holdings, "market_value");
  }, [snap, holdings]);
  const totalPnl = useMemo(() => {
    if (snap?.pnl != null) return snap.pnl;
    return sumField(holdings, "pnl");
  }, [snap, holdings]);
  const totalCost = useMemo(() => sumField(holdings, "cost_value"), [holdings]);
  const totalPnlPct = useMemo(() => {
    if (snap?.pnl_pct != null) return snap.pnl_pct;
    if (totalPnl != null && totalCost) return (totalPnl / totalCost) * 100;
    return null;
  }, [snap, totalPnl, totalCost]);
  const cashVal = useMemo(() => {
    const fromRows = sumField(cashRows, "market_value");
    if (fromRows != null) return fromRows;
    if (snap?.cash != null && !Number.isNaN(Number(snap.cash))) {
      return Number(snap.cash);
    }
    return null;
  }, [cashRows, snap]);
  const breakdown = useMemo(
    () => fmtPosBreakdown(countPapersByKind(papers)),
    [papers]
  );
  /** MSK Sat/Sun — как ванильный dayMktNote */
  const moexWeekend = useMemo(() => {
    try {
      const parts = new Intl.DateTimeFormat("en-US", {
        timeZone: "Europe/Moscow",
        weekday: "short",
      }).formatToParts(new Date());
      const wd = parts.find((p) => p.type === "weekday")?.value;
      return wd === "Sat" || wd === "Sun";
    } catch {
      const d = new Date().getDay();
      return d === 0 || d === 6;
    }
  }, []);

  const selectTicker = useCallback(
    (tid) => {
      const id = String(tid || "")
        .trim()
        .toUpperCase();
      if (!id) return;
      if (id === selected && tab === "home") {
        reviewRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
        return;
      }
      scrollAfterSelect.current = true;
      setSelected(id);
      if (tab !== "home") setTab("home");
    },
    [tab, selected]
  );

  useEffect(() => {
    if (!selected || tab !== "home" || !scrollAfterSelect.current) return;
    scrollAfterSelect.current = false;
    const t = window.setTimeout(() => {
      reviewRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }, 80);
    return () => window.clearTimeout(t);
  }, [selected, tab]);

  /** Browser / mouse Back·Forward via History API (hash under /app/). */
  useEffect(() => {
    const view = {
      tab,
      selected: tab === "home" ? selected || "" : "",
    };
    const key = navKey(view);
    const hash = navHash(view);

    if (navBoot.current) {
      navBoot.current = false;
      window.history.replaceState({ ...view, navKey: key }, "", hash);
      return;
    }
    if (navFromPop.current) {
      navFromPop.current = false;
      return;
    }
    if (window.history.state?.navKey === key) return;
    window.history.pushState({ ...view, navKey: key }, "", hash);
  }, [tab, selected]);

  useEffect(() => {
    const onPop = (ev) => {
      const view = viewFromState(ev.state);
      navFromPop.current = true;
      setTab(view.tab);
      setSelected(view.selected || "");
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const top = (day && day.top) || [];

  return (
    <div className="shell">
      <motion.header
        className="top"
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      >
        <div>
          <h1 className="brand">Portfolio News</h1>
          <p className="tagline">Утренний терминал</p>
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

      {!error && holdingsNote && tab === "home" ? (
        <div className="banner warn">
          <span className="muted">{holdingsNote}</span>
        </div>
      ) : null}

      {tab === "news" ? <NewsFeed onOpenReview={selectTicker} /> : null}
      {tab === "ops" ? <OpsPanel /> : null}
      {tab === "calendar" ? <CalendarPanel /> : null}

      {tab === "home" ? (
        <div className="day-panel">
          <motion.section
            className="kpis"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.06, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            <article className="kpi">
              <div className="k">Стоимость</div>
              <div className="v">
                {loading ? "…" : totalValue != null ? fmtRub(totalValue) : "—"}
              </div>
              <div className="s muted">
                {totalCost != null ? `вложено ${fmtRub(totalCost)}` : "вложено —"}
              </div>
            </article>
            <article className="kpi">
              <div className="k">Денег на счёте</div>
              <div className="v">
                {loading ? "…" : cashVal != null ? fmtRub(cashVal) : "—"}
              </div>
              <div className="s muted">кэш</div>
            </article>
            <article className="kpi">
              <div className="k">За день</div>
              <div className={"v " + pnlClass(day && day.day_rub)}>
                {loading ? "…" : fmtRub(day && day.day_rub, { signed: true })}
              </div>
              <div className={"s " + pnlClass(day && day.day_pct)}>
                {loading
                  ? "MOEX × позиции"
                  : `${fmtPct(day && day.day_pct)}${
                      day && day.stale ? " · кэш" : ""
                    }`}
              </div>
            </article>
            <article className="kpi">
              <div className="k">PnL</div>
              <div className={"v " + pnlClass(totalPnl)}>
                {loading ? "…" : fmtRub(totalPnl, { signed: true })}
              </div>
              <div className={"s " + pnlClass(totalPnlPct)}>
                {loading ? "—" : fmtPct(totalPnlPct)}
              </div>
            </article>
            <article className="kpi">
              <div className="k">Позиций</div>
              <div className="v">{loading ? "…" : String(papers.length)}</div>
              <div className="s muted">{breakdown}</div>
            </article>
          </motion.section>

          <motion.section
            className={"day-box" + (loading ? " loading" : "")}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            <h2>Кто двинул день</h2>
            <p className="lead">
              {loading
                ? "Считаем, кто двинул день…"
                : top.length
                  ? "Топ по вкладу в дневной Δ — клик по строке откроет разбор."
                  : "Нет топа (выходной / нет Δ)."}
            </p>
            {moexWeekend ? (
              <p className="mkt-note">
                Биржа выходной · цифры за последнюю сессию MOEX (MSK)
              </p>
            ) : null}
            {loading ? (
              <p className="day-skel">загрузка котировок…</p>
            ) : top.length ? (
              <ol className="movers">
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
                      className={"day-row" + (active ? " active" : "")}
                      title={tid ? `Открыть разбор ${tid}` : undefined}
                      onClick={() => selectTicker(tid)}
                      onKeyDown={(ev) => {
                        if (ev.key === "Enter" || ev.key === " ") {
                          ev.preventDefault();
                          selectTicker(tid);
                        }
                      }}
                      initial={{ opacity: 0, x: -6 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.1 + i * 0.04 }}
                    >
                      <span className="t">{r.ticker}</span>
                      <span className={"rub " + pnlClass(r.day_rub)}>
                        {fmtRub(r.day_rub, { signed: true })}
                      </span>
                      <span className="pct muted">{fmtPct(r.day_pct)}</span>
                      <span className="go">разбор →</span>
                    </motion.li>
                  );
                })}
              </ol>
            ) : null}
          </motion.section>

          <CapitalChart />

          <motion.section
            className="holdings"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              delay: 0.14,
              duration: 0.4,
              ease: [0.22, 1, 0.36, 1],
            }}
          >
            <div className="holdings-head">
              <div>
                <h2>Позиции</h2>
                <p className="muted lead">
                  {loading
                    ? "грузим…"
                    : papers.length
                      ? `${papers.length} · ${breakdown}`
                      : "Нет позиций в ответе БКС"}
                </p>
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
                    <div key={g.key} className={"asset-group ac-" + g.key}>
                      <h3>
                        {g.title}
                        <span className="muted"> · {g.rows.length}</span>
                      </h3>
                      <ul className="pos-list">
                        <li className="pos-cols" aria-hidden="true">
                          <span>Тикер</span>
                          <span className="num">Кол-во</span>
                          <span className="num">Стоимость</span>
                          <span className="num">PnL</span>
                        </li>
                        <AnimatePresence initial={false}>
                          {visible.map((h, i) => {
                            const tid = paperId(h);
                            const active = tid && tid === selected;
                            const title =
                              h.name || h.ticker || h.sec_code || "—";
                            return (
                              <motion.li
                                key={tid || `${g.key}-${i}`}
                                layout
                                initial={{ opacity: 0, y: 4 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0 }}
                                transition={{ duration: 0.18 }}
                                className={
                                  "pos-row" + (active ? " active" : "")
                                }
                              >
                                <button
                                  type="button"
                                  className="pos-main"
                                  onClick={() => selectTicker(tid)}
                                  title={
                                    tid ? `Открыть разбор ${tid}` : undefined
                                  }
                                >
                                  <span className="pos-id">
                                    <TickerLogo
                                      ticker={tid}
                                      isin={h.isin}
                                      title={title}
                                    />
                                    <strong>{tid || "?"}</strong>
                                    <span className="name muted">{title}</span>
                                  </span>
                                  <span className="pos-qty muted">
                                    {qtyFmt(h.quantity)}
                                  </span>
                                  <span className="pos-val">
                                    {fmtRub(h.market_value)}
                                  </span>
                                  <span
                                    className={"pos-pnl " + pnlClass(h.pnl)}
                                  >
                                    {fmtRub(h.pnl, { signed: true })}
                                  </span>
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
              ref={reviewRef}
              ticker={selected}
              holdings={holdings}
              totalValue={snap?.total_value ?? null}
            />
          ) : null}
        </div>
      ) : null}

      <nav className="tabs" aria-label="Разделы">
        <button
          type="button"
          className={"tab" + (tab === "home" ? " on" : "")}
          onClick={() => {
            setTab("home");
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        >
          День
        </button>
        <button
          type="button"
          className={"tab" + (tab === "news" ? " on" : "")}
          onClick={() => {
            setTab("news");
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        >
          Новости
        </button>
        <button
          type="button"
          className={"tab" + (tab === "ops" ? " on" : "")}
          onClick={() => {
            setTab("ops");
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        >
          Сделки
        </button>
        <button
          type="button"
          className={"tab" + (tab === "calendar" ? " on" : "")}
          onClick={() => {
            setTab("calendar");
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        >
          Календарь
        </button>
      </nav>
    </div>
  );
}
