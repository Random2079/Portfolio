# Промпт для нового чата — Chart_Sandbox (IDEA-024)

> Workspace: `C:\Users\Home\OneDrive\Desktop\DS_Projects\Chart_Sandbox`  
> ТЗ: [`docs/TZ.md`](TZ.md). Дальше: `делаем K1` / `делаем K2` / …

Скопируй блок ниже в новый Agent-чат (или attach `/work-from-tz`).

---

```
Chart_Sandbox (IDEA-024): локальный график «как TradingView».
Workspace: C:\Users\Home\OneDrive\Desktop\DS_Projects\Chart_Sandbox
Читай docs/TZ.md. Пользователь: Тё Ян. Git: не коммить/пушь без просьбы.

Стек: FastAPI + static HTML/JS + Lightweight Charts (CDN). Данные — свой API, MOEX ISS дневные OHLC. Не iframe TV Widget. Не встраивать в Portfolio_News.

Слои: K1 свечи → K2 кэш → K3 маркеры. Один слой за фразу «делаем KN».
Критерий: localhost → тикер → свечи с зумом, данные через /api/candles.
```
