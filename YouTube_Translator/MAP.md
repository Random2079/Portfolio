# MAP — YouTube_Translator

Канон статуса / очереди / плана. Техника — `docs/TZ.md` + `docs/parts/`.
Дизайн UI (тема / motion) — `~/.cursor/skills/ui-design/profiles.md` + блок ниже.

| | |
|---|---|
| **Где мы** | IDEA-025 **A0+A1+A2** ✅. Хоткеи ок. **Дизайн SR закрыт.** |
| **Фокус** | 021 F1 / SMTC / или стоп по Фонu — по запросу |
| **Код scope** | `overlay_player.py` (025); shell UI — `Subtitle_App.py` / `ui_motion.py` |

---

## Дизайн SR — закрыто (2026-09-28)

Не открывать заново без явной просьбы («бесит глаз» / новый превью-раунд).

| | Канон |
|---|---|
| Жанр | **Tool**, не лендинг |
| Тема | **Theme A Slate** (`configure_qt_theme`) |
| Переходы окон | **fade+center** (`fade_center_transition`) — не morph size+pos |
| Фон | fade-in при открытии; первый раз — центр |
| Превью | `docs/design-previews/` · выбор motion: `window-transition-types.html` → **3** |
| Профиль | `~/.cursor/skills/ui-design/profiles.md` |

Коммит motion: `664d44c`.

---

## Очередь

| # | Что | Статус |
|---|-----|--------|
| 1 | Хоткеи: клиппинг текста + Mouse4/5 | ✅ |
| 2 | **025 A0** prefs + галка | ✅ |
| 3 | **025 A1** idle → сквозь + % | ✅ |
| 4 | Смоук A0/A1 | ✅ (юзер: работает стабильно) |
| 5 | 025 A2 сброс / hold opacity | ✅ |
| 6 | 021 F1 delete/rename | ⬜ |
| — | Дизайн тема + fade+center | ✅ |
| — | SMTC | ⏸ |

---

## Смоук A0/A1/A2

✅ A0/A1 2026-09-28: полное окно + play → idle → сквозь + %; стабильно.
⬜ A2: next track в авто-стекле — без мигания 100% / без записи auto-% в prefs; Esc → ручной %.

Опц.: угол экрана → Плеер/Назад (fade+center); Sign in WebView → обратно на ролик.

---

## Запреты

- Плотность `<100%` только со сквозь.
- Пуш только по просьбе.
- Не возвращать morph size+pos на shell; не /embed/ top-level (Error 153).
