# Документация Portfolio_News

| Документ | Назначение |
|----------|------------|
| [TZ.md](TZ.md) | Главное ТЗ (слои, не делаем, проверка) |
| [PROMPT_FOR_AGENT.md](PROMPT_FOR_AGENT.md) | Блок для нового чата |
| [parts/INDEX.md](parts/INDEX.md) | Карта parts |

## Parts → код

| Part | Код |
|------|-----|
| [01-core](parts/01-core.md) | `portfolio_news/config.py`, `db.py`, `cli.py` |
| [02-tickers](parts/02-tickers.md) | `import_tickers.py`, `tickers.example.json` |
| [03-sources](parts/03-sources.md) | `sources/*` |
| [04-poll-toast](parts/04-poll-toast.md) | `poller.py`, `poll_job.py`, `notify_toast.py` |
| [05-api-ui](parts/05-api-ui.md) | `api.py`, `static/index.html` |
| [06-moex](parts/06-moex.md) | `metrics_moex.py` |
| [07-bcs](parts/07-bcs.md) | `bcs_client.py` |
| [08-ai-noise](parts/08-ai-noise.md) | *(план)* |
| [09-watch-phone](parts/09-watch-phone.md) | CLI `watch` + план авто/телефон |
| [10-bcs-terminal](parts/10-bcs-terminal.md) | Свой БКС: история / графики / разбор (K0–K6) |
