import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import "./App.css";

function fmtRub(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  const sign = v > 0 ? "+" : "";
  return (
    sign +
    v.toLocaleString("ru-RU", {
      maximumFractionDigits: 0,
      minimumFractionDigits: 0,
    }) +
    " ₽"
  );
}

function fmtPct(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  const sign = v > 0 ? "+" : "";
  return sign + v.toFixed(2) + "%";
}

function pnlClass(n) {
  if (n == null || Number.isNaN(Number(n))) return "";
  if (Number(n) > 0) return "up";
  if (Number(n) < 0) return "down";
  return "";
}

async function getJson(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [day, setDay] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [h, d] = await Promise.all([
        getJson("/api/health"),
        getJson("/api/day?top=5"),
      ]);
      setHealth(h);
      setDay(d);
    } catch (e) {
      setError(String(e.message || e));
      setHealth(null);
      setDay(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const apiOk = !!(health && (health.ok === true || health.ok === "true"));
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
          <p className="eyebrow">IDEA-003 · React R0</p>
          <h1 className="brand">Portfolio News</h1>
          <p className="tagline">
            Утренний терминал · референс ваниль · API на :8765
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
          Нет связи с ванильным serve. Запусти в{" "}
          <code>Portfolio_News</code>:{" "}
          <code>python -m portfolio_news serve</code>
          <br />
          <span className="muted">{error}</span>
        </motion.div>
      ) : null}

      <motion.section
        className="kpi-row"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.12, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      >
        <article className="kpi">
          <h2>День</h2>
          <p className={"v " + pnlClass(day && day.day_rub)}>
            {loading ? "…" : fmtRub(day && day.day_rub)}
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
                ? Number(day.total_value).toLocaleString("ru-RU", {
                    maximumFractionDigits: 0,
                  }) + " ₽"
                : "—"}
          </p>
          <p className="s muted">
            {day && day.missing
              ? "без котировок: " + day.missing
              : "MOEX × BCS"}
          </p>
        </article>
        <article className="kpi wide">
          <h2>Кто двинул день</h2>
          {loading ? (
            <p className="muted">грузим…</p>
          ) : top.length ? (
            <ul className="movers">
              {top.map((r, i) => (
                <motion.li
                  key={r.ticker || i}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.18 + i * 0.05 }}
                >
                  <span className="t">{r.ticker}</span>
                  <span className={"rub " + pnlClass(r.day_rub)}>
                    {fmtRub(r.day_rub)}
                  </span>
                  <span className="pct muted">{fmtPct(r.day_pct)}</span>
                </motion.li>
              ))}
            </ul>
          ) : (
            <p className="muted">Нет топа (выходной / нет Δ)</p>
          )}
        </article>
      </motion.section>

      <motion.footer
        className="foot"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.35 }}
      >
        <p>
          <strong>R0</strong> — шелл + прокси. Бэкап ванили:{" "}
          <a href="http://127.0.0.1:8765/" target="_blank" rel="noreferrer">
            127.0.0.1:8765
          </a>
          . Дальше R1: позиции / focus.
        </p>
      </motion.footer>
    </div>
  );
}
