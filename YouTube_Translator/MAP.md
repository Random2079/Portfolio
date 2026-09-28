# MAP — YouTube_Translator

Канон статуса / очереди / плана. Техника — `docs/TZ.md` + `docs/parts/`.
Дизайн UI (тема / motion) — `~/.cursor/skills/ui-design/profiles.md` + блок ниже.

| | |
|---|---|
| **Где мы** | IDEA-025 **A0+A1** в коде. Хоткеи: паддинг + Mouse4/5. **Дизайн SR закрыт.** |
| **Фокус** | Смоук авто-плотности; A2 по запросу |
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
| 4 | 025 A2 сброс / hold opacity | ⬜ (частично: idle bump на mouse) |
| 5 | 021 F1 delete/rename | ⬜ |
| — | Дизайн тема + fade+center | ✅ |
| — | SMTC | ⏸ |

---

## Смоук A0/A1

1. Полный рестарт Фона.
2. Настр. → поля хоткеев читаются целиком; клик → Ctrl+Shift+1; клик → Mouse4.
3. Авто-плотность вкл, 45%, 4с → OK → снова Настр. → те же значения.
4. Полное окно + play → 4с без мыши → сквозь + ~45%. Esc/Ctrl+O → управление.

Опц. после дизайна: угол экрана → Плеер/Назад (fade+center); Sign in WebView → обратно на ролик.

---

## Запреты

- Плотность `<100%` только со сквозь.
- Пуш только по просьбе.
- Не возвращать morph size+pos на shell; не /embed/ top-level (Error 153).
