# 🔧 AI sidebar UX — слой D (карточка №2)

| | |
|---|---|
| **Код** | [`../../Subtitle_App.py`](../../Subtitle_App.py) — `_build_player_view`, `_apply_ai_analysis`, `on_ai_analyze`, `_set_ai_busy`, `_apply_player_folder_state` |
| **Слой** | D · карточка №2 |
| **Статус** | ✅ |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

---

## 🎯 Зачем

Сайдбар плеера разделяет **разбор ИИ** и **таймкоды**, показывает прогресс запроса и поднимает сохранённый разбор без повторного API.

## Сделано (код)

| Требование | Реализация |
|------------|------------|
| Три вкладки | `QTabWidget`: **Разбор** / **ИИ-моменты** / **Все** |
| Busy UX | `_set_ai_busy`, текст «ИИ…», `BusyPulse`, тик `_ai_busy_timer` |
| Restore | `load_saved_analysis` в `_apply_player_folder_state` |
| Режимы | кнопки **Инвест** / **Обычный**, `_ai_mode` |
| Память | `self._last_ai_analysis` |

Старые боли (одна колонка, «↩ все таймкоды без возврата», пустой сайдбар после reopen) — закрыты.

## Связь с карточкой №1

UX сайдбара готов; **какой folder** анализируется — зона [07](07-player-ai-current-video.md).

## 🔍 Проверка

```powershell
cd C:\Users\Home\OneDrive\Desktop\DS_Projects\YouTube_Translator
python Subtitle_App.py
```

1. ✨ ИИ → статус + пульс до ответа.  
2. Табы без повторного DeepSeek.  
3. Закрыть/открыть плеер — HTML из `ai_analysis.json`.

## ⚠️ Ограничения

- Не ломать `_unload_player` / whitelist WebView.  
- Не расширять до «браузер для всех сайтов».
