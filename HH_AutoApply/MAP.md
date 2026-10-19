# MAP — HH_AutoApply (IDEA-026)

👀 Скан: **📍 → 🎯 → 🟡 → 🚫**. ⏭️ ✅ / 📖 / 🗄️.

| | |
|---|---|
| 📍 **Где мы** | **E1 Kwork LIVE** ✅ (DeepSeek cover + час-цикл + лента) |
| 🎯 **Фокус** | смоук `kwork-login` → `kwork-tick --dry-run` → LIVE тик / UI ▶ Старт |
| 📁 **Код** | `kwork_search` · `kwork_ai` · `kwork_usage` · `kwork_apply` · `kwork_loop` · `ui.py` |

---

## Канон данных

| Источник | Роль |
|---|---|
| `config.daily_limit` | HH **100**/день |
| `config.kwork.*` | Kwork лимит **15**/день, тик **3**, интервал **60** мин |
| `data/apply_state.json` | HH счётчик дня |
| `data/kwork_apply_state.json` | Kwork счётчик / applied_ids |
| `data/kwork_apply_log.jsonl` | лента заявок (buyer / title / url / cover) |
| `data/kwork_ai_usage.jsonl` | счётчик токенов DeepSeek (вызовы / $ / баланс) |
| `data/kwork_storage_state.json` | 🔒 сессия Kwork (не hh) |
| `data/storage_state.json` | 🔒 сессия hh |
| `data/yj_hh_cache.json` | кеш Young&Junior → hh vacancy id |
| `data/ranked_tg_*.json` | очередь apply из ТГ/YJ |
| `DEEPSEEK_API_KEY` | `.env` (Portfolio_News / YT / DS_Projects) |

---

## Очередь

| # | Что | Статус |
|---|-----|--------|
| A–D4b | HH ядро + UI LIVE | ✅ |
| E0 | `tg-scan` | ✅ |
| **E0b** | YJ→HH (`tg-scan --resolve-hh` → `ranked_tg_*`) | ✅ |
| **E1** | Kwork LIVE + DeepSeek + UI цикл | ✅ |
| — | автоотклик в Telegram | 🚫 (другой агент / нет API) |
| — | обход капчи | 🚫 |

📖 **HH:** 🔍 Поиск · 📨 Отклики LIVE · 📄 Резюме↑ · ⏸ Отмена · 🔄 Статистика · 🗑 Сброс лога.  
📖 **Kwork:** ▶ Старт цикла · ⏸ Стоп · 🔄 Тик · 🧪 Dry-run · 🔑 Login · 📨 Лента.

---

## Смоук

```text
wscript //nologo launch.vbs
# Kwork → 🔑 Login → 🧪 Dry-run → 📨 Лента
# ▶ Старт цикла → тик сейчас + через 60 мин

python -m hh_auto kwork-login
python -m hh_auto kwork-tick --dry-run --limit 1
python -m hh_auto kwork-tick --limit 1
python -m hh_auto kwork-feed

python -m hh_auto tg-scan --resolve-hh --resolve-limit 10
python -m hh_auto apply --ranked data/ranked_tg_….json --dry-run
```

---

## 🚫 Запреты

- Капчу не обходить · секреты / `*_storage_state` не в git · пуш по просьбе
- В cover не светить ИИ / Cursor / агента
