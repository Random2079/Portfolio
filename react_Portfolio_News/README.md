# Portfolio News · React (`react_Portfolio_News`)

Новый UI-трек (R0+). **API и ванильный бэкап** — в соседней папке `Portfolio_News/`.

Карта: [`../Portfolio_News/MAP.md`](../Portfolio_News/MAP.md) §7R.

## Запуск

Терминал 1 — ванильный backend:

```powershell
cd ..\Portfolio_News
python -m portfolio_news serve
```

Терминал 2 — React:

```powershell
cd ..\react_Portfolio_News
npm install
npm run dev
```

Открыть: http://127.0.0.1:5173/  
Бэкап ванили: http://127.0.0.1:8765/

Vite проксирует `/api` → `127.0.0.1:8765`.

## Слои

| Слой | Что |
|------|-----|
| **R0** | Шелл, тема, motion, health + day KPI |
| R1… | см. MAP §7R |
