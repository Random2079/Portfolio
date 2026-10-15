# MAP — HH_AutoApply (IDEA-026)

👀 Скан: **📍 → 🎯 → 🟡 → 🚫**. ⏭️ ✅ / 📖 / 🗄️.

| | |
|---|---|
| 📍 **Где мы** | **D4** headless фон ✅ |
| 🎯 **Фокус** | смоук dry-run / raise без окна Chromium |
| 📁 **Код** | `playwright_headless` · `ui` switch · `config.playwright.headless` |

---

## Канон данных

| Источник | Роль |
|---|---|
| `data/apply_state.json` | день / лимит 40 |
| `data/apply_log.jsonl` | лента |
| `config.cover_template` | сопроводительное |
| `config.ui` | тема / шрифт |
| `config.playwright.headless` | **true** = браузер без окна (apply/search/resume) |
| `data/storage_state.json` | 🔒 не в git |

---

## Очередь

| # | Что | Статус |
|---|-----|--------|
| A–D3 | ядро + UI + ярлык + cover + ui-config | ✅ |
| **D4** | **headless фон** (не дёргать глаз) | ✅ 🟡 смоук |
| — | обход капчи | 🚫 |

📖 **D4:** apply / resume / search → `headless: true` по умолчанию. В UI переключатель «фон без окна» пишет в `config.json`.  
**login** (`python -m hh_auto login`) всегда **с окном** — иначе руками не войти.

---

## Смоук D4

```text
# config: playwright.headless = true (или галка в UI)
wscript //nologo launch.vbs
# Dry-run×5 / Поднять резюме → окно Chromium НЕ должно вылезать
# только tool-UI; в статусе/консоли: «фон(headless)»
# login по-прежнему: python -m hh_auto login → окно видно
```

---

## 🚫 Запреты

- Капчу не обходить · секреты не в git · пуш по просьбе
