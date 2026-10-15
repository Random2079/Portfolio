# MAP — HH_AutoApply (IDEA-026)

👀 Скан: **📍 → 🎯 → 🟡 → 🚫**. ⏭️ ✅ / 📖 / 🗄️.

| | |
|---|---|
| 📍 **Где мы** | UI ✅ · **ярлык `launch.vbs`** как у YT (без exe) |
| 🎯 **Фокус** | смоук двойной клик / headless apply в фоне |
| 📁 **Код** | `launch.vbs` · `launch_gui.py` · `hh_auto/ui.py` · `stats.py` |

---

## Канон данных

| Источник | Роль |
|---|---|
| `data/apply_state.json` | **день**: `date` / `count` / `applied_ids` → лимит 40/день |
| `data/apply_log.jsonl` | **лента**: статусы ok/skip/error/captcha + resume events |
| `data/resume_state.json` | последнее поднятие резюме (cooldown) |
| `data/storage_state.json` | 🔒 логин Playwright — **не в git** |

---

## Очередь

| # | Что | Статус |
|---|-----|--------|
| A | search / score / cover | ✅ |
| B | Playwright login + apply | ✅ |
| **C** | **UI отчётность + raise resume** | ✅ |
| **C1** | **ярлык launch.vbs** (как YouTube_Translator) | ✅ |
| — | headless apply из UI (не дёргать Chromium) | ⬜ дальше |
| — | авто-цикл по расписанию | ⬜ не сейчас |
| — | обход капчи | 🚫 |

---

## Смоук

```text
cd HH_AutoApply
pip install -r requirements.txt
python -m playwright install chromium
# ярлык (без консоли, как YT):
wscript //nologo launch.vbs
# или CLI:
python -m hh_auto ui
python -m hh_auto stats
python -m hh_auto raise-resume
```

Ярлык на рабочий стол → ПКМ на `launch.vbs` → «Создать ярлык» / перетащить. Код меняешь — пересобирать ничего не надо.

Ожидание `raise-resume`: `raised` | `already_raised_skip` | `captcha` | `error`.
Повтор без `--force` → skip по cooldown (не спам).

---

## 🚫 Запреты

- Капчу не обходить — стоп + видно в UI/логе
- `storage_state.json` / токены / живой `config.json` с секретами — не коммитить
- Пуш только по просьбе
- Не production-антибот / полный редизайн hh
