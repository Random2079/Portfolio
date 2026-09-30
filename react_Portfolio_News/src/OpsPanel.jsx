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

function buildParams(kind, year, tickerQ) {
  const p = new URLSearchParams();
  if (kind) p.set("kind", kind);
  if (year) p.set("year", year);
  if (tickerQ) p.set("ticker", tickerQ);
  return p;
}

function csvHref(kind, year, tickerQ) {
  const p = buildParams(kind, year, tickerQ);
  const path = `/api/operations.csv?${p.toString()}`;
  return API_BASE ? `${API_BASE}${path}` : path;
}

function collectChips(ops, idKey, labelKey) {
  const map = new Map();
  for (const o of ops) {
    const id = String(o[idKey] || "").trim();
    if (!id) continue;
    const label = String(o[labelKey] || id).trim() || id;
    if (!map.has(id)) map.set(id, { id, label, n: 0 });
    map.get(id).n += 1;
  }
  return Array.from(map.values()).sort((a, b) =>
    a.label.localeCompare(b.label, "ru")
  );
}

function chipOn(selected, id) {
  if (!selected.size) return true;
  return selected.has(id);
}

function toggleChip(prev, id) {
  const next = new Set(prev);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

function SubChips({ label, chips, selected, onToggle, onClear }) {
  if (!chips.length) return null;
  return (
    <div className="ops-subfilters" aria-label={label}>
      <span className="ops-sub-k">{label}</span>
      <div className="ops-sub-chips">
        {chips.map((c) => (
          <button
            key={c.id}
            type="button"
            className={
              "ops-sub-chip" +
              (chipOn(selected, c.id) && selected.size ? " on" : "") +
              (!selected.size ? " soft" : "")
            }
            onClick={() => onToggle(c.id)}
          >
            {c.label}
            <span className="n">{c.n}</span>
          </button>
        ))}
        {selected.size ? (
          <button type="button" className="ops-sub-chip ghost" onClick={onClear}>
            все
          </button>
        ) : null}
      </div>
    </div>
  );
}

export default function OpsPanel() {
  /** One asset class at a time — keeps secondary filters readable. */
  const [kind, setKind] = useState("equity");
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
  const [sectorSel, setSectorSel] = useState(() => new Set());
  const [bondTypeSel, setBondTypeSel] = useState(() => new Set());
  const [ratingSel, setRatingSel] = useState(() => new Set());
  const [fundSel, setFundSel] = useState(() => new Set());
  const searchTimer = useRef(null);
  const seq = useRef(0);

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setTickerQ(tickerInput.trim().toUpperCase());
    }, 280);
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, [tickerInput]);

  const selectKind = (key) => {
    if (key === kind) return;
    setKind(key);
    setSectorSel(new Set());
    setBondTypeSel(new Set());
    setRatingSel(new Set());
    setFundSel(new Set());
    setExpanded(false);
  };

  const load = useCallback(async () => {
    const my = ++seq.current;
    setLoading(true);
    setError("");
    try {
      const p = buildParams(kind, year, tickerQ);
      p.set("limit", "0");
      const data = await getJson(`/api/operations?${p.toString()}`);
      if (my !== seq.current) return;
      setSnap(data);
      setSectorSel(new Set());
      setBondTypeSel(new Set());
      setRatingSel(new Set());
      setFundSel(new Set());
    } catch (e) {
      if (my !== seq.current) return;
      setSnap(null);
      setError(String(e.message || e));
    } finally {
      if (my === seq.current) setLoading(false);
    }
  }, [kind, year, tickerQ]);

  useEffect(() => {
    load();
  }, [load]);

  const years = useMemo(() => {
    const list = (snap?.years || []).slice().sort().reverse();
    return list;
  }, [snap]);

  const opsAll = snap?.operations || [];

  const sectorChips = useMemo(
    () => collectChips(opsAll, "sector_id", "sector_label"),
    [opsAll]
  );
  const bondTypeChips = useMemo(
    () => collectChips(opsAll, "bond_type", "bond_type_label"),
    [opsAll]
  );
  const ratingChips = useMemo(
    () => collectChips(opsAll, "rating_bucket", "rating_bucket_label"),
    [opsAll]
  );
  const fundChips = useMemo(
    () => collectChips(opsAll, "fund_bucket", "fund_bucket_label"),
    [opsAll]
  );

  const ops = useMemo(() => {
    return opsAll.filter((o) => {
      if (kind === "equity") {
        const id = String(o.sector_id || "").trim();
        if (id && !chipOn(sectorSel, id)) return false;
      } else if (kind === "bond") {
        const bt = String(o.bond_type || "").trim();
        if (bt && !chipOn(bondTypeSel, bt)) return false;
        const rb = String(o.rating_bucket || "").trim();
        if (rb && !chipOn(ratingSel, rb)) return false;
      } else if (kind === "fund") {
        const fb = String(o.fund_bucket || "").trim();
        if (fb && !chipOn(fundSel, fb)) return false;
      }
      return true;
    });
  }, [opsAll, kind, sectorSel, bondTypeSel, ratingSel, fundSel]);

  const shownLimit = expanded ? ops.length : Math.min(OPS_PREVIEW, ops.length);
  const shown = ops.slice(0, shownLimit);
  const rest = ops.length - OPS_PREVIEW;

  const kindTitle =
    KIND_LABELS.find((k) => k.key === kind)?.label || kind;

  const lead = useMemo(() => {
    if (loading && !snap) return "Вся история: журнал Snowball + свежие сделки БКС.";
    if (loading) return "Загрузка…";
    if (error) return `Сделки не загрузились: ${error}`;
    if (!snap) return "Вся история: журнал Snowball + свежие сделки БКС.";
    if (!snap.configured) {
      return "Нет BCS токена и нет журнала — сделки недоступны.";
    }
    if (!snap.ok) return snap.error || "Не удалось загрузить сделки.";
    const src = snap.source ? ` · ${snap.source}` : "";
    if (!opsAll.length) return `${kindTitle}: под фильтры ничего не попало${src}`;
    const span = years.length
      ? ` · ${year || `${years[years.length - 1]}–${years[0]}`}`
      : "";
    const sub =
      ops.length !== opsAll.length ? ` · после уточнения ${ops.length}` : "";
    return (
      `${kindTitle} · показано ${shown.length} из ${ops.length}` +
      sub +
      span +
      src +
      (snap.error ? ` · ${snap.error}` : "")
    );
  }, [
    loading,
    error,
    snap,
    opsAll.length,
    ops.length,
    shown.length,
    years,
    year,
    kindTitle,
  ]);

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
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28 }}
    >
      <h2>Сделки</h2>
      <p className="lead">{lead}</p>

      <div className="ops-filters">
        <div className="ops-kind-chips" role="radiogroup" aria-label="Тип бумаг">
          {KIND_LABELS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              role="radio"
              aria-checked={kind === key}
              className={"ops-kind-chip" + (kind === key ? " on" : "")}
              data-kind={key}
              onClick={() => selectKind(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="ops-period-wrap">
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
          aria-label="Фильтр по тикеру или названию компании"
          value={tickerInput}
          onChange={(e) => setTickerInput(e.target.value)}
        />
        <a className="ops-csv-btn" href={csvHref(kind, year, tickerQ)}>
          Скачать CSV
        </a>
      </div>

      {kind === "equity" ? (
        <SubChips
          label="Сектора"
          chips={sectorChips}
          selected={sectorSel}
          onToggle={(id) => setSectorSel((prev) => toggleChip(prev, id))}
          onClear={() => setSectorSel(new Set())}
        />
      ) : null}

      {kind === "bond" ? (
        <>
          <SubChips
            label="Тип"
            chips={bondTypeChips}
            selected={bondTypeSel}
            onToggle={(id) => setBondTypeSel((prev) => toggleChip(prev, id))}
            onClear={() => setBondTypeSel(new Set())}
          />
          <SubChips
            label="Рейтинг"
            chips={ratingChips}
            selected={ratingSel}
            onToggle={(id) => setRatingSel((prev) => toggleChip(prev, id))}
            onClear={() => setRatingSel(new Set())}
          />
        </>
      ) : null}

      {kind === "fund" ? (
        <SubChips
          label="Корзины"
          chips={fundChips}
          selected={fundSel}
          onToggle={(id) => setFundSel((prev) => toggleChip(prev, id))}
          onClear={() => setFundSel(new Set())}
        />
      ) : null}

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
            {loading && !snap ? (
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
                  const bucket =
                    o.kind === "equity"
                      ? o.sector_label
                      : o.kind === "bond"
                        ? [o.bond_type_label, o.rating_bucket_label]
                            .filter(Boolean)
                            .join(" · ")
                        : o.fund_bucket_label;
                  return (
                    <tr key={`${o.executed_at}-${o.ticker}-${i}`}>
                      <td>{fmtWhen(o.executed_at)}</td>
                      <td>
                        <strong>{o.ticker || "—"}</strong>
                        {tag ? (
                          <span className="ops-kind-tag"> {tag}</span>
                        ) : null}
                        {bucket ? (
                          <div className="ops-bucket muted">{bucket}</div>
                        ) : null}
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
                        className="ops-more-btn"
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
