import { useEffect, useMemo, useRef, useState } from "react";
import { createChart } from "lightweight-charts";
import { getJson } from "./api";
import { fmtRub, shortErr } from "./format";

function dayHuman(iso) {
  const p = String(iso || "").split("-");
  if (p.length < 3) return iso || "—";
  return `${p[2]}.${p[1]}.${p[0]}`;
}

/**
 * K6 capital curve — /api/capital (weekly points), LWC area like vanilla Chart.js block.
 */
export default function CapitalChart() {
  const wrapRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const [points, setPoints] = useState([]);
  const [status, setStatus] = useState("Загрузка…");
  const [err, setErr] = useState(false);
  const [hover, setHover] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        let data;
        try {
          data = await getJson("/api/capital?days=1100");
        } catch {
          data = await getJson("/api/capital?days=900");
        }
        if (cancelled) return;
        const pts = Array.isArray(data?.points) ? data.points : [];
        setPoints(pts);
        setErr(false);
        if (!pts.length) {
          setStatus(
            "Пока одна точка появится после удачного ответа брокера. История начнётся с сегодня."
          );
          setHover(null);
        }
      } catch (e) {
        if (cancelled) return;
        setPoints([]);
        setHover(null);
        setErr(true);
        setStatus(shortErr(e.message || e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const statusLine = useMemo(() => {
    if (err || !points.length) return status;
    const first = points[0];
    const last = points[points.length - 1];
    if (points.length === 1) {
      return (
        "Пока только сегодня: " +
        fmtRub(last.total_value, { digits: 0 }) +
        " — история подтянется с сделок"
      );
    }
    const a = Number(first.total_value);
    const b = Number(last.total_value);
    const d = b - a;
    const sign = d > 0 ? "+" : "";
    return (
      "Недели (сделки×биржа) " +
      points.length +
      " тчк · " +
      dayHuman(first.day) +
      " → " +
      dayHuman(last.day) +
      " · Δ " +
      sign +
      fmtRub(d, { digits: 0 })
    );
  }, [points, status, err]);

  useEffect(() => {
    if (!points.length) return;
    setHover(points[points.length - 1]);
  }, [points]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el || !points.length) {
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
        seriesRef.current = null;
      }
      return;
    }

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
      seriesRef.current = null;
    }

    const chart = createChart(el, {
      width: el.clientWidth,
      height: 200,
      layout: {
        background: { color: "transparent" },
        textColor: "#9bb0c9",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(155, 176, 201, 0.08)" },
        horzLines: { color: "rgba(155, 176, 201, 0.08)" },
      },
      rightPriceScale: {
        borderVisible: false,
        scaleMargins: { top: 0.12, bottom: 0.08 },
      },
      timeScale: {
        borderVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      crosshair: {
        horzLine: { visible: false, labelVisible: false },
        vertLine: {
          color: "rgba(47, 155, 120, 0.45)",
          style: 3,
          labelVisible: false,
        },
      },
    });

    const series = chart.addAreaSeries({
      lineColor: "#2f9b78",
      topColor: "rgba(47, 155, 120, 0.28)",
      bottomColor: "rgba(47, 155, 120, 0.02)",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerRadius: 4,
    });

    const data = points
      .map((p) => {
        const time = String(p.day || "").slice(0, 10);
        const value = Number(p.total_value);
        if (!time || !Number.isFinite(value)) return null;
        return { time, value };
      })
      .filter(Boolean);

    series.setData(data);
    chart.timeScale().fitContent();

    chart.subscribeCrosshairMove((param) => {
      if (!param || !param.time) {
        setHover(points[points.length - 1] || null);
        return;
      }
      const t = String(param.time);
      const pt = points.find((p) => String(p.day).slice(0, 10) === t);
      setHover(pt || points[points.length - 1] || null);
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const ro = new ResizeObserver(() => {
      if (!wrapRef.current || !chartRef.current) return;
      chartRef.current.applyOptions({ width: wrapRef.current.clientWidth });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [points]);

  return (
    <section className="capital-box" aria-label="Капитал">
      <h2>Капитал</h2>
      <p className="lead">
        Сколько стоил весь портфель по неделям с 2024. Журнал × закрытие MOEX.
      </p>
      <div className="capital-wrap" ref={wrapRef} />
      {hover ? (
        <div className="capital-hover">
          <span className="hv">{fmtRub(hover.total_value, { digits: 0 })}</span>
          <span className="hd">{dayHuman(hover.day)} · неделя</span>
        </div>
      ) : null}
      <div className={"chart-status" + (err ? " err" : "")}>{statusLine}</div>
    </section>
  );
}
