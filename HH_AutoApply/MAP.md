# MAP — HH_AutoApply (IDEA-026)

👀 Скан: **📍 → 🎯 → 🟡 → 🚫**. ⏭️ ✅ / 📖 / 🗄️.

| | |
|---|---|
| 📍 **Где мы** | UI кнопки: **Поиск / LIVE / Резюме / Отмена** ✅ · лог сброшен |
| 🎯 **Фокус** | смоук: Поиск → Отклики LIVE (headless) |
| 📁 **Код** | `hh_auto/ui.py` · `stats.archive_and_clear_log` |

---

## Канон данных

| Источник | Роль |
|---|---|
| `config.daily_limit` | **100**/день |
| `data/apply_state.json` | счётчик дня |
| `data/apply_log.jsonl` | лента (можно сбросить кнопкой) |
| `config.playwright.headless` | фон без окна |
| `data/storage_state.json` | 🔒 не в git |

---

## Очередь

| # | Что | Статус |
|---|-----|--------|
| A–D4 | ядро + headless + cover | ✅ |
| **D4b** | UI: LIVE-кнопки, убран dry-run, сброс лога | ✅ |
| — | обход капчи | 🚫 |

📖 **Кнопки:** 🔍 Поиск · 📨 Отклики LIVE (поле «за раз») · 📄 Резюме↑ · ⏸ Отмена · 🔄 Статистика · 🗑 Сброс лога.  
Dry-run из UI убран (CLI `apply --dry-run` жив).

---

## Смоук

```text
wscript //nologo launch.vbs
# Поиск → Отклики LIVE (20) → Chromium не вылезает · счётчик растёт
# Сброс лога → лента пустая, архив в data/apply_log_archive_*.jsonl
```

---

## 🚫 Запреты

- Капчу не обходить · секреты не в git · пуш по просьбе
