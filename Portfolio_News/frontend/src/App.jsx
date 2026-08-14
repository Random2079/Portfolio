import { useCallback, useEffect, useMemo, useState } from "react";

const API = "";
const KIND_LABEL = { all: "Все", equity: "Акции", bond: "Облигации", fund: "Фонды" };
const KIND_BADGE = { equity: "акция", bond: "облигация", fund: "фонд" };

async function getJson(path) {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}

export default function App() {
  const [tickers, setTickers] = useState([]);
  const [allNews, setAllNews] = useState([]);
  const [selected, setSelected] = useState(null);
  const [kindFilter, setKindFilter] = useState("all");
  const [sectorFilter, setSectorFilter] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [pollInfo, setPollInfo] = useState(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const [t, n] = await Promise.all([getJson("/api/tickers"), getJson("/api/news?limit=200")]);
      setTickers(t);
      setAllNews(n);
    } catch (e) {
      setError(String(e.message || e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const counts = useMemo(() => {
    const equity = tickers.filter((t) => t.kind === "equity").length;
    const bond = tickers.filter((t) => t.kind === "bond").length;
    const fund = tickers.filter((t) => t.kind === "fund").length;
    return { equity, bond, fund };
  }, [tickers]);

  const filteredTickers = useMemo(() => {
    let list = tickers;
    if (kindFilter !== "all") list = list.filter((t) => t.kind === kindFilter);
    if (kindFilter === "equity" && sectorFilter) {
      list = list.filter((t) => (t.category || "") === sectorFilter);
    }
    return list;
  }, [tickers, kindFilter, sectorFilter]);

  const sectors = useMemo(() => {
    const set = new Set();
    for (const t of tickers) {
      if (t.kind === "equity" && t.category) set.add(t.category);
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b, "ru"));
  }, [tickers]);

  const news = useMemo(() => {
    if (selected) return allNews.filter((n) => n.ticker_id === selected);
    const ids = new Set(filteredTickers.map((t) => t.id));
    if (kindFilter === "all" && !sectorFilter) return allNews;
    return allNews.filter((n) => ids.has(n.ticker_id));
  }, [allNews, selected, filteredTickers, kindFilter, sectorFilter]);

  function setKind(key) {
    setKindFilter(key);
    setSectorFilter(null);
    setSelected(null);
  }

  async function runPoll() {
    setBusy(true);
    setError("");
    try {
      const stats = await fetch(`${API}/api/poll?notify=true`, { method: "POST" }).then((r) => {
        if (!r.ok) throw new Error(`poll ${r.status}`);
        return r.json();
      });
      setPollInfo(stats);
      await load();
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <header>
        <div>
          <h1>Portfolio News</h1>
          <p>
            {tickers.length} бумаг · {counts.equity} акций · {counts.bond} облигаций · {counts.fund} фондов
            {pollInfo ? ` · last poll +${pollInfo.inserted}` : ""}
          </p>
        </div>
        <div className="actions">
          <button type="button" className="secondary" onClick={load} disabled={busy}>
            Обновить
          </button>
          <button type="button" onClick={runPoll} disabled={busy}>
            {busy ? "Опрос…" : "Опросить сейчас"}
          </button>
        </div>
      </header>

      <div className="filters">
        {["all", "equity", "bond", "fund"].map((key) => {
          const count = key === "all" ? tickers.length : tickers.filter((t) => t.kind === key).length;
          return (
            <button
              key={key}
              type="button"
              className={`chip${kindFilter === key ? " active-filter" : ""}`}
              onClick={() => setKind(key)}
            >
              {KIND_LABEL[key]} ({count})
            </button>
          );
        })}
      </div>

      {kindFilter === "equity" ? (
        <div className="sectors">
          <button
            type="button"
            className={`chip${!sectorFilter ? " active-filter" : ""}`}
            onClick={() => {
              setSectorFilter(null);
              setSelected(null);
            }}
          >
            Все сектора
          </button>
          {sectors.map((sec) => (
            <button
              key={sec}
              type="button"
              className={`chip${sectorFilter === sec ? " active-filter" : ""}`}
              onClick={() => {
                setSectorFilter(sec);
                setSelected(null);
              }}
            >
              {sec} ({tickers.filter((t) => t.kind === "equity" && t.category === sec).length})
            </button>
          ))}
        </div>
      ) : null}

      {error ? <div className="error">API: {error}. Запущен ли backend на :8765?</div> : null}

      <div className="layout">
        <aside className="panel">
          <h2>Тикеры · {filteredTickers.length}</h2>
          <ul className="ticker-list">
            {filteredTickers.map((t) => (
              <li key={t.id}>
                <button
                  type="button"
                  className={selected === t.id ? "active" : ""}
                  onClick={() => setSelected(t.id)}
                >
                  <span className={`badge ${t.kind}`}>{KIND_BADGE[t.kind] || t.kind}</span>
                  <span className="id">{t.id}</span>
                  <span className="name">
                    {t.name}
                    {t.kind === "equity" && t.category ? ` · ${t.category}` : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <main className="panel">
          <h2>
            {selected
              ? `Новости · ${selected}`
              : kindFilter === "equity" && sectorFilter
                ? `Лента · акции · ${sectorFilter}`
                : kindFilter !== "all"
                  ? `Лента · ${KIND_LABEL[kindFilter].toLowerCase()}`
                  : "Лента"}
          </h2>
          {news.length === 0 ? (
            <div className="empty">Пока пусто. Нажми «Опросить сейчас» или смени фильтр.</div>
          ) : (
            <ul className="news-list">
              {news.map((n) => (
                <li key={n.id} className="news-item">
                  <a href={n.url} target="_blank" rel="noreferrer">
                    {n.title}
                  </a>
                  <div className="meta">
                    <span>{n.ticker_id}</span>
                    <span>{n.source}</span>
                    <span>{n.published_at ? new Date(n.published_at).toLocaleString("ru-RU") : "—"}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </main>
      </div>
    </div>
  );
}
