import { useCallback, useEffect, useMemo, useState } from "react";

const API = "";

async function getJson(path) {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}

export default function App() {
  const [tickers, setTickers] = useState([]);
  const [news, setNews] = useState([]);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [pollInfo, setPollInfo] = useState(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const [t, n] = await Promise.all([
        getJson("/api/tickers"),
        getJson(selected ? `/api/news?ticker=${encodeURIComponent(selected)}&limit=80` : "/api/news?limit=80"),
      ]);
      setTickers(t);
      setNews(n);
    } catch (e) {
      setError(String(e.message || e));
    }
  }, [selected]);

  useEffect(() => {
    load();
  }, [load]);

  const counts = useMemo(() => {
    const equity = tickers.filter((t) => t.kind === "equity").length;
    const bond = tickers.filter((t) => t.kind === "bond").length;
    return { equity, bond };
  }, [tickers]);

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
            {tickers.length} бумаг · {counts.equity} акций · {counts.bond} облигаций
            {pollInfo ? ` · last poll +${pollInfo.inserted}` : ""}
          </p>
        </div>
        <div className="actions">
          <button type="button" className="secondary" onClick={() => setSelected(null)}>
            Все
          </button>
          <button type="button" className="secondary" onClick={load} disabled={busy}>
            Обновить
          </button>
          <button type="button" onClick={runPoll} disabled={busy}>
            {busy ? "Опрос…" : "Опросить сейчас"}
          </button>
        </div>
      </header>

      {error ? <div className="error">API: {error}. Запущен ли backend на :8765?</div> : null}

      <div className="layout">
        <aside className="panel">
          <h2>Тикеры</h2>
          <ul className="ticker-list">
            {tickers.map((t) => (
              <li key={t.id}>
                <button
                  type="button"
                  className={selected === t.id ? "active" : ""}
                  onClick={() => setSelected(t.id)}
                >
                  <span className={`badge ${t.kind}`}>{t.kind}</span>
                  <span className="id">{t.id}</span>
                  <span className="name">{t.name}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <main className="panel">
          <h2>{selected ? `Новости · ${selected}` : "Лента"}</h2>
          {news.length === 0 ? (
            <div className="empty">Пока пусто. Нажми «Опросить сейчас» или CLI: python -m portfolio_news once</div>
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
