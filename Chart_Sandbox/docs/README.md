# docs — карта для агента

| Part | Файл кода | Слой |
|------|-----------|------|
| [01-moex](parts/01-moex.md) | `app/moex.py` | K1 |
| [02-api-cache](parts/02-api-cache.md) | `app/main.py`, `app/cache.py` | K1–K2 |
| [03-ui-chart](parts/03-ui-chart.md) | `static/index.html` | K1 |
| [04-markers](parts/04-markers.md) | `data/markers.json` + API/UI | K3 |
| [05-bar-replay](parts/05-bar-replay.md) | `static/index.html` replay | K4 |

Главное ТЗ: [TZ.md](TZ.md). Промпт нового чата: [PROMPT_FOR_AGENT.md](PROMPT_FOR_AGENT.md).
