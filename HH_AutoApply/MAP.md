# MAP — HH_AutoApply (IDEA-026)

👀 Скан: **📍 → 🎯 → 🟡 → 🚫**. ⏭️ ✅ / 📖 / 🗄️.

| | |
|---|---|
| 📍 **Где мы** | **D3** UI из `config.ui` ✅ |
| 🎯 **Фокус** | **D4** headless фон (не дёргать глаз) |
| 📁 **Код** | `hh_auto/ui.py` · `config*.json` · дальше `apply.py` / playwright |

---

## Канон данных

| Источник | Роль |
|---|---|
| `data/apply_state.json` | **день**: лимит 40 |
| `data/apply_log.jsonl` | лента статусов |
| `config.json` → `cover_template` | сопроводительное |
| `config.json` → `ui` | тема / шрифт / размер окна |
| `data/storage_state.json` | 🔒 не в git |

---

## Очередь

| # | Что | Статус |
|---|-----|--------|
| A–D2 | ядро + UI + ярлык + cover | ✅ |
| **D3** | **кастом UI из config** (`appearance_mode`, theme, font, geometry) | ✅ |
| **D4** | headless фон | ⬜ дальше |
| — | обход капчи | 🚫 |

📖 **Почему слой быстрый:** HH — тонкий tool (~сотни строк), не YT/TTS на десятки kLOC. Скорость ≠ «халтура», просто меньше графа связей.

📖 **`config.ui` (D3):**  
`appearance_mode`: dark|light|system · `color_theme`: blue|green|dark-blue · `font_family` / `font_size` (10–22) · `geometry` · `window_title`. Мусорные значения → дефолты.

---

## Смоук D3

```text
# в config.json → ui.font_size: 16, color_theme: "green"
wscript //nologo launch.vbs
# шрифт/тема подхватились → ок
```

---

## 🚫 Запреты

- Капчу не обходить · секреты не в git · пуш по просьбе
- D4 отдельно, не клеить с D3
