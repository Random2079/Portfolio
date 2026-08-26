# 🔧 Launch & зависимости — слой A

| | |
|---|---|
| **Код** | [`../../launch.vbs`](../../launch.vbs) · [`../../launch/run.vbs`](../../launch/run.vbs) · [`../../launch/README.md`](../../launch/README.md) · [`../../requirements.txt`](../../requirements.txt) |
| **Слой** | A |
| **Статус** | ✅ (запуск) · 🟡 `requirements.txt` может отставать от PySide6 |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

---

## 🎯 Зачем

Частые правки → **Python + VBS**, не обязательный PyInstaller на каждый чих.

## Факт стека

| Было в старом README | Сейчас в бою |
|----------------------|--------------|
| CustomTkinter | **PySide6** + QtWebEngine |
| — | `ui_motion.py`, `ai_analyze.py` |

`requirements.txt` на момент ТЗ всё ещё может указывать `customtkinter` — при «делаем» синхронизировать с реальным импортом (`PySide6`, `yt-dlp`).

## Запуск

```powershell
cd C:\Users\Home\OneDrive\Desktop\DS_Projects\YouTube_Translator
pip install -r requirements.txt
# при необходимости: pip install PySide6
py -3.12 -m yt_dlp --version
python Subtitle_App.py
# или: wscript launch.vbs
```

yt-dlp предпочтительно через `python -m yt_dlp` (обход WinError 5 / Defender на exe в Scripts).

## ⚠️ Ограничения

- Exe — только по явной просьбе.  
- Не коммитить живые секреты / `.env`.
