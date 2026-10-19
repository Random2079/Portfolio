# HH_AutoApply (IDEA-026)

Полуавтомат откликов: **hh.ru** + **Kwork** (DeepSeek пишет заявку, LIVE каждый час).
HH лимит **100/день**, Kwork **15/день**. Стоп на капче. UI-отчёт + лента ссылок.

📍 Статус / очередь — [`MAP.md`](MAP.md).

## Запуск

**Как приложение (рекомендуется):** двойной клик `launch.vbs`  
(тот же приём, что YouTube_Translator — не exe, код правишь без пересборки).

```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m hh_auto login          # hh → data/storage_state.json
python -m hh_auto kwork-login    # Kwork → data/kwork_storage_state.json
python -m hh_auto search
python -m hh_auto apply --dry-run --limit 5
python -m hh_auto kwork-tick --dry-run --limit 1
python -m hh_auto kwork-tick --limit 1
python -m hh_auto kwork-feed
python -m hh_auto stats
python -m hh_auto raise-resume
python -m hh_auto ui             # HH + Kwork цикл
python -m hh_auto tg-scan
python -m hh_auto tg-scan --resolve-hh   # youngjunior.ru → hh + ranked_tg_*.json
python -m hh_auto apply --ranked data/ranked_tg_YYYY.json --dry-run
```

Ключ DeepSeek: `DEEPSEEK_API_KEY` в `DS_Projects/.env`.

## Пакет

| Модуль | Роль |
|---|---|
| `search` | выдача hh (web Playwright; API probe) |
| `tg_scan` | публичные `t.me/s/*` → filter |
| `yj_resolve` | `youngjunior.ru` → `hh.ru/vacancy` (кеш) |
| `kwork_search` / `kwork_ai` / `kwork_usage` / `kwork_apply` / `kwork_loop` | Kwork + DeepSeek + токены + LIVE |
| `score` / `cover` | ранг + сопроводительное (hh) |
| `limits` | дневной лимит |
| `apply` | login + отклик hh |
| `stats` | отчёт сегодня/лимит/статусы |
| `resume` | поднять резюме (идемпотентно) |
| `ui` | CustomTkinter: HH + Kwork цикл/лента |

🔒 Не коммитить: `data/storage_state.json`, `data/kwork_storage_state.json`, `.env`.
