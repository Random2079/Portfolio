# MAP — HH_AutoApply (IDEA-026)

👀 Скан: **📍 → 🎯 → 🟡 → 🚫**. ⏭️ ✅ / 📖 / 🗄️.

| | |
|---|---|
| 📍 **Где мы** | слой **UI+stats+resume bump** ✅ · ядро A/B восстановлено из pyc |
| 🎯 **Фокус** | смоук UI / `raise-resume` · не раздувать антибот |
| 📁 **Код** | `hh_auto/stats.py` · `ui.py` · `resume.py` · `apply.py` · `limits.py` |

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
| **C** | **UI отчётность + raise resume** | ✅ 🟡 смоук |
| — | авто-цикл по расписанию | ⬜ не сейчас |
| — | обход капчи | 🚫 |

---

## Смоук

```text
cd HH_AutoApply
pip install -r requirements.txt
python -m playwright install chromium
python -m unittest tests.test_core -v
python -m hh_auto stats
python -m hh_auto ui
python -m hh_auto raise-resume
```

Ожидание `raise-resume`: `raised` | `already_raised_skip` | `captcha` | `error`.
Повтор без `--force` → skip по cooldown (не спам).

---

## 🚫 Запреты

- Капчу не обходить — стоп + видно в UI/логе
- `storage_state.json` / токены / живой `config.json` с секретами — не коммитить
- Пуш только по просьбе
- Не production-антибот / полный редизайн hh
