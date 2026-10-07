import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { API_BASE, getJson } from "./api";
import { fmtRub, qtyFmt } from "./format";

const OPS_PREVIEW = 25;
const OPS_KIND_TAG = { equity: "акц", bond: "обл", fund: "фонд" };
const KIND_LABELS = [
  { key: "", label: "Все" },
  { key: "equity", label: "Акции" },
  { key: "bond", label: "Облигации" },
  { key: "fund", label: "Фонды" },
];
/** BCS journal = buy/sell only; payouts history comes from calendar cache. */
const PAY_KIND_CHIPS = [
  { key: "coupon", label: "Купоны" },
  { key: "dividend", label: "Дивиденды" },
  { key: "redemption", label: "Погашения / амортизация" },
];

function sideLabel(side) {
  const s = String(side || "").toLowerCase();
  if (s === "buy") return { text: "Покупка", cls: "side-buy" };
  if (s === "sell") return { text: "Продажа", cls: "side-sell" };
  return { text: side || "—", cls: "" };
}

function payKindLabel(kind) {
  if (kind === "coupon") return "Купон";
  if (kind === "dividend") return "Дивиденд";
  if (kind === "redemption") return "Погашение / амортизация";
  return kind || "—";
}

function payStatusLabel(st) {
  if (st === "paid") return "Выплачено";
  if (st === "announced") return "Объявлено";
  return "Будет";
}

function payEventStatus(ev, today) {
  if (ev && ev.status) return ev.status;
  const day = String((ev && ev.pay_date) || "").slice(0, 10);
  if (day && today && day < today) return "paid";
  if ((ev && ev.kind) === "dividend" || (ev && ev.amount) == null) {
    return "announced";
  }
  return "upcoming";
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

export default function OpsPanel({ onOpenCalendar }) {
  /** trades = BCS buy/sell; payouts = calendar cashflows (див/купон/погашение). */
  const [view, setView] = useState("trades");
  /** "" = all kinds; one class at a time for readable subfilters. */
  const [kind, setKind] = useState("");
  const [year, setYear] = useState("");
  const [tickerInput, setTickerInput] = useState("");
  const [tickerQ, setTickerQ] = useState("");
  const [snap, setSnap] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [payEvents, setPayEvents] = useState([]);
  const [payLoading, setPayLoading] = useState(false);
  const [payError, setPayError] = useState("");
  const [payKinds, setPayKinds] = useState({
    coupon: true,
    dividend: true,
    redemption: true,
  });
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
  const today = useMemo(() => {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }, []);

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

  const loadPayouts = useCallback(async () => {
    setPayLoading(true);
    setPayError("");
    try {
      const data = await getJson("/api/calendar?days=730");
      const events = Array.isArray(data?.events) ? data.events : [];
      setPayEvents(events);
      if (data?.error && !events.length) {
        setPayError(String(data.error));
      }
    } catch (e) {
      setPayEvents([]);
      setPayError(String(e.message || e));
    } finally {
      setPayLoading(false);
    }
  }, []);

  useEffect(() => {
    if (view === "payouts") loadPayouts();
  }, [view, loadPayouts]);

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

  const payouts = useMemo(() => {
    const q = tickerQ.trim().toUpperCase();
    return payEvents
      .filter((ev) => {
        const k = String(ev.kind || "");
        if (k === "coupon" || k === "dividend" || k === "redemption") {
          if (!payKinds[k]) return false;
        } else {
          return false;
        }
        if (year) {
          const y = String(ev.pay_date || "").slice(0, 4);
          if (y !== String(year)) return false;
        }
        if (q) {
          const hay = `${ev.ticker || ""} ${ev.name || ""}`.toUpperCase();
          if (!hay.includes(q)) return false;
        }
        return true;
      })
      .slice()
      .sort((a, b) =>
        String(b.pay_date || "").localeCompare(String(a.pay_date || ""))
      );
  }, [payEvents, payKinds, year, tickerQ]);

  const payShownLimit = expanded
    ? payouts.length
    : Math.min(OPS_PREVIEW, payouts.length);
  const payShown = payouts.slice(0, payShownLimit);
  const payRest = payouts.length - OPS_PREVIEW;

  const kindTitle =
    KIND_LABELS.find((k) => k.key === kind)?.label || "Все";

  const lead = useMemo(() => {
    if (view === "payouts") {
      if (payLoading && !payEvents.length) {
        return "История выплат из календаря (купоны / дивиденды / погашения).";
      }
      if (payLoading) return "Загрузка выплат…";
      if (payError) return `Выплаты: ${payError}`;
      return (
        `Выплаты · ${payouts.length}` +
        (year ? ` · ${year}` : " · 2 года") +
        " · вперёд — вкладка Календарь"
      );
    }
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
    view,
    payLoading,
    payEvents.length,
    payError,
    payouts.length,
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
      <div className="ops-head">
        <h2>{view === "payouts" ? "Выплаты" : "Сделки"}</h2>
        <div className="ops-view-chips" role="radiogroup" aria-label="Режим">
          <button
            type="button"
            role="radio"
            aria-checked={view === "trades"}
            className={"ops-view-chip" + (view === "trades" ? " on" : "")}
            onClick={() => {
              setView("trades");
              setExpanded(false);
            }}
          >
            Сделки
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={view === "payouts"}
            className={"ops-view-chip" + (view === "payouts" ? " on" : "")}
            onClick={() => {
              setView("payouts");
              setExpanded(false);
            }}
          >
            Выплаты
          </button>
        </div>
      </div>
      <p className="lead">{lead}</p>

      {view === "payouts" ? (
        <>
          <div className="ops-filters">
            <div className="ops-kind-chips" role="group" aria-label="Тип выплат">
              {PAY_KIND_CHIPS.map(({ key, label }) => (
                <button
                  key={key}
                  type="button"
                  className={
                    "ops-kind-chip pay-" +
                    key +
                    (payKinds[key] ? " on" : "")
                  }
                  onClick={() =>
                    setPayKinds((prev) => ({ ...prev, [key]: !prev[key] }))
                  }
                >
                  {label}
                </button>
              ))}
            </div>
            <label className="ops-period-wrap">
              <span>Год</span>
              <select
                value={year}
                onChange={(e) => setYear(e.target.value)}
                aria-label="Год выплат"
              >
                <option value="">Все</option>
                {Array.from(
                  new Set(
                    payEvents
                      .map((e) => String(e.pay_date || "").slice(0, 4))
                      .filter(Boolean)
                  )
                )
                  .sort()
                  .reverse()
                  .map((y) => (
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
              aria-label="Фильтр выплат"
              value={tickerInput}
              onChange={(e) => setTickerInput(e.target.value)}
            />
            <button
              type="button"
              className="ops-csv-btn"
              onClick={loadPayouts}
              disabled={payLoading}
            >
              Обновить
            </button>
            {typeof onOpenCalendar === "function" ? (
              <button
                type="button"
                className="ops-cal-link"
                onClick={onOpenCalendar}
              >
                Календарь вперёд →
              </button>
            ) : null}
          </div>

          <div className="ops-scroll">
            <table className="ops-table">
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>Тикер</th>
                  <th>Тип</th>
                  <th>Статус</th>
                  <th className="num">Сумма</th>
                </tr>
              </thead>
              <tbody>
                {payLoading && !payEvents.length ? (
                  <tr>
                    <td colSpan={5} className="empty">
                      Загрузка…
                    </td>
                  </tr>
                ) : payError && !payEvents.length ? (
                  <tr>
                    <td colSpan={5} className="empty">
                      {payError}
                    </td>
                  </tr>
                ) : !payouts.length ? (
                  <tr>
                    <td colSpan={5} className="empty">
                      Нет выплат в фильтрах. Журнал BCS — только покупки/продажи;
                      выплаты из календаря MOEX/БКС.
                    </td>
                  </tr>
                ) : (
                  <>
                    {payShown.map((ev, i) => {
                      const st = payEventStatus(ev, today);
                      return (
                        <tr key={`${ev.ticker}-${ev.pay_date}-${ev.kind}-${i}`}>
                          <td>{fmtWhen(String(ev.pay_date || "") + "T00:00:00")}</td>
                          <td>
                            <strong>{ev.ticker || "—"}</strong>
                            {ev.name ? (
                              <div className="ops-bucket muted">{ev.name}</div>
                            ) : null}
                          </td>
                          <td>{payKindLabel(ev.kind)}</td>
                          <td className={"pay-st st-" + st}>
                            {payStatusLabel(st)}
                          </td>
                          <td className="num">
                            {ev.amount != null
                              ? fmtRub(ev.amount, { digits: 0 })
                              : "—"}
                          </td>
                        </tr>
                      );
                    })}
                    {payRest > 0 ? (
                      <tr className="ops-more">
                        <td colSpan={5}>
                          <button
                            type="button"
                            className="ops-more-btn"
                            onClick={toggleExpand}
                          >
                            {expanded
                              ? "Свернуть"
                              : `Ещё ${payRest} ${ruPlural(payRest, "выплата", "выплаты", "выплат")} ▾`}
                          </button>
                        </td>
                      </tr>
                    ) : null}
                  </>
                )}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <>
          <div className="ops-filters">
            <div className="ops-kind-chips" role="radiogroup" aria-label="Тип бумаг">
              {KIND_LABELS.map(({ key, label }) => (
                <button
                  key={key || "all"}
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
            {typeof onOpenCalendar === "function" ? (
              <button
                type="button"
                className="ops-cal-link"
                onClick={onOpenCalendar}
              >
                Календарь →
              </button>
            ) : null}
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
        </>
      )}
    </motion.section>
  );
}
