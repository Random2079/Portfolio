import { useCallback, useEffect, useState } from "react";
import { getJson, postJson } from "./api";
import { shortErr } from "./format";

/**
 * F-B one-shot AI ticker review — same API as vanilla ai-review-box.
 */
export default function AiTickerReview({ ticker }) {
  const tid = String(ticker || "")
    .trim()
    .toUpperCase();
  const [ready, setReady] = useState(false);
  const [statusHint, setStatusHint] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [data, setData] = useState(null);
  const [fromCache, setFromCache] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const st = await getJson("/api/news/ai-status");
        if (cancelled) return;
        setReady(!!(st && st.ready));
        setStatusHint((st && st.hint) || "");
      } catch {
        if (cancelled) return;
        setReady(false);
        setStatusHint("статус ИИ недоступен");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!tid) {
      setData(null);
      setErr("");
      setFromCache(false);
      return;
    }
    let cancelled = false;
    setData(null);
    setErr("");
    setFromCache(false);
    (async () => {
      try {
        const payload = await getJson(
          `/api/ai/ticker-review/${encodeURIComponent(tid)}`
        );
        if (cancelled) return;
        if (payload?.data && typeof payload.data === "object") {
          setData(payload.data);
          setFromCache(!!payload.from_cache);
        }
      } catch {
        /* no cache — empty until button */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tid]);

  const run = useCallback(
    async (force) => {
      if (!tid || busy) return;
      setBusy(true);
      setErr("");
      try {
        const payload = await postJson("/api/ai/ticker-review", {
          ticker: tid,
          force: !!force,
        });
        setData(
          payload?.data && typeof payload.data === "object"
            ? payload.data
            : null
        );
        setFromCache(!!payload?.from_cache);
      } catch (e) {
        setErr(shortErr(e.message || e));
      } finally {
        setBusy(false);
      }
    },
    [tid, busy]
  );

  if (!tid) return null;

  const urg = String(data?.urgency || "").toLowerCase();
  const hits = Array.isArray(data?.hits) ? data.hits : [];
  const checks = Array.isArray(data?.checklist) ? data.checklist : [];
  const caves = Array.isArray(data?.caveats) ? data.caveats : [];
  let metaLine = "";
  if (data && fromCache) metaLine = "кэш";
  if (data?.news_count != null) {
    metaLine += (metaLine ? " · " : "") + `новостей: ${data.news_count}`;
  }

  return (
    <section className="ai-review-box" aria-label="ИИ разбор тикера">
      <div className="arv-head">
        <h3>ИИ-разбор</h3>
        <span className="rv-tag">F-B</span>
        <button
          type="button"
          className="arv-btn"
          disabled={!ready || busy}
          onClick={() => run(false)}
        >
          {busy ? "…" : "Разбор ИИ"}
        </button>
        {data ? (
          <button
            type="button"
            className="arv-btn ghost"
            disabled={!ready || busy}
            onClick={() => run(true)}
          >
            Ещё раз
          </button>
        ) : null}
      </div>
      {!data && statusHint ? (
        <p className="arv-hint">{statusHint}</p>
      ) : null}
      {err ? <p className="arv-err">{err}</p> : null}
      {!data && !err ? (
        <p className="arv-empty">
          One-shot по новостям {tid}: на что бьёт + чеклист к стратегии. Не чат,
          не «купи».
        </p>
      ) : null}
      {data ? (
        <div className="arv-body">
          {urg ? <span className={"arv-urg " + urg}>{urg}</span> : null}
          {metaLine ? <span className="arv-meta">{metaLine}</span> : null}
          <p className="arv-sum">{data.summary || "—"}</p>
          {hits.length ? (
            <>
              <div className="arv-label">На что бьёт</div>
              <ul>
                {hits.map((x, i) => (
                  <li key={i}>{String(x)}</li>
                ))}
              </ul>
            </>
          ) : null}
          {checks.length ? (
            <>
              <div className="arv-label">Чеклист к стратегии</div>
              <ul>
                {checks.map((x, i) => (
                  <li key={i}>{String(x)}</li>
                ))}
              </ul>
            </>
          ) : null}
          {caves.length ? (
            <>
              <div className="arv-label">Оговорки</div>
              <ul>
                {caves.map((x, i) => (
                  <li key={i}>{String(x)}</li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
