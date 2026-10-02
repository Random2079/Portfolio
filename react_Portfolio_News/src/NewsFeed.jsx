import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { getJson, postJson } from "./api";
import TickerLogo from "./TickerLogo";

const NOTIFY_KEY = "pn_notify";
const HEADLINES_PER_CARD = 3;

const URG_RANK = { high: 3, mid: 2, low: 1 };

function readNotify() {
  try {
    const v = localStorage.getItem(NOTIFY_KEY);
    if (v === "off" || v === "each" || v === "digest") return v;
  } catch {
    /* ignore */
  }
  return "digest";
}

function writeNotify(mode) {
  try {
    localStorage.setItem(NOTIFY_KEY, mode);
  } catch {
    /* ignore */
  }
}

function safeHref(url) {
  const href = String(url || "");
  return href.startsWith("http://") || href.startsWith("https://") ? href : "";
}

function urgRank(u) {
  return URG_RANK[String(u || "").toLowerCase()] || 0;
}

function itemTs(n) {
  const s = n.published_at || n.created_at || "";
  const t = Date.parse(s);
  return Number.isNaN(t) ? 0 : t;
}

function fmtNewsDate(iso) {
  const s = String(iso || "").trim();
  if (!s) return "";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s.slice(0, 16).replace("T", " ");
  return d.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Bucket for §7N floors. Noise/dup never shown. */
function fmtTokens(n) {
  const v = Number(n) || 0;
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + "M";
  if (v >= 1000) return Math.round(v / 1000) + "k";
  return String(v);
}

function fmtUsd(n) {
  const v = Number(n) || 0;
  return v >= 1 ? v.toFixed(2) : v.toFixed(3);
}

function floorOf(n) {
  const label = String(n.ai_label || "").toLowerCase();
  if (label === "noise" || label === "dup") return null;
  if (label === "relevant") {
    const u = String(n.ai_urgency || "").toLowerCase();
    if (u === "high") return "urgent";
    return "facts";
  }
  return "raw";
}

function groupByTicker(list) {
  const map = new Map();
  for (const n of list) {
    const tid = String(n.ticker_id || "").trim().toUpperCase() || "?";
    if (!map.has(tid)) map.set(tid, []);
    map.get(tid).push(n);
  }
  const cards = [];
  for (const [ticker, items] of map) {
    const sorted = items.slice().sort((a, b) => {
      const ur = urgRank(b.ai_urgency) - urgRank(a.ai_urgency);
      if (ur) return ur;
      return itemTs(b) - itemTs(a);
    });
    const maxUrg = Math.max(0, ...sorted.map((x) => urgRank(x.ai_urgency)));
    const maxTs = Math.max(0, ...sorted.map(itemTs));
    cards.push({
      ticker,
      items: sorted.slice(0, HEADLINES_PER_CARD),
      total: sorted.length,
      maxUrg,
      maxTs,
    });
  }
  cards.sort((a, b) => {
    if (b.maxUrg !== a.maxUrg) return b.maxUrg - a.maxUrg;
    return b.maxTs - a.maxTs;
  });
  return cards;
}

function UrgTag({ urgency }) {
  const u = String(urgency || "").toLowerCase();
  if (!u) return null;
  return (
    <span className={"news-urg news-urg-" + u} title="Срочность F-A">
      {u}
    </span>
  );
}

function TickerCard({ card, onOpenReview }) {
  return (
    <motion.article
      className="news-card"
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.18 }}
    >
      <header className="news-card-head">
        <button
          type="button"
          className="news-card-who"
          onClick={() => onOpenReview?.(card.ticker)}
          title="Открыть разбор на Дне"
        >
          <TickerLogo ticker={card.ticker} />
          <strong>{card.ticker}</strong>
        </button>
        <button
          type="button"
          className="news-card-go"
          onClick={() => onOpenReview?.(card.ticker)}
        >
          В разбор
        </button>
      </header>
      <ul className="news-card-lines">
        {card.items.map((n) => {
          const href = safeHref(n.url);
          const title = n.title || "(без заголовка)";
          const when = fmtNewsDate(n.published_at || n.created_at);
          return (
            <li key={n.id} className="news-line">
              <div className="news-line-main">
                {href ? (
                  <a href={href} target="_blank" rel="noreferrer">
                    {title}
                  </a>
                ) : (
                  <span className="feed-title">{title}</span>
                )}
                <UrgTag urgency={n.ai_urgency} />
              </div>
              <div className="news-line-meta">
                {[when, n.source].filter(Boolean).join(" · ")}
              </div>
            </li>
          );
        })}
      </ul>
      {card.total > HEADLINES_PER_CARD ? (
        <p className="news-card-more muted">
          ещё {card.total - HEADLINES_PER_CARD} по {card.ticker}
        </p>
      ) : null}
    </motion.article>
  );
}

function Floor({ title, hint, cards, empty, onOpenReview }) {
  return (
    <section className="news-floor">
      <h3 className="news-floor-title">{title}</h3>
      {hint ? <p className="news-floor-hint">{hint}</p> : null}
      {!cards.length ? (
        <p className="muted pad news-floor-empty">{empty}</p>
      ) : (
        <div className="news-cards">
          <AnimatePresence initial={false}>
            {cards.map((c) => (
              <TickerCard
                key={c.ticker}
                card={c}
                onOpenReview={onOpenReview}
              />
            ))}
          </AnimatePresence>
        </div>
      )}
    </section>
  );
}

/**
 * §7N news floors: urgent / facts by ticker cards; noise hidden; raw ≠ urgent.
 */
export default function NewsFeed({ onOpenReview }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notify, setNotify] = useState(readNotify);
  const [aiReady, setAiReady] = useState(false);
  const [aiHint, setAiHint] = useState("");
  const [aiMeter, setAiMeter] = useState(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [pollBusy, setPollBusy] = useState(false);
  const [statusText, setStatusText] = useState("");
  const [statusErr, setStatusErr] = useState(false);
  const pollTimer = useRef(null);

  const loadNews = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const news = await getJson("/api/news?limit=80");
      setItems(Array.isArray(news) ? news : []);
    } catch (e) {
      setError(String(e.message || e));
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadAiStatus = useCallback(async (refreshBalance = false) => {
    try {
      const st = await getJson(
        "/api/news/ai-status" + (refreshBalance ? "?refresh_balance=true" : "")
      );
      const ready = !!(st && st.ready);
      setAiReady(ready);
      setAiHint(ready ? "" : st?.hint || "ИИ выкл");
      setAiMeter(st?.has_key ? st : null);
    } catch {
      setAiReady(false);
      setAiHint("статус ИИ недоступен");
      setAiMeter(null);
    }
  }, []);

  useEffect(() => {
    loadNews();
    loadAiStatus();
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, [loadNews, loadAiStatus]);

  const floors = useMemo(() => {
    const urgent = [];
    const facts = [];
    const raw = [];
    for (const n of items) {
      const f = floorOf(n);
      if (f === "urgent") urgent.push(n);
      else if (f === "facts") facts.push(n);
      else if (f === "raw") raw.push(n);
    }
    return {
      urgent: groupByTicker(urgent),
      facts: groupByTicker(facts),
      raw: groupByTicker(raw),
      hasAi: items.some((n) => String(n.ai_label || "").trim()),
    };
  }, [items]);

  const onNotify = (mode) => {
    setNotify(mode);
    writeNotify(mode);
  };

  const setStatus = (text, isErr = false) => {
    setStatusText(text || "");
    setStatusErr(!!isErr);
  };

  const pollTick = useCallback(async () => {
    try {
      const st = await getJson("/api/poll/status");
      if (!st) return;
      if (st.running) {
        setPollBusy(true);
        const cur = st.current || 0;
        const tot = st.total || 0;
        const tid = st.ticker_id ? " · " + st.ticker_id : "";
        setStatus(
          "Опрос " + cur + "/" + tot + tid + " · +" + (st.inserted || 0)
        );
        return;
      }
      if (pollTimer.current) {
        clearInterval(pollTimer.current);
        pollTimer.current = null;
      }
      setPollBusy(false);
      if (st.error) {
        setStatus(String(st.error), true);
      } else {
        setStatus(
          "Готово · +" +
            (st.inserted || 0) +
            (st.skipped ? " · пропуск " + st.skipped : "")
        );
      }
      await loadNews();
    } catch (e) {
      setPollBusy(false);
      if (pollTimer.current) {
        clearInterval(pollTimer.current);
        pollTimer.current = null;
      }
      setStatus(String(e.message || e), true);
    }
  }, [loadNews]);

  const startPoll = async () => {
    if (pollBusy) return;
    setPollBusy(true);
    setStatus("Старт опроса…");
    try {
      await postJson("/api/poll?notify=" + encodeURIComponent(notify), {});
      if (pollTimer.current) clearInterval(pollTimer.current);
      pollTimer.current = setInterval(pollTick, 800);
      pollTick();
    } catch (e) {
      setPollBusy(false);
      setStatus(String(e.message || e), true);
    }
  };

  const cancelPoll = async () => {
    try {
      await postJson("/api/poll/cancel", {});
      setStatus("Отмена…");
    } catch (e) {
      setStatus(String(e.message || e), true);
    }
  };

  const runAiClassify = async () => {
    if (aiBusy || !aiReady) return;
    setAiBusy(true);
    setStatus("ИИ: классификация…");
    try {
      const data = await postJson("/api/news/ai-classify", {
        today_only: true,
        limit: 30,
      });
      setStatus(
        "ИИ: помечено " +
          (data.classified || 0) +
          (data.skipped ? " · пропуск " + data.skipped : "")
      );
      await loadNews();
    } catch (e) {
      setStatus("ИИ: " + String(e.message || e), true);
    } finally {
      setAiBusy(false);
      await loadAiStatus(true);
    }
  };

  const emptyFeed = !loading && !error && !items.length;
  const urgentEmptyHint = !floors.hasAi
    ? "Без ИИ срочное не угадываем — жми «Прогнать ИИ»."
    : "Сейчас нет high по фундаменту.";

  return (
    <motion.section
      className="news-panel"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="news-head">
        <h2>Новости</h2>
        <p className="lead">
          Срочно и факты — карточки по бумагам. Шум скрыт. Клик → разбор на
          Дне.
        </p>
      </div>

      <div className="feed-toolbar">
        <label className="notify-label">
          <span>Toast</span>
          <select
            value={notify}
            onChange={(e) => onNotify(e.target.value)}
            aria-label="Режим уведомлений"
            disabled={pollBusy}
          >
            <option value="digest">digest (один)</option>
            <option value="off">off</option>
            <option value="each">each (каждый)</option>
          </select>
        </label>
        <button
          type="button"
          className="poll-btn"
          onClick={startPoll}
          disabled={pollBusy}
        >
          Искать новости
        </button>
        {pollBusy ? (
          <button type="button" className="poll-cancel" onClick={cancelPoll}>
            Отмена
          </button>
        ) : null}
        <button
          type="button"
          className="feed-refresh"
          onClick={loadNews}
          disabled={loading || pollBusy}
          title="Перечитать ленту из БД — без нового опроса источников"
        >
          Обновить ленту
        </button>
        <button
          type="button"
          className="ai-btn"
          onClick={runAiClassify}
          disabled={!aiReady || aiBusy || pollBusy}
          title={
            aiReady
              ? "Прогнать DeepSeek по сегодняшним"
              : aiHint || "ИИ недоступен"
          }
        >
          {aiBusy ? "ИИ…" : "Прогнать ИИ"}
        </button>
        {aiMeter ? (
          <span
            className="ai-meter"
            title={
              "Месяц: " +
              (aiMeter.month_calls || 0) +
              " вызовов · " +
              fmtTokens(aiMeter.month_tokens) +
              " ток · ≈$" +
              fmtUsd(aiMeter.month_usd) +
              " (оценка по прайсу; баланс — с DeepSeek)"
            }
          >
            {aiMeter.balance != null
              ? "DeepSeek " +
                fmtUsd(aiMeter.balance) +
                " " +
                (aiMeter.balance_currency || "") +
                " · "
              : "баланс ? · "}
            сегодня {fmtTokens(aiMeter.today_tokens)} ток ≈ $
            {fmtUsd(aiMeter.today_usd)}
          </span>
        ) : null}
        {statusText ? (
          <span
            className={"poll-status" + (statusErr ? " err" : "")}
            aria-live="polite"
          >
            {statusText}
          </span>
        ) : null}
        {aiHint ? <span className="ai-hint">{aiHint}</span> : null}
      </div>

      {error ? <p className="banner err">{error}</p> : null}
      {loading ? <p className="muted pad">грузим ленту…</p> : null}
      {emptyFeed ? (
        <p className="muted pad">
          Лента пуста — нажми «Искать новости» или CLI: once.
        </p>
      ) : null}

      {!loading && !error && !emptyFeed ? (
        <>
          <Floor
            title="Срочно / к разбору"
            hint="relevant · high — бьёт в фундамент"
            cards={floors.urgent}
            empty={urgentEmptyHint}
            onOpenReview={onOpenReview}
          />
          <Floor
            title="Факты / среднее"
            hint="relevant · mid/low"
            cards={floors.facts}
            empty="Пока пусто — после «Прогнать ИИ» сюда попадут mid/low."
            onOpenReview={onOpenReview}
          />
          {floors.raw.length ? (
            <Floor
              title="Без разметки ИИ"
              hint="Сырое — не считаем срочным"
              cards={floors.raw}
              empty=""
              onOpenReview={onOpenReview}
            />
          ) : null}
        </>
      ) : null}
    </motion.section>
  );
}
