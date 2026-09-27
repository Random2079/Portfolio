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
const MONTH_RU_SHORT = [
  "янв",
  "фев",
  "мар",
  "апр",
  "май",
  "июн",
  "июл",
  "авг",
  "сен",
  "окт",
  "ноя",
  "дек",
];

const BAR_SERIES = [
  ["coupon", "paid"],
  ["coupon", "announced"],
  ["coupon", "upcoming"],
  ["dividend", "paid"],
  ["dividend", "announced"],
  ["dividend", "upcoming"],
  ["redemption", "paid"],
  ["redemption", "announced"],
  ["redemption", "upcoming"],
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

function payStatusKey(st) {
  if (st === "paid" || st === "announced") return st;
  return "upcoming";
}

function payKindLabel(kind) {
  if (kind === "coupon") return "Купон";
  if (kind === "redemption") return "Погашение";
  return "Дивиденд";
}

function payStatusLabel(st) {
  if (st === "paid") return "выплачено";
  if (st === "announced") return "объявлено";
  return "будет";
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

function monthLabel(key, full = true) {
  const p = parseMonthKey(key);
  if (!p) return "—";
  const name = full ? MONTH_RU[p.mm - 1] : MONTH_RU_SHORT[p.mm - 1];
  return full ? `${name} ${p.yy}` : name;
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

function emptyPayMonth(key) {
  return {
    month: key,
    amount: 0,
    coupon_paid: 0,
    coupon_announced: 0,
    coupon_upcoming: 0,
    dividend_paid: 0,
    dividend_announced: 0,
    dividend_upcoming: 0,
    redemption_paid: 0,
    redemption_announced: 0,
    redemption_upcoming: 0,
  };
}

function monthsFromEvents(events, today) {
  const map = {};
  for (const ev of events) {
    const key = String(ev.pay_date || "").slice(0, 7);
    if (!key) continue;
    if (!map[key]) map[key] = emptyPayMonth(key);
    const val = ev.amount != null ? Number(ev.amount) : 0;
    const st = payStatusKey(payEventStatus(ev, today));
    const kind = payKindKey(ev.kind);
    map[key].amount += val;
    map[key][`${kind}_${st}`] += val;
  }
  return Object.keys(map)
    .sort()
    .map((k) => map[k]);
}

function padPayMonths(months, period, today) {
  const by = {};
  for (const m of months || []) if (m?.month) by[m.month] = m;
  let year = "";
  if (period === "year" && today) year = String(today).slice(0, 4);
  else if (/^\d{4}$/.test(period)) year = period;
  if (year) {
    const out = [];
    for (let i = 1; i <= 12; i += 1) {
      const key = year + "-" + String(i).padStart(2, "0");
      out.push(by[key] || emptyPayMonth(key));
    }
    return out;
  }
  if (period === "ahead" && today) {
    const start = parseMonthKey(String(today).slice(0, 7));
    if (!start) return months || [];
    const out = [];
    for (let i = 0; i < 12; i += 1) {
      const d = new Date(start.yy, start.mm - 1 + i, 1);
      const key =
        d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0");
      out.push(by[key] || emptyPayMonth(key));
    }
    return out;
  }
  return months || [];
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

  const monthBars = useMemo(() => {
    const raw = monthsFromEvents(visible, today);
    return padPayMonths(raw, period, today);
  }, [visible, period, today]);

  const barMax = useMemo(() => {
    let m = 0;
    for (const row of monthBars) {
      if (row.amount > m) m = row.amount;
    }
    return m || 1;
  }, [monthBars]);

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
      className="cal-box"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
    >
      <div className="cal-head">
        <h2>Календарь выплат</h2>
        <div className="cal-modes">
          <button
            type="button"
            className={"cal-mode" + (mode === "calendar" ? " on" : "")}
            onClick={() => setMode("calendar")}
          >
            Календарь
          </button>
          <button
            type="button"
            className={"cal-mode" + (mode === "list" ? " on" : "")}
            onClick={() => setMode("list")}
          >
            Список
          </button>
          <button
            type="button"
            className="btn sm"
            onClick={load}
            disabled={loading}
          >
            Обновить
          </button>
        </div>
      </div>
      <p className="cal-lead">
        Купоны, дивиденды и погашения по своим бумагам.
      </p>

      <div className="cal-filters">
        <label className="cal-period">
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
        <div className="cal-chips" role="group" aria-label="Тип выплат">
          {KIND_CHIPS.map(({ key, label, cls }) => (
            <button
              key={key}
              type="button"
              className={"cal-chip " + cls + (kinds[key] ? " on" : "")}
              onClick={() => toggleKind(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="cal-chips" role="group" aria-label="Статус выплат">
          {STATUS_CHIPS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              className={
                "cal-chip" + (statuses[key] ? " on" : "") + " st-" + key
              }
              onClick={() => toggleStatus(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="cal-legend" aria-hidden="true">
        <span className="cal-lg coupon">Купон</span>
        <span className="cal-lg dividend">Дивиденд</span>
        <span className="cal-lg redemption">Погашение</span>
        <span className="cal-lg paid-ink">Яркий = выплачено</span>
        <span className="cal-lg ann-ink">Бледнеет = объявлено</span>
        <span className="cal-lg upc-ink">Самый бледный = будет</span>
      </div>

      <div className="cal-top">
        <div className="cal-sum">
          <div className="cal-sum-k">{sumLabel}</div>
          <div className="cal-sum-v">
            {totals.total != null
              ? fmtRub(totals.total, { digits: 0 })
              : visible.length
                ? `${visible.length} дат`
                : "—"}
          </div>
          <div className="cal-sum-rows">
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
        <div
          className="cal-bars"
          role="img"
          aria-label="Выплаты по месяцам"
        >
          {monthBars.map((row) => {
            const active = row.month === monthKey;
            const h = Math.max(
              0,
              Math.round((row.amount / barMax) * 100)
            );
            return (
              <button
                key={row.month}
                type="button"
                className={"cal-bar-col" + (active ? " on" : "")}
                onClick={() => {
                  if (monthInPeriod(row.month, period, today)) {
                    setMonthKey(row.month);
                    setMode("calendar");
                  }
                }}
                title={`${monthLabel(row.month)} · ${
                  row.amount
                    ? fmtRub(row.amount, { digits: 0 })
                    : "нет сумм"
                }`}
              >
                <div className="cal-bar-stack" style={{ height: `${h}%` }}>
                  {BAR_SERIES.map(([kind, st]) => {
                    const val = Number(row[`${kind}_${st}`] || 0);
                    if (!val || !row.amount) return null;
                    const segH = Math.max(
                      2,
                      Math.round((val / row.amount) * 100)
                    );
                    return (
                      <span
                        key={`${kind}_${st}`}
                        className={`cal-bar-seg ${kind} st-${st}`}
                        style={{ flexGrow: segH, flexBasis: 0 }}
                      />
                    );
                  })}
                </div>
                <span className="cal-bar-lbl">{monthLabel(row.month, false)}</span>
              </button>
            );
          })}
        </div>
      </div>

      {mode === "calendar" ? (
        <div className="cal-wrap">
          <div className="cal-nav">
            <button
              type="button"
              className="cal-arrow"
              onClick={() => shiftMonth(-1)}
              aria-label="Предыдущий месяц"
            >
              ‹
            </button>
            <span className="cal-month">{monthLabel(monthKey)}</span>
            <button
              type="button"
              className="cal-arrow"
              onClick={() => shiftMonth(1)}
              aria-label="Следующий месяц"
            >
              ›
            </button>
            <span className="cal-badge">
              {calendarCells?.monthSum
                ? `+${fmtRub(calendarCells.monthSum, { digits: 0 })}`
                : calendarCells?.evCount
                  ? `${calendarCells.evCount} дат · суммы после БКС`
                  : "нет выплат"}
            </span>
          </div>
          <div className="cal-grid">
            {WD.map((w) => (
              <div key={w} className="cal-wd">
                {w}
              </div>
            ))}
            {calendarCells?.cells.map((c) =>
              c.empty ? (
                <div key={c.key} className="cal-day empty" />
              ) : (
                <div
                  key={c.key}
                  className={"cal-day" + (c.today ? " today" : "")}
                >
                  <div className="cal-day-top">
                    <span className="cal-num">{c.day}</span>
                    {c.daySum ? (
                      <span className="cal-day-sum">
                        +{fmtRub(c.daySum, { digits: 0 })}
                      </span>
                    ) : null}
                  </div>
                  {c.evs.slice(0, 3).map((ev, i) => {
                    const kind = payKindKey(ev.kind);
                    const st = payEventStatus(ev, today);
                    return (
                      <div
                        key={`${ev.ticker}-${ev.pay_date}-${i}`}
                        className={"cal-ev " + kind + " st-" + st}
                        title={`${ev.ticker || ""} · ${payKindLabel(ev.kind)} · ${payStatusLabel(st)}`}
                      >
                        <i className="cal-dot" aria-hidden="true" />
                        <div className="cal-ev-body">
                          <span className="cal-ev-t">{payEvTitle(ev)}</span>
                          <span className="cal-ev-v">
                            {ev.amount != null
                              ? fmtRub(ev.amount, { digits: 0 })
                              : "сумма ?"}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                  {c.evs.length > 3 ? (
                    <div className="cal-more">+ ещё {c.evs.length - 3}</div>
                  ) : null}
                </div>
              )
            )}
          </div>
        </div>
      ) : (
        <ol className="cal-list">
          {visible.slice(0, 60).map((ev, i) => (
            <li key={`${ev.ticker}-${ev.pay_date}-${i}`}>
              <span className="cal-list-d">{payDateHuman(ev.pay_date)}</span>
              <span className="cal-list-rub">
                {ev.amount != null
                  ? fmtRub(ev.amount, { digits: 0 })
                  : "сумма ?"}
              </span>
              <span className="cal-list-meta">
                {ev.name || ev.ticker || ""} · {payKindLabel(ev.kind)}
              </span>
            </li>
          ))}
          {!visible.length ? (
            <li className="cal-list-empty">Нет выплат в фильтрах.</li>
          ) : null}
        </ol>
      )}

      <p
        className={
          "cal-status" +
          (error || (data?.error && !(data.events || []).length) ? " err" : "")
        }
      >
        {statusText}
      </p>
    </motion.section>
  );
}
