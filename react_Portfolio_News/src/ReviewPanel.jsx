import { useCallback, useEffect, useState } from "react";
import { getJson } from "./api";
import { shortErr } from "./format";

const REVIEW_VERDICTS = [
  { id: "жив", label: "тезис жив" },
  { id: "ослаб", label: "ослаб" },
  { id: "hold", label: "hold" },
  { id: "pass", label: "PASS-кэш" },
  { id: "watch", label: "WATCH" },
  { id: "нет_данных", label: "[НЕТ ДАННЫХ]" },
];

function verdictKey(tid) {
  return `pn_review_verdict_${String(tid || "").toUpperCase()}`;
}

function loadVerdict(tid) {
  try {
    return localStorage.getItem(verdictKey(tid)) || "";
  } catch {
    return "";
  }
}

function saveVerdict(tid, id) {
  try {
    localStorage.setItem(verdictKey(tid), id);
  } catch {
    /* ignore */
  }
}

function SrcBadge({ src, asOf, missing }) {
  const s = String(src || "").trim();
  const miss = missing || !s;
  const cls = miss
    ? "miss"
    : s === "MOEX" || s === "calendar"
      ? "moex"
      : s === "BCS"
        ? "bcs"
        : "";
  const text = miss ? "[НЕТ ДАННЫХ]" : s + (asOf ? ` · ${asOf}` : "");
  return <span className={"rv-src " + cls}>{text}</span>;
}

/**
 * KS review — /api/review/{ticker}
 * @param {{ ticker: string }} props
 */
export default function ReviewPanel({ ticker }) {
  const tid = String(ticker || "")
    .trim()
    .toUpperCase();
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const [verdict, setVerdict] = useState("");

  useEffect(() => {
    if (!tid) {
      setData(null);
      setErr("");
      setLoading(false);
      setVerdict("");
      return;
    }
    let cancelled = false;
    setLoading(true);
    setErr("");
    setData(null);
    setVerdict(loadVerdict(tid));

    (async () => {
      try {
        const payload = await getJson(
          `/api/review/${encodeURIComponent(tid)}`
        );
        if (cancelled) return;
        setData(payload);
      } catch (e) {
        if (cancelled) return;
        setErr(shortErr(e.message || e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [tid]);

  const onVerdict = useCallback(
    (id) => {
      if (!tid) return;
      setVerdict(id);
      saveVerdict(tid, id);
    },
    [tid]
  );

  if (!tid) {
    return (
      <section className="review-box">
        <div className="rv-head">
          <h3>Сверка</h3>
          <span className="rv-tag">KS</span>
        </div>
        <p className="muted">Кликни тикер — подтянется сверка (кэш / MOEX).</p>
      </section>
    );
  }

  const tag = data?.from_cache
    ? data.stale
      ? "кэш · stale"
      : "кэш"
    : data
      ? "live"
      : "KS";
  const sec = data?.sector || {};

  return (
    <section className="review-box" aria-label="Сверка факты">
      <div className="rv-head">
        <h3>Сверка · {tid}</h3>
        <span className="rv-tag">{tag}</span>
      </div>

      {loading && !data ? (
        <p className="muted">Сверка {tid}…</p>
      ) : null}
      {err && !data ? <p className="err-text">{err}</p> : null}

      {data ? (
        <>
          {data.kind === "bond" ? (
            <div className="rv-bond-title">
              {data.name || tid}
              {data.isin ? (
                <span className="isin">ISIN {data.isin}</span>
              ) : null}
            </div>
          ) : (
            <div className="rv-sector">
              <span className="rv-chip">{sec.label || "сектор ?"}</span>
              {sec.look_for ? (
                <div className="rv-look">
                  <span>Смотрим:</span> {sec.look_for}
                </div>
              ) : null}
            </div>
          )}

          {data.position_line ? (
            <p className="rv-pos">{data.position_line}</p>
          ) : null}
          {data.error ? (
            <p className="err-text">{String(data.error).slice(0, 180)}</p>
          ) : null}

          <div className="rv-grid">
            {(data.fields || []).map((f, i) => {
              const missing = !!f.missing;
              return (
                <div className="rv-cell" key={`${f.label || i}-${i}`}>
                  <div className="k">{f.label || ""}</div>
                  <div className={"v" + (missing ? " miss" : "")}>
                    {missing ? "[НЕТ ДАННЫХ]" : f.value || "—"}
                  </div>
                  <SrcBadge
                    src={missing ? "" : f.source}
                    asOf={missing ? "" : f.as_of}
                    missing={missing}
                  />
                </div>
              );
            })}
          </div>

          <div className="rv-flags">
            <div className="fk">Красные флаги</div>
            <p className="rv-legend">пусто · серое (глянуть) · красное</p>
            <ul>
              {(data.flags || []).map((f, i) => {
                const st = f.state || "empty";
                const cls =
                  st === "bad" ? "bad" : st === "warn" ? "warn" : "";
                return (
                  <li className={cls} key={`${f.label || i}-${i}`}>
                    <span className="dot" aria-hidden="true" />
                    {f.label || ""}
                  </li>
                );
              })}
            </ul>
          </div>

          <div className="rv-verdict">
            <div className="vk">Итог сверки (твой клик)</div>
            <div className="rv-verdict-btns">
              {REVIEW_VERDICTS.map((v) => (
                <button
                  key={v.id}
                  type="button"
                  className={verdict === v.id ? "on" : ""}
                  onClick={() => onVerdict(v.id)}
                >
                  {v.label}
                </button>
              ))}
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}
