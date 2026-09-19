# Документация Portfolio_News

| Документ | Назначение |
|----------|------------|
| **[MAP.md](../MAP.md)** | **Главная карта (статус, очередь, F-A) — открывай её** |
| [TZ.md](TZ.md) | Техслои для кода |
| [PROMPT_FOR_AGENT.md](PROMPT_FOR_AGENT.md) | Блок для нового чата |
| [parts/INDEX.md](parts/INDEX.md) | Оглавление parts |

## Parts → код

| Part | Код |
|------|-----|
| [01-core](parts/01-core.md) | `portfolio_news/config.py`, `db.py`, `cli.py` |
| [02-tickers](parts/02-tickers.md) | `import_tickers.py`, `tickers.example.json` |
| [03-sources](parts/03-sources.md) | `sources/*` |
| [04-poll-toast](parts/04-poll-toast.md) | `poller.py`, `poll_job.py`, `notify_toast.py` |
| [05-api-ui](parts/05-api-ui.md) | `api.py`, `static/dashboard-demo.html` |
| [06-moex](parts/06-moex.md) | `metrics_moex.py` |
| [07-bcs](parts/07-bcs.md) | `bcs_client.py` |
| [08-ai-noise](parts/08-ai-noise.md) | *(план)* |
| [09-watch-phone](parts/09-watch-phone.md) | CLI `watch` + план авто/телефон |
| [10-bcs-terminal](parts/10-bcs-terminal.md) | Свой БКС: история / графики / разбор (K0–K9) |
| [11-review-checkpoint](parts/11-review-checkpoint.md) | **KS** сверка · `review_facts.py` + `/api/review` |
