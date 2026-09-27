import { useEffect, useRef, useState } from "react";
import { createChart, CrosshairMode } from "lightweight-charts";
import { getJson } from "./api";
import { shortErr } from "./format";
import { assetClassOf, paperId } from "./holdings";

function candleDateKey(s) {
  const t = String(s || "").trim();
  return t ? t.slice(0, 10) : "";
}

function markerDateKey(s) {
  const t = String(s || "").trim();
  if (!t) return "";
  if (/^\d{4}-\d{2}-\d{2}/.test(t)) return t.slice(0, 10);
  const m = t.match(/(\d{2})\.(\d{2})\.(\d{4})/);
  if (m) return `${m[3]}-${m[2]}-${m[1]}`;
  return t.slice(0, 10);
}

function candlesToLwc(raw) {
  const bars = [];
  const vols = [];
  const seen = new Set();
  for (const c of raw || []) {
    const time = candleDateKey(c.begin || c.time);
    if (!time || seen.has(time)) continue;
    const close = c.close != null ? Number(c.close) : NaN;
    if (!Number.isFinite(close)) continue;
    const open =
      c.open != null && Number.isFinite(Number(c.open))
        ? Number(c.open)
        : close;
    let high =
      c.high != null && Number.isFinite(Number(c.high))
        ? Number(c.high)
        : Math.max(open, close);
    let low =
      c.low != null && Number.isFinite(Number(c.low))
        ? Number(c.low)
        : Math.min(open, close);
    if (high < Math.max(open, close)) high = Math.max(open, close);
    if (low > Math.min(open, close)) low = Math.min(open, close);
    seen.add(time);
    bars.push({ time, open, high, low, close });
    const vol = c.volume != null ? Number(c.volume) : NaN;
    vols.push({
      time,
      value: Number.isFinite(vol) && vol > 0 ? vol : 0,
      color:
        close >= open
          ? "rgba(38,166,154,0.45)"
          : Number.isFinite(vol) && vol > 0
            ? "rgba(239,83,80,0.45)"
            : "rgba(139,148,158,0.2)",
    });
  }
  bars.sort((a, b) => String(a.time).localeCompare(String(b.time)));
  vols.sort((a, b) => String(a.time).localeCompare(String(b.time)));
  return { bars, vols };
}

function markersToLwc(rawMarkers, candleTimes) {
  const times = candleTimes || [];
  function snap(dk) {
    if (!dk || !times.length) return "";
    if (times.includes(dk)) return dk;
    let best = "";
    for (let i = 0; i < times.length; i++) {
      if (times[i] <= dk) best = times[i];
      else break;
    }
    return best;
  }
  const byTime = {};
  for (const m of rawMarkers || []) {
    const dk = snap(markerDateKey(m.executed_at || m.time || ""));
    if (!dk) continue;
    const side = String(m.side || "").toLowerCase();
    if (side !== "buy" && side !== "sell") continue;
    if (!byTime[dk]) byTime[dk] = { time: dk, buy: false, sell: false };
    if (side === "buy") byTime[dk].buy = true;
    if (side === "sell") byTime[dk].sell = true;
  }
  const out = [];
  Object.keys(byTime)
    .sort()
    .forEach((k) => {
      const s = byTime[k];
      if (s.buy) {
        out.push({
          time: s.time,
          position: "belowBar",
          color: "#22c55e",
          shape: "circle",
          text: "покупка",
        });
      }
      if (s.sell) {
        out.push({
          time: s.time,
          position: "aboveBar",
          color: "#ef4444",
          shape: "circle",
          text: "продажа",
        });
      }
    });
  return out;
}

function chartYearStartKey() {
  try {
    const y = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Yekaterinburg",
      year: "numeric",
    }).format(new Date());
    return `${String(y).slice(0, 4)}-01-01`;
  } catch {
    return `${new Date().getFullYear()}-01-01`;
  }
}

function focusChartOnLocalYear(chart, bars) {
  if (!chart || !bars?.length) return;
  const ys = chartYearStartKey();
  let fromIdx = -1;
  for (let i = 0; i < bars.length; i++) {
    if (String(bars[i].time) >= ys) {
      fromIdx = i;
      break;
    }
  }
  if (fromIdx < 0) fromIdx = Math.max(0, bars.length - 260);
  const from = bars[fromIdx].time;
  const to = bars[bars.length - 1].time;
  try {
    chart.timeScale().setVisibleRange({ from, to });
  } catch {
    try {
      chart.timeScale().fitContent();
    } catch {
      /* ignore */
    }
  }
}

function kindHintFromHoldings(tid, holdings) {
  const h = (holdings || []).find((x) => paperId(x) === tid);
  if (!h) return "";
  const ac = assetClassOf(h);
  if (ac === "bond") return "bond";
  if (ac === "fund") return "fund";
  if (ac === "stock") return "equity";
  return "";
}

/**
 * K3 price chart — /api/chart/{ticker} + Lightweight Charts
 * @param {{ ticker: string, holdings?: object[], avgPrice?: number|null }} props
 */
export default function PriceChart({ ticker, holdings, avgPrice }) {
  const tid = String(ticker || "")
    .trim()
    .toUpperCase();
  const hostRef = useRef(null);
  const chartRef = useRef(null);
  const [status, setStatus] = useState("Выбери бумагу.");
  const [statusErr, setStatusErr] = useState(false);

  useEffect(() => {
    if (!tid) {
      if (chartRef.current) {
        try {
          chartRef.current.remove();
        } catch {
          /* ignore */
        }
        chartRef.current = null;
      }
      setStatus("Выбери бумагу.");
      setStatusErr(false);
      return;
    }

    let cancelled = false;
    const host = hostRef.current;
    setStatus(`Загрузка ${tid}…`);
    setStatusErr(false);

    if (chartRef.current) {
      try {
        chartRef.current.remove();
      } catch {
        /* ignore */
      }
      chartRef.current = null;
    }
    if (host) host.innerHTML = "";

    (async () => {
      try {
        const kind = kindHintFromHoldings(tid, holdings);
        let url = `/api/chart/${encodeURIComponent(tid)}`;
        if (kind) url += `?kind=${encodeURIComponent(kind)}`;
        const data = await getJson(url);
        if (cancelled) return;
        if (!data?.ok) {
          setStatus(`${tid} · ${shortErr(data?.error || "Нет графика")}`);
          setStatusErr(true);
          return;
        }
        const { bars, vols } = candlesToLwc(data.candles || []);
        if (!bars.length) {
          setStatus("Нет свечей MOEX для отрисовки.");
          setStatusErr(true);
          return;
        }
        if (!hostRef.current || cancelled) return;

        const chartH = Math.max(
          hostRef.current.clientHeight || 0,
          320
        );
        const chart = createChart(hostRef.current, {
          layout: {
            background: { color: "transparent" },
            textColor: "#c8cdd3",
          },
          grid: {
            vertLines: { color: "rgba(26,31,39,0.9)" },
            horzLines: { color: "rgba(26,31,39,0.9)" },
          },
          crosshair: {
            mode: CrosshairMode?.Normal ?? 0,
          },
          rightPriceScale: {
            borderColor: "#2a313c",
            scaleMargins: { top: 0.08, bottom: 0.28 },
          },
          timeScale: { borderColor: "#2a313c", timeVisible: false },
          width: Math.max(hostRef.current.clientWidth || 0, 100),
          height: chartH,
        });
        const series = chart.addCandlestickSeries({
          upColor: "#26a69a",
          downColor: "#ef5350",
          borderVisible: false,
          wickUpColor: "#26a69a",
          wickDownColor: "#ef5350",
        });
        series.setData(bars);

        const hasVol = vols.some((v) => v.value > 0);
        if (hasVol) {
          const volSeries = chart.addHistogramSeries({
            priceFormat: { type: "volume" },
            priceScaleId: "vol",
            lastValueVisible: false,
            priceLineVisible: false,
          });
          volSeries.setData(vols);
          try {
            chart.priceScale("vol").applyOptions({
              scaleMargins: { top: 0.78, bottom: 0 },
              borderVisible: false,
            });
          } catch {
            /* ignore */
          }
        } else {
          try {
            series.priceScale().applyOptions({
              scaleMargins: { top: 0.08, bottom: 0.08 },
            });
          } catch {
            /* ignore */
          }
        }

        const marks = markersToLwc(
          data.markers || [],
          bars.map((b) => b.time)
        );
        if (marks.length && series.setMarkers) series.setMarkers(marks);

        if (avgPrice != null && Number.isFinite(Number(avgPrice))) {
          try {
            series.createPriceLine({
              price: Number(avgPrice),
              color: "rgba(232,164,90,0.85)",
              lineWidth: 1,
              lineStyle: 2,
              axisLabelVisible: true,
              title: "avg",
            });
          } catch {
            /* ignore */
          }
        }

        focusChartOnLocalYear(chart, bars);
        chartRef.current = chart;

        const buyN = (data.markers || []).filter(
          (m) => String(m.side || "").toLowerCase() === "buy"
        ).length;
        const sellN = (data.markers || []).filter(
          (m) => String(m.side || "").toLowerCase() === "sell"
        ).length;
        const year = chartYearStartKey().slice(0, 4);
        setStatus(
          `${tid} · вид ${year} · ${data.n_candles || bars.length} свечей` +
            (data.from_cache
              ? data.stale
                ? " · кэш stale"
                : " · кэш"
              : " · live MOEX") +
            (data.board ? ` · ${data.board}` : "") +
            (data.kind === "bond" || data.price_unit === "rub_per_bond"
              ? " · ₽/шт"
              : "") +
            (marks.length
              ? ` · сделки ↑${buyN} ↓${sellN}`
              : " · сделок в кэше нет")
        );
        setStatusErr(false);

        const ro =
          typeof ResizeObserver !== "undefined"
            ? new ResizeObserver(() => {
                if (!hostRef.current || !chartRef.current) return;
                chartRef.current.applyOptions({
                  width: Math.max(hostRef.current.clientWidth || 0, 100),
                  height: Math.max(hostRef.current.clientHeight || 0, 320),
                });
              })
            : null;
        if (ro && hostRef.current) ro.observe(hostRef.current);

        // stash cleanup for this effect
        chart._pnRo = ro;
      } catch (e) {
        if (cancelled) return;
        setStatus(`${tid} · ${shortErr(e.message || e)}`);
        setStatusErr(true);
      }
    })();

    return () => {
      cancelled = true;
      if (chartRef.current) {
        try {
          if (chartRef.current._pnRo) chartRef.current._pnRo.disconnect();
          chartRef.current.remove();
        } catch {
          /* ignore */
        }
        chartRef.current = null;
      }
    };
  }, [tid, holdings, avgPrice]);

  return (
    <section className="chart-box">
      <div className="chart-toolbar">
        <span className="chart-ticker-label">{tid || "—"}</span>
        <span className="chart-hint">
          вид: этот год · ● зел./красн. · маркеры сделок BCS
        </span>
      </div>
      <div className="chart-wrap" ref={hostRef} />
      <p className={"chart-status" + (statusErr ? " err" : "")}>{status}</p>
    </section>
  );
}
