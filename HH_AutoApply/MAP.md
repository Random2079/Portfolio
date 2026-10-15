# MAP — HH_AutoApply (IDEA-026)

👀 Скан: **📍 → 🎯 → 🟡 → 🚫**. ⏭️ ✅ / 📖 / 🗄️.

| | |
|---|---|
| 📍 **Где мы** | **D2** ярлык=живой код ✅ · заготовка cover ✅ |
| 🎯 **Фокус** | **D3** кастом UI из config (тема/шрифт) |
| 📁 **Код** | `launch.vbs` · `launch_gui.py` · `ui.py` · `apply.py` · `config*.json` |

---

## Канон данных

| Источник | Роль |
|---|---|
| `data/apply_state.json` | **день**: `date` / `count` / `applied_ids` → лимит 40/день |
| `data/apply_log.jsonl` | **лента**: статусы + `cover_filled` при live |
| `data/resume_state.json` | последнее поднятие резюме (cooldown) |
| `config.json` → `cover_template` | текст письма; `{title}` `{company}` |
| `data/storage_state.json` | 🔒 логин Playwright — **не в git** |

---

## Очередь (по пунктам)

| # | Что | Статус |
|---|-----|--------|
| A–C1 | search/apply/UI/launch.vbs | ✅ |
| **D1** | кнопка Отмена + textbox read-only | ✅ |
| **D2** | ярлык → живой `.py` (stamp в UI / лог) + cover-заготовка | ✅ |
| **D3** | кастом UI из config (тема/шрифт — что можно) | ⬜ дальше |
| **D4** | headless фон (не дёргать глаз) | ⬜ |
| **D5** | отчёт «как работаю с агентом» | ✅ уже в чате |
| — | финальный текст cover в config (+ лёгкий кивок TTS/Portfolio) | ✅ |
| — | обход капчи | 🚫 |

📖 **Ярлык (D2):** `launch.vbs` → `pythonw launch_gui.py` → импорт `hh_auto.ui` с диска. Не exe. В окне строка `код ui.py @ <mtime>` — поменял ui.py → новый stamp без пересборки ярлыка.

📖 **Cover:** при apply, если в ranked нет `cover` — рендер из `cover_template`. Live: `_fill_cover_if_present` + в лог `cover_filled` / `cover_len`. Текст-заготовка в config — заменишь, когда кинешь.

---

## Смоук D2

```text
wscript //nologo launch.vbs
# в шапке UI: «код ui.py @ …» — запомни
# поправь пробел в hh_auto/ui.py, сохрани, закрой UI, снова ярлык
# stamp должен обновиться → принцип ок
```

---

## 🚫 Запреты

- Капчу не обходить
- `storage_state` / секреты не в git
- Пуш только по просьбе
- Не склеивать D3+D4 в один заход
