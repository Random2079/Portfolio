# HH_AutoApply (IDEA-026)

Полуавтомат откликов на hh.ru: поиск → score → cover → Playwright apply.
Лимит **40/день**, стоп на капче. UI-отчёт + поднятие резюме.

📍 Статус / очередь — [`MAP.md`](MAP.md).

## Запуск

**Как приложение (рекомендуется):** двойной клик `launch.vbs`  
(тот же приём, что YouTube_Translator — не exe, код правишь без пересборки).

```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m hh_auto login          # один раз: логин руками → data/storage_state.json
python -m hh_auto search
python -m hh_auto apply --dry-run --limit 5
python -m hh_auto stats
python -m hh_auto raise-resume   # raised | already_raised_skip | captcha | error
python -m hh_auto ui             # то же окно, что launch.vbs
```

## Пакет

| Модуль | Роль |
|---|---|
| `search` | выдача hh (web Playwright; API probe) |
| `score` / `cover` | ранг + сопроводительное |
| `limits` | дневной лимит (`apply_state`) |
| `apply` | login + отклик |
| `stats` | отчёт сегодня/лимит/статусы |
| `resume` | поднять резюме (идемпотентно) |
| `ui` | CustomTkinter tool-окно |

🔒 Не коммитить: `data/storage_state.json`.
