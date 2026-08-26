# 🃏 ИИ по текущему ролику — карточка №1 (слой D1+)

| | |
|---|---|
| **Код** | [`../../Subtitle_App.py`](../../Subtitle_App.py) — `on_ai_analyze`, `_start_ai_analyze_folder`, `on_analyze_current_video`, `_get_current_youtube_url`, `_apply_player_folder_state` · [`../../ai_analyze.py`](../../ai_analyze.py) |
| **Слой** | D1+ · **карточка №1** |
| **Статус** | ✅ |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

---

## 🎯 Зачем

Пользователь смотрит ролик во встроенном плеере и жмёт **✨ ИИ** там же — получает обзор **этого** ролика (как сайдбар на скрине: Разбор / ИИ-моменты / Все, вердикт).

Цитата (чат): «На кар №1 … ролик который текущий … нажать кнопку ии … обзор по этому ролику».

## Реализация

```
✨ ai_btn → on_ai_analyze
            _get_current_youtube_url (location.href WebView)
            → video_id
            → find_output_folder(id) + файлы субов?
                 да → sync folder (_apply_player_folder_state если id сменился)
                      → _start_ai_analyze_folder → analyze_subtitles
                 нет → _pending_ai_after_subs=True
                      → тот же worker player_subs, что у 📥
                      → после _done: _start_ai_analyze_folder

📥 analyze_btn → on_analyze_current_video (без ИИ; сбрасывает pending)
```

## Acceptance (карточка №1)

- [x] ✨ на ролике A с субами → разбор A в «Разбор».  
- [x] Смена на B в WebView → ✨ → разбор B + артефакты в папке B.  
- [x] B без `dist/` → скачивание субов, затем ИИ; **не** анализ A.  
- [x] Инвест/Обычный, табы, cancel, busy pulse сохранены.  
- [x] `ai_analysis.json` в папке разобранного id.

## 🔍 Проверка

```powershell
cd C:\Users\Home\OneDrive\Desktop\DS_Projects\YouTube_Translator
python Subtitle_App.py
```

Сценарии — см. раздел «Проверка» в [TZ](../TZ.md) (карточка №1).

## ⚠️ Ограничения

- Не авто-ИИ на каждый `urlChanged`.  
- Не ломать 📥 как «только субы».  
- Не трогать IDEA-021/022.
