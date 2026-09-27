import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { getJson } from "./api";
import { fmtRub } from "./format";

const KIND_CHIPS = [
  { key: "coupon", label: "Купоны", cls: "coupon" },
  { key: "dividend", label: "Дивиденды", cls: "dividend" },
  { key: "redemption", label: "Погашения", cls: "redemption" },
];

const STATUS_CHIPS = [
  { key: "paid", label: "Выплаченные" },
  { key: "upcoming", label: "Будут оплачены" },
  { key: "announced", label: "Объявлены" },
];

const WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"];
const MONTH_RU = [
  "январь",
  "февраль",
  "март",
  "апрель",
  "май",
  "июнь",
  "июль",
  "август",
  "сентябрь",
  "октябрь",
  "ноябрь",
  "декабрь",
];

function payKindKey(kind) {
  if (kind === "coupon" || kind === "redemption") return kind;
  return "dividend";
}

function payEventStatus(ev, today) {
  if (ev && ev.status) return ev.status;
  const day = String((ev && ev.pay_date) || "");
  if (day && today && day < today) return "paid";
  if ((ev && ev.kind) === "dividend" || (ev && ev.amount) == null) return "announced";
  return "upcoming";
}

function payKindLabel(kind) {
  if (kind === "coupon") return "Купон";
  if (kind === "redemption") return "Погашение";
  return "Дивиденд";
}

function payEvTitle(ev) {
  return ev.ticker || ev.name || "—";
}

function payDateHuman(iso) {
  const s = String(iso || "").slice(0, 10);
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return s || "—";
  return `${m[3]}.${m[2]}.${m[1]}`;
}

function parseMonthKey(key) {
  const m = String(key || "").match(/^(\d{4})-(\d{2})$/);
  if (!m) return null;
  const yy = Number(m[1]);
  const mm = Number(m[2]);
  if (!yy || mm < 1 || mm > 12) return null;
  return { yy, mm, key: `${yy}-${String(mm).padStart(2, "0")}` };
}

function monthLabel(key) {
  const p = parseMonthKey(key);
  if (!p) return "—";
  return `${MONTH_RU[p.mm - 1]} ${p.yy}`;
}

function inPeriod(ev, period, today) {
  const day = String(ev.pay_date || "").slice(0, 10);
  if (!day) return false;
  const t = today || day;
  if (period === "ahead") return day >= t;
  if (period === "year") return day.slice(0, 4) === t.slice(0, 4);
  return day.slice(0, 4) === period;
}

function monthInPeriod(monthKey, period, today) {
  const p = parseMonthKey(monthKey);
  if (!p) return false;
  if (period === "ahead" && today) {
    const start = String(today).slice(0, 7);
    const endDate = new Date(
      Number(today.slice(0, 4)),
      Number(today.slice(5, 7)) - 1 + 11,
      1
    );
    const end =
      endDate.getFullYear() +
      "-" +
      String(endDate.getMonth() + 1).padStart(2, "0");
    return monthKey >= start && monthKey <= end;
  }
  if (period === "year" && today) {
    return monthKey.slice(0, 4) === String(today).slice(0, 4);
  }
  if (/^\d{4}$/.test(period)) return monthKey.slice(0, 4) === period;
  return true;
}

function firstMonthInPeriod(today, events, period) {
  if (period === "year" && today) return String(today).slice(0, 7);
  if (/^\d{4}$/.test(period)) return `${period}-01`;
  if (period === "ahead" && today) return String(today).slice(0, 7);
  const first = (events || [])
    .map((e) => String(e.pay_date || "").slice(0, 7))
    .filter(Boolean)
    .sort()[0];
  return first || (today ? String(today).slice(0, 7) : "");
}

export default function CalendarPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [period, setPeriod] = useState("year");
  const [kinds, setKinds] = useState({
    coupon: true,
    dividend: true,
    redemption: true,
  });
  const [statuses, setStatuses] = useState({
    paid: true,
    upcoming: true,
    announced: true,
  });
  const [mode, setMode] = useState("calendar");
  const [monthKey, setMonthKey] = useState("");
  const pollRef = useRef(null);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const my = ++seq.current;
    setLoading(true);
    setError("");
    try {
      const snap = await getJson("/api/calendar?days=365");
      if (my !== seq.current) return;
      setData(snap);
      if (snap?.pending) {
        if (pollRef.current) clearTimeout(pollRef.current);
        pollRef.current = setTimeout(() => load(), 8000);
      }
    } catch (e) {
      if (my !== seq.current) return;
      setData(null);
      setError(String(e.message || e));
    } finally {
      if (my === seq.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [load]);

  const today = (data && data.today) || "";

  const visible = useMemo(() => {
    const all = (data && data.events) || [];
    return all.filter((ev) => {
      const k = payKindKey(ev.kind);
      const st = payEventStatus(ev, today);
      if (!kinds[k]) return false;
      if (!statuses[st]) return false;
      return inPeriod(ev, period, today);
    });
  }, [data, kinds, statuses, period, today]);

  useEffect(() => {
    if (!monthInPeriod(monthKey, period, today)) {
      setMonthKey(firstMonthInPeriod(today, visible, period));
    }
  }, [monthKey, period, today, visible]);

  const totals = useMemo(() => {
    const known = visible
      .map((e) => (e.amount != null ? Number(e.amount) : 0))
      .filter((n) => n);
    const totalFromEv = known.length ? known.reduce((a, b) => a + b, 0) : null;
    const total =
      totalFromEv != null
        ? totalFromEv
        : data && data.total_amount != null && period === "year"
          ? Number(data.total_amount)
          : null;
    let span = 365;
    if (period === "ahead") {
      span = Number((data && data.ahead_days) || 365) || 365;
    } else if (period === "year" && today) {
      const y = Number(today.slice(0, 4));
      const start = new Date(y, 0, 1);
      const end = new Date(y, 11, 31);
      span = Math.max(1, Math.round((end - start) / 86400000) + 1);
    }
    const perDay = total != null ? total / span : null;
    const perMonth = perDay != null ? perDay * 30.4 : null;
    return { total, perDay, perMonth };
  }, [visible, data, period, today]);

  const byDay = useMemo(() => {
    const map = {};
    const key = monthKey;
    for (const ev of visible) {
      const day = String(ev.pay_date || "").slice(0, 10);
      if (!day.startsWith(key)) continue;
      const d = Number(day.slice(8, 10));
      if (!map[d]) map[d] = [];
      map[d].push(ev);
    }
    return map;
  }, [visible, monthKey]);

  const calendarCells = useMemo(() => {
    const parsed = parseMonthKey(monthKey);
    if (!parsed) return null;
    const { yy, mm } = parsed;
    const first = new Date(yy, mm - 1, 1);
    const daysInMonth = new Date(yy, mm, 0).getDate();
    if (!daysInMonth || Number.isNaN(first.getTime())) return null;
    const shift = (first.getDay() + 6) % 7;
    const cells = [];
    for (let i = 0; i < shift; i += 1) {
      cells.push({ empty: true, key: `e${i}` });
    }
    let monthSum = 0;
    let evCount = 0;
    for (let d = 1; d <= daysInMonth; d += 1) {
      const iso = `${monthKey}-${String(d).padStart(2, "0")}`;
      const evs = byDay[d] || [];
      let daySum = 0;
      for (const ev of evs) {
        if (ev.amount != null) daySum += Number(ev.amount);
      }
      monthSum += daySum;
      evCount += evs.length;
      cells.push({
        empty: false,
        key: iso,
        day: d,
        iso,
        today: iso === today,
        evs,
        daySum,
      });
    }
    return { cells, monthSum, evCount };
  }, [monthKey, byDay, today]);

  const periodOptions = useMemo(() => {
    const years = (data && data.years) || [];
    return [
      { value: "ahead", label: "На год вперёд" },
      { value: "year", label: "Текущий год" },
      ...years.map((y) => ({ value: String(y), label: String(y) })),
    ];
  }, [data]);

  const sumLabel =
    period === "ahead"
      ? "Всего вперёд"
      : period === "year"
        ? "Всего за год"
        : `Всего за ${period}`;

  const statusText = useMemo(() => {
    if (loading && !data) return "Загрузка…";
    if (error) return error;
    if (data?.pending) {
      return "Собираю календарь с биржи — это медленно, обнови через минуту.";
    }
    if (data?.error && !(data.events || []).length) return data.error;
    if (!visible.length) return "Нет выплат в выбранных фильтрах.";
    return (
      `${visible.length} выплат` +
      (data?.missing ? ` · без данных по ${data.missing} бумагам` : "")
    );
  }, [loading, data, error, visible.length]);

  const shiftMonth = (delta) => {
    const parsed = parseMonthKey(monthKey);
    if (!parsed) return;
    const d = new Date(parsed.yy, parsed.mm - 1 + delta, 1);
    const next =
      d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0");
    if (!monthInPeriod(next, period, today)) return;
    setMonthKey(next);
  };

  const toggleKind = (key) =>
    setKinds((prev) => ({ ...prev, [key]: !prev[key] }));
  const toggleStatus = (key) =>
    setStatuses((prev) => ({ ...prev, [key]: !prev[key] }));

  return (
    <motion.section
      className="pay-box"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
    >
      <div className="panel-head">
        <div>
          <h2>Календарь выплат</h2>
          <p className="muted lead">
            Купоны, дивиденды и погашения по своим бумагам.
          </p>
        </div>
        <div className="pay-modes">
          <button
            type="button"
            className={"chip" + (mode === "calendar" ? " on" : "")}
            onClick={() => setMode("calendar")}
          >
            Календарь
          </button>
          <button
            type="button"
            className={"chip" + (mode === "list" ? " on" : "")}
            onClick={() => setMode("list")}
          >
            Список
          </button>
          <button type="button" className="btn sm" onClick={load} disabled={loading}>
            Обновить
          </button>
        </div>
      </div>

      <div className="ops-filters pay-filters">
        <label className="filter-field">
          <span>Период</span>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            aria-label="Период календаря"
          >
            {periodOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <div className="chip-row" role="group" aria-label="Тип выплат">
          {KIND_CHIPS.map(({ key, label, cls }) => (
            <button
              key={key}
              type="button"
              className={"chip " + cls + (kinds[key] ? " on" : "")}
              onClick={() => toggleKind(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="chip-row" role="group" aria-label="Статус выплат">
          {STATUS_CHIPS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              className={"chip" + (statuses[key] ? " on" : "")}
              onClick={() => toggleStatus(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="pay-sum-row">
        <div className="pay-sum">
          <div className="pay-sum-k">{sumLabel}</div>
          <div className="pay-sum-v">
            {totals.total != null
              ? fmtRub(totals.total, { digits: 0 })
              : visible.length
                ? `${visible.length} дат`
                : "—"}
          </div>
          <div className="pay-sum-rows">
            <div>
              <span>В месяц</span>
              <b>
                {totals.perMonth != null
                  ? fmtRub(totals.perMonth, { digits: 0 })
                  : "—"}
              </b>
            </div>
            <div>
              <span>В день</span>
              <b>
                {totals.perDay != null
                  ? fmtRub(totals.perDay, { digits: 0 })
                  : "—"}
              </b>
            </div>
          </div>
        </div>
      </div>

      {mode === "calendar" ? (
        <div className="pay-cal">
          <div className="pay-nav">
            <button
              type="button"
              className="btn sm"
              onClick={() => shiftMonth(-1)}
              aria-label="Предыдущий месяц"
            >
              ‹
            </button>
            <span className="pay-month">{monthLabel(monthKey)}</span>
            <button
              type="button"
              className="btn sm"
              onClick={() => shiftMonth(1)}
              aria-label="Следующий месяц"
            >
              ›
            </button>
            <span className="pay-badge muted">
              {calendarCells?.monthSum
                ? `+${fmtRub(calendarCells.monthSum, { digits: 0 })}`
                : calendarCells?.evCount
                  ? `${calendarCells.evCount} дат · суммы после БКС`
                  : "нет выплат"}
            </span>
          </div>
          <div className="pay-grid">
            {WD.map((w) => (
              <div key={w} className="pg-wd">
                {w}
              </div>
            ))}
            {calendarCells?.cells.map((c) =>
              c.empty ? (
                <div key={c.key} className="pg-day empty" />
              ) : (
                <div
                  key={c.key}
                  className={"pg-day" + (c.today ? " today" : "")}
                >
                  <div className="pg-top">
                    <span className="pg-num">{c.day}</span>
                    {c.daySum ? (
                      <span className="pg-sum">
                        +{fmtRub(c.daySum, { digits: 0 })}
                      </span>
                    ) : null}
                  </div>
                  {c.evs.slice(0, 3).map((ev, i) => (
                    <div
                      key={`${ev.ticker}-${ev.pay_date}-${i}`}
                      className={
                        "pay-ev " +
                        payKindKey(ev.kind) +
                        " st-" +
                        payEventStatus(ev, today)
                      }
                      title={`${ev.ticker || ""} · ${payKindLabel(ev.kind)}`}
                    >
                      <span className="pe-t">{payEvTitle(ev)}</span>
                      <span className="pe-v">
                        {ev.amount != null
                          ? fmtRub(ev.amount, { digits: 0 })
                          : "сумма ?"}
                      </span>
                    </div>
                  ))}
                  {c.evs.length > 3 ? (
                    <div className="pe-more">+ ещё {c.evs.length - 3}</div>
                  ) : null}
                </div>
              )
            )}
          </div>
        </div>
      ) : (
        <ol className="pay-list">
          {visible.slice(0, 60).map((ev, i) => (
            <li key={`${ev.ticker}-${ev.pay_date}-${i}`}>
              <span className="t">{payDateHuman(ev.pay_date)}</span>
              <span className="rub">
                {ev.amount != null
                  ? fmtRub(ev.amount, { digits: 0 })
                  : "сумма ?"}
              </span>
              <span className="pct muted">
                {ev.name || ev.ticker || ""} · {payKindLabel(ev.kind)}
              </span>
            </li>
          ))}
          {!visible.length ? (
            <li className="muted">Нет выплат в фильтрах.</li>
          ) : null}
        </ol>
      )}

      <p
        className={
          "panel-status" +
          (error || (data?.error && !(data.events || []).length) ? " err" : "")
        }
      >
        {statusText}
      </p>
    </motion.section>
  );
}
