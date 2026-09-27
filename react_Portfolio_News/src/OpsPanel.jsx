import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { API_BASE, getJson } from "./api";
import { fmtRub, qtyFmt } from "./format";

const OPS_PREVIEW = 25;
const OPS_KIND_TAG = { equity: "акц", bond: "обл", fund: "фонд" };
const KIND_LABELS = [
  { key: "equity", label: "Акции" },
  { key: "bond", label: "Облигации" },
  { key: "fund", label: "Фонды" },
];

function sideLabel(side) {
  const s = String(side || "").toLowerCase();
  if (s === "buy") return { text: "Покупка", cls: "side-buy" };
  if (s === "sell") return { text: "Продажа", cls: "side-sell" };
  return { text: side || "—", cls: "" };
}

function fmtWhen(iso) {
  const s = String(iso || "").trim();
  if (!s) return "—";
  const d = new Date(s);
  if (!Number.isNaN(d.getTime()) && /T00:00:00/.test(s)) {
    return d.toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  }
  if (!Number.isNaN(d.getTime())) {
    return d.toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }
  return s.replace("T", " ").slice(0, 19);
}

function ruPlural(n, one, few, many) {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b === 1) return one;
  if (b >= 2 && b <= 4) return few;
  return many;
}

function buildParams(kinds, year, tickerQ) {
  const p = new URLSearchParams();
  const on = Object.keys(kinds).filter((k) => kinds[k]);
  if (on.length && on.length < 3) p.set("kind", on.join(","));
  if (year) p.set("year", year);
  if (tickerQ) p.set("ticker", tickerQ);
  return p;
}

function csvHref(kinds, year, tickerQ) {
  const p = buildParams(kinds, year, tickerQ);
  const path = `/api/operations.csv?${p.toString()}`;
  return API_BASE ? `${API_BASE}${path}` : path;
}

export default function OpsPanel() {
  const [kinds, setKinds] = useState({ equity: true, bond: true, fund: true });
  const [year, setYear] = useState("");
  const [tickerInput, setTickerInput] = useState("");
  const [tickerQ, setTickerQ] = useState("");
  const [snap, setSnap] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState(() => {
    try {
      return sessionStorage.getItem("pn_ops_expanded") === "1";
    } catch {
      return false;
    }
  });
  const searchTimer = useRef(null);
  const seq = useRef(0);

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setTickerQ(tickerInput.trim());
    }, 280);
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, [tickerInput]);

  const load = useCallback(async () => {
    const anyKind = Object.values(kinds).some(Boolean);
    if (!anyKind) {
      setSnap(null);
      setError("");
      setLoading(false);
      return;
    }
    const my = ++seq.current;
    setLoading(true);
    setError("");
    try {
      const p = buildParams(kinds, year, tickerQ);
      p.set("limit", "0");
      const data = await getJson(`/api/operations?${p.toString()}`);
      if (my !== seq.current) return;
      setSnap(data);
    } catch (e) {
      if (my !== seq.current) return;
      setSnap(null);
      setError(String(e.message || e));
    } finally {
      if (my === seq.current) setLoading(false);
    }
  }, [kinds, year, tickerQ]);

  useEffect(() => {
    load();
  }, [load]);

  const years = useMemo(() => {
    const list = (snap?.years || []).slice().sort().reverse();
    return list;
  }, [snap]);

  const ops = snap?.operations || [];
  const anyKind = Object.values(kinds).some(Boolean);
  const shownLimit = expanded ? ops.length : Math.min(OPS_PREVIEW, ops.length);
  const shown = ops.slice(0, shownLimit);
  const rest = ops.length - OPS_PREVIEW;

  const lead = useMemo(() => {
    if (!anyKind) return "Выбери хотя бы один тип бумаг.";
    if (loading) return "Загрузка…";
    if (error) return `Сделки не загрузились: ${error}`;
    if (!snap) return "Загрузка…";
    if (!snap.configured) {
      return "Нет BCS токена и нет журнала — сделки недоступны.";
    }
    if (!snap.ok) return snap.error || "Не удалось загрузить сделки.";
    const src = snap.source ? ` · ${snap.source}` : "";
    if (!ops.length) return `Под фильтры ничего не попало${src}`;
    const span = years.length
      ? ` · ${year || `${years[years.length - 1]}–${years[0]}`}`
      : "";
    return (
      `Сделки · показано ${shown.length} из ${snap.total != null ? snap.total : ops.length}` +
      span +
      src +
      (snap.error ? ` · ${snap.error}` : "")
    );
  }, [anyKind, loading, error, snap, ops.length, shown.length, years, year]);

  const toggleKind = (key) => {
    setKinds((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const toggleExpand = () => {
    const next = !expanded;
    setExpanded(next);
    try {
      sessionStorage.setItem("pn_ops_expanded", next ? "1" : "0");
    } catch {
      /* ignore */
    }
  };

  return (
    <motion.section
      className="ops-box"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
    >
      <div className="panel-head">
        <div>
          <h2>Сделки</h2>
          <p className="muted lead">{lead}</p>
        </div>
        <button type="button" className="btn sm" onClick={load} disabled={loading}>
          Обновить
        </button>
      </div>

      <div className="ops-filters">
        <div className="chip-row" role="group" aria-label="Тип бумаг">
          {KIND_LABELS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              className={"chip" + (kinds[key] ? " on" : "")}
              onClick={() => toggleKind(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="filter-field">
          <span>Период</span>
          <select
            value={year}
            onChange={(e) => setYear(e.target.value)}
            aria-label="Период сделок"
          >
            <option value="">Всё время</option>
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
        <input
          type="search"
          className="ops-search"
          placeholder="Тикер или название"
          aria-label="Фильтр по тикеру или названию"
          value={tickerInput}
          onChange={(e) => setTickerInput(e.target.value)}
        />
        <a className="btn sm" href={csvHref(kinds, year, tickerQ)}>
          Скачать CSV
        </a>
      </div>

      <div className="ops-scroll">
        <table className="ops-table">
          <thead>
            <tr>
              <th>Дата / время</th>
              <th>Тикер</th>
              <th>Сторона</th>
              <th className="num">Кол-во</th>
              <th className="num">Цена</th>
              <th className="num">Сумма</th>
            </tr>
          </thead>
          <tbody>
            {!anyKind ? (
              <tr>
                <td colSpan={6} className="empty">
                  Все типы выключены.
                </td>
              </tr>
            ) : loading && !snap ? (
              <tr>
                <td colSpan={6} className="empty">
                  Загрузка…
                </td>
              </tr>
            ) : error && !snap ? (
              <tr>
                <td colSpan={6} className="empty">
                  {error}
                </td>
              </tr>
            ) : !snap?.configured ? (
              <tr>
                <td colSpan={6} className="empty">
                  Нет данных
                </td>
              </tr>
            ) : !snap.ok ? (
              <tr>
                <td colSpan={6} className="empty">
                  {snap.error || "Ошибка БКС"}
                </td>
              </tr>
            ) : !ops.length ? (
              <tr>
                <td colSpan={6} className="empty">
                  Нет сделок в выбранном типе/периоде.
                </td>
              </tr>
            ) : (
              <>
                {shown.map((o, i) => {
                  const side = sideLabel(o.side);
                  const tag = OPS_KIND_TAG[o.kind];
                  return (
                    <tr key={`${o.executed_at}-${o.ticker}-${i}`}>
                      <td>{fmtWhen(o.executed_at)}</td>
                      <td>
                        <strong>{o.ticker || "—"}</strong>
                        {tag ? <span className="ops-kind-tag">{tag}</span> : null}
                      </td>
                      <td className={side.cls}>{side.text}</td>
                      <td className="num">{qtyFmt(o.quantity)}</td>
                      <td className="num">{fmtRub(o.price, { digits: 2 })}</td>
                      <td className="num">{fmtRub(o.volume, { digits: 2 })}</td>
                    </tr>
                  );
                })}
                {rest > 0 ? (
                  <tr className="ops-more">
                    <td colSpan={6}>
                      <button
                        type="button"
                        className="btn sm more"
                        onClick={toggleExpand}
                      >
                        {expanded
                          ? "Свернуть"
                          : `Ещё ${rest} ${ruPlural(rest, "сделка", "сделки", "сделок")} ▾`}
                      </button>
                    </td>
                  </tr>
                ) : null}
              </>
            )}
          </tbody>
        </table>
      </div>
    </motion.section>
  );
}
