# 03 · Источники новостей (RSS + Pulse)

| | |
|---|---|
| **Код** | [`sources/base.py`](../../portfolio_news/sources/base.py) · [`google_news_ru.py`](../../portfolio_news/sources/google_news_ru.py) · [`smartlab.py`](../../portfolio_news/sources/smartlab.py) · [`pulse_allowlist.py`](../../portfolio_news/sources/pulse_allowlist.py) + [`pulse_allowlist.json`](../../portfolio_news/sources/pulse_allowlist.json) · [`pulse_news_ticker.py`](../../portfolio_news/sources/pulse_news_ticker.py) · [`telegram_allowlist.py`](../../portfolio_news/sources/telegram_allowlist.py) + json |
| **Слой** | A · **§7S** Pulse v1 + news-by-ticker + TG preview |
| **Статус** | ✅ RSS; Pulse allowlist v1; Pulse news-by-ticker (equity); Telegram Рубиндей |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) · [MAP §7S](../../MAP.md) |

## Вход / выход

- Вход: тикер / имя / kind (бонды — по эмитенту/имени, не ISIN вслепую).
- Выход: список кандидатов URL+title+published для дедупа в poller.
- Pulse allowlist: профили из `pulse_allowlist.json` → `v1` only; mirror `tbank-online.com`; tag `pulse_allowlist`.
- Pulse news-by-ticker: `/invest/stocks/{TICKER}/news/` → `investSocialNewsByTicker`; tag `pulse_news_ticker`; **equity only**.
- Telegram allowlist: `t.me/s/{slug}` preview; v1 = Рубиндей · РКИ · Интерфакс.Рынки; `i_moex` rejected; tag `telegram_allowlist`.

## Не здесь

- ИИ-фильтр → [08-ai-noise](08-ai-noise.md) · план A в [MAP §7](../../MAP.md).
- Maybe/IR pack / bond→company / ещё TG (Архивариус) — [MAP §7S](../../MAP.md).
