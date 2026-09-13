# Parts — INDEX

| # | Part | Статус | Код |
|---|------|--------|-----|
| 01 | [core](01-core.md) | ✅ | `config.py`, `db.py`, `cli.py` |
| 02 | [tickers](02-tickers.md) | ✅ | `import_tickers.py`, `tickers.example.json` |
| 03 | [sources](03-sources.md) | ✅ | `sources/*` |
| 04 | [poll-toast](04-poll-toast.md) | ✅ | `poller.py`, `poll_job.py`, `notify_toast.py` |
| 05 | [api-ui](05-api-ui.md) | ✅ A–D / 🟡 E | `api.py`, `static/dashboard-demo.html` |
| 06 | [moex](06-moex.md) | ✅ | `metrics_moex.py` |
| 07 | [bcs](07-bcs.md) | ✅ каркас | `bcs_client.py` |
| 08 | [ai-noise](08-ai-noise.md) | ⬜ | — |
| 09 | [watch-phone](09-watch-phone.md) | ⬜ | CLI `watch` есть; авто/телефон нет |
| 10 | [bcs-terminal](10-bcs-terminal.md) | 🟡 K0–K8 · KA–KB ✅ → K9 | история / Focus / график / карточка / капитал / календарь / сделки |

**Фокус сейчас:** part 10 (K9→). Новостной хвост E–J — по остаточному принципу.

Порядок для нового агента: TZ → 07 + 10; обзор 01–05 при необходимости.
