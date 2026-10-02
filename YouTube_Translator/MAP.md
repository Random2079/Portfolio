# MAP — YouTube_Translator

Канон статуса / очереди / плана. Техника — `docs/TZ.md` + `docs/parts/`.
Дизайн UI (тема / motion) — `~/.cursor/skills/ui-design/profiles.md` + блок ниже.

| | |
|---|---|
| **Где мы** | IDEA-025 A0–A3 ✅ · план B0 в part 18. **YT adblock** в плеере. **🎞↓ обои mp4+mp3** ✅ (part 20). |
| **Фокус** | Смоук 🎞↓ · или **025 B0** по запросу |
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
| 6 | 025 A3 плотность от яркости стола | ✅ (база; grab-при-CT убран) |
| 7 | **025 B0** комфорт: lerp + тик без вспышек | ⬜ **следующий** |
| 8 | 025 B1 кривая/prefs по тесту | ⬜ если B0 мало |
| 9 | 025 B2 dxcam/DXGI | ⬜ только если B0+B1 мало под игрой |
| 10 | 021 F1 delete/rename | ⬜ |
| — | **🎞↓ обои mp4+mp3 → YouTube_DL** | ✅ part 20 |
| — | YT плеер: блок рекламы (URL filter + skip JS) | ✅ |
| — | Дизайн тема + fade+center | ✅ |
| — | SMTC | ⏸ |

---

## Смоук / план авто-плотности

Канон цели и лестница B0→B3: [`docs/parts/18-overlay-auto-density.md`](docs/parts/18-overlay-auto-density.md).

✅ A0/A1: idle → сквозь.  
✅ A2/A3 база в коде; урок: `grabWindow` при сквозь = вспышка на чужом окне.  
⬜ **B0:** комфорт без нового capture — команда `делаем B0`.

Опц.: угол экрана → Плеер/Назад (fade+center); Sign in WebView → обратно на ролик.

---

## Запреты

- Плотность `<100%` только со сквозь.
- Пуш только по просьбе.
- Не возвращать morph size+pos на shell; не /embed/ top-level (Error 153).
