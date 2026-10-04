# 03 · Источники новостей (RSS + Pulse)

| | |
|---|---|
| **Код** | [`sources/base.py`](../../portfolio_news/sources/base.py) · [`google_news_ru.py`](../../portfolio_news/sources/google_news_ru.py) · [`smartlab.py`](../../portfolio_news/sources/smartlab.py) · [`pulse_allowlist.py`](../../portfolio_news/sources/pulse_allowlist.py) + json · [`pulse_news_ticker.py`](../../portfolio_news/sources/pulse_news_ticker.py) · [`telegram_allowlist.py`](../../portfolio_news/sources/telegram_allowlist.py) + json · [`e_disclosure.py`](../../portfolio_news/sources/e_disclosure.py) + json |
| **Слой** | A · **§7S** Pulse/TG + e-disclosure |
| **Статус** | ✅ RSS; Pulse allowlist + news-by-ticker; Telegram v1; e-disclosure (Азипи) |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) · [MAP §7S](../../MAP.md) |

## Вход / выход

- Вход: тикер / имя / kind (бонды — по эмитенту/имени, не ISIN вслепую).
- Выход: список кандидатов URL+title+published для дедупа в poller.
- Pulse allowlist: профили из `pulse_allowlist.json` → `v1` only; mirror `tbank-online.com`; tag `pulse_allowlist`.
- Pulse news-by-ticker: `/invest/stocks/{TICKER}/news/` → `investSocialNewsByTicker`; tag `pulse_news_ticker`; **equity only**.
- Telegram allowlist: `t.me/s/{slug}` preview; v1 = Рубиндей · РКИ · Интерфакс.Рынки; `i_moex` rejected; tag `telegram_allowlist`.
- Bond→issuer: `bond_issuer.py` + json — poll query = issuer aliases (не серия БО).
- e-disclosure: `e_disclosure.py` + json · tag `e_disclosure` · в `default_sources()`. Лента Азипи `/?msg_day=` (офиц. факты по ИНН/эмитенту). Interfax `company.aspx` — антибот, парсер HTML есть, fetch не через urllib.

## Не здесь

- ИИ-фильтр → [08-ai-noise](08-ai-noise.md) · план A в [MAP §7](../../MAP.md).
- Maybe/IR pack / bond→company / ещё TG (Архивариус) — [MAP §7S](../../MAP.md).
