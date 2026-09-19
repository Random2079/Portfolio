# 03 · Источники новостей (RSS)

| | |
|---|---|
| **Код** | [`sources/base.py`](../../portfolio_news/sources/base.py) · [`google_news_ru.py`](../../portfolio_news/sources/google_news_ru.py) · [`smartlab.py`](../../portfolio_news/sources/smartlab.py) |
| **Слой** | A |
| **Статус** | ✅ (шум ленты — слой F) |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

## Вход / выход

- Вход: тикер / имя / kind (бонды — по эмитенту/имени, не ISIN вслепую).
- Выход: список кандидатов URL+title+published для дедупа в poller.

## Не здесь

- ИИ-фильтр → [08-ai-noise](08-ai-noise.md) · план A в [MAP §7](../../MAP.md).
