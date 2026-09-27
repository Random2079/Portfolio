import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { getJson, postJson } from "./api";

const AI_HIDE_KEY = "pn_ai_hide_noise";
const NOTIFY_KEY = "pn_notify";

const LABEL_RU = { noise: "шум", relevant: "ок", dup: "дубль" };

function readHideNoise() {
  try {
    return localStorage.getItem(AI_HIDE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeHideNoise(on) {
  try {
    localStorage.setItem(AI_HIDE_KEY, on ? "1" : "0");
  } catch {
    /* ignore */
  }
}

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

function AiBadge({ item }) {
  const label = String(item.ai_label || "").toLowerCase();
  if (!label) return null;
  const text = LABEL_RU[label] || label;
  return (
    <>
      <span className={"ai-badge " + label} title={item.ai_reason || ""}>
        {text}
      </span>
      {label === "relevant" && item.ai_urgency ? (
        <span className="ai-urg" title={item.ai_reason || ""}>
          {String(item.ai_urgency)}
        </span>
      ) : null}
    </>
  );
}

export default function NewsFeed() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [hideNoise, setHideNoise] = useState(readHideNoise);
  const [notify, setNotify] = useState(readNotify);
  const [aiReady, setAiReady] = useState(false);
  const [aiHint, setAiHint] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [pollBusy, setPollBusy] = useState(false);
  const [statusText, setStatusText] = useState("");
  const [statusErr, setStatusErr] = useState(false);
  const pollTimer = useRef(null);

  const loadNews = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const news = await getJson("/api/news?limit=40");
      setItems(Array.isArray(news) ? news : []);
    } catch (e) {
      setError(String(e.message || e));
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadAiStatus = useCallback(async () => {
    try {
      const st = await getJson("/api/news/ai-status");
      const ready = !!(st && st.ready);
      setAiReady(ready);
      setAiHint(ready ? "" : st?.hint || "ИИ выкл");
    } catch {
      setAiReady(false);
      setAiHint("статус ИИ недоступен");
    }
  }, []);

  useEffect(() => {
    loadNews();
    loadAiStatus();
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, [loadNews, loadAiStatus]);

  const visible = useMemo(() => {
    if (!hideNoise) return items;
    return items.filter(
      (n) => String(n.ai_label || "").toLowerCase() !== "noise"
    );
  }, [items, hideNoise]);

  const onHideNoise = (checked) => {
    setHideNoise(checked);
    writeHideNoise(checked);
  };

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
      await loadAiStatus();
    }
  };

  return (
    <motion.section
      className="news-panel"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="news-head">
        <div>
          <h2>Новости</h2>
          <p className="muted">
            Лента по бумагам портфеля (BCS). Toast — только сегодняшние, по
            умолчанию digest.
          </p>
        </div>
        <button
          type="button"
          className="btn sm"
          onClick={loadNews}
          disabled={loading || pollBusy}
        >
          Обновить ленту
        </button>
      </div>

      <div className="feed-toolbar">
        <label className="notify-label">
          <span className="muted">Toast</span>
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
          className="btn"
          onClick={startPoll}
          disabled={pollBusy}
        >
          Искать новости
        </button>
        {pollBusy ? (
          <button type="button" className="btn ghost" onClick={cancelPoll}>
            Отмена
          </button>
        ) : null}
        <button
          type="button"
          className="btn ai"
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
        <label className="ai-hide">
          <input
            type="checkbox"
            checked={hideNoise}
            onChange={(e) => onHideNoise(e.target.checked)}
          />
          <span>Скрыть шум</span>
        </label>
        {statusText ? (
          <span
            className={"poll-status" + (statusErr ? " err" : "")}
            aria-live="polite"
          >
            {statusText}
          </span>
        ) : null}
        {aiHint ? <span className="ai-hint muted">{aiHint}</span> : null}
      </div>

      {error ? (
        <p className="banner err">{error}</p>
      ) : loading ? (
        <p className="muted pad">грузим ленту…</p>
      ) : !visible.length ? (
        <p className="muted pad">
          Лента пуста — нажми «Искать новости» или CLI: once.
        </p>
      ) : (
        <ul className="feed-list">
          <AnimatePresence initial={false}>
            {visible.map((n) => {
              const href = safeHref(n.url);
              const meta = [n.ticker_id, n.source].filter(Boolean).join(" · ");
              const title = n.title || "(без заголовка)";
              return (
                <motion.li
                  key={n.id}
                  layout
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.18 }}
                  className="feed-item"
                >
                  <div className="feed-title-row">
                    {href ? (
                      <a href={href} target="_blank" rel="noreferrer">
                        {title}
                      </a>
                    ) : (
                      <span>{title}</span>
                    )}
                    <AiBadge item={n} />
                  </div>
                  {meta ? <div className="feed-meta muted">{meta}</div> : null}
                </motion.li>
              );
            })}
          </AnimatePresence>
        </ul>
      )}
    </motion.section>
  );
}
