# 03 · Источники новостей (RSS + Pulse allowlist)

| | |
|---|---|
| **Код** | [`sources/base.py`](../../portfolio_news/sources/base.py) · [`google_news_ru.py`](../../portfolio_news/sources/google_news_ru.py) · [`smartlab.py`](../../portfolio_news/sources/smartlab.py) · [`pulse_allowlist.py`](../../portfolio_news/sources/pulse_allowlist.py) + [`pulse_allowlist.json`](../../portfolio_news/sources/pulse_allowlist.json) |
| **Слой** | A · **§7S** Pulse v1 |
| **Статус** | ✅ RSS; Pulse allowlist v1 (Interfax+Advokat SSR) |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) · [MAP §7S](../../MAP.md) |

## Вход / выход

- Вход: тикер / имя / kind (бонды — по эмитенту/имени, не ISIN вслепую).
- Выход: список кандидатов URL+title+published для дедупа в poller.
- Pulse: профили из `pulse_allowlist.json` → `v1` only; mirror `tbank-online.com`; source tag `pulse_allowlist`.

## Не здесь

- ИИ-фильтр → [08-ai-noise](08-ai-noise.md) · план A в [MAP §7](../../MAP.md).
- Maybe/IR pack / TG Архивариус — [MAP §7S](../../MAP.md).
