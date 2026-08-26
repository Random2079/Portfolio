# 07 · БКС holdings (read-only)

| | |
|---|---|
| **Код** | [`bcs_client.py`](../../portfolio_news/bcs_client.py) · [`tests/test_bcs_client.py`](../../tests/test_bcs_client.py) |
| **Слой** | D |
| **Статус** | ✅ каркас (живой токен — у пользователя локально) |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

## Вход / выход

- `BCS_TRADE_REFRESH_TOKEN` + `BCS_TRADE_CLIENT_ID=trade-api-read` в `.env`.
- OAuth refresh → portfolio/limits → `Holding` / snapshot.
- UI: вкладка «Позиции БКС» + banner на других вкладках.

## Запреты

- Не `trade-api-write`.
- Не коммитить `.env` / токен. Не кидать токен в чат.

## Проверка

```powershell
pytest tests/test_bcs_client.py -q
# с токеном: GET /api/holdings/status → configured
```
