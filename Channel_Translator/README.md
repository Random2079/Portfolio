# Channel Translator

Массовый обход видео канала YouTube (список URL через yt-dlp) и пакетная обработка.

Завязан на папку `YouTube_Translator` (импорт хелперов оттуда).

## Запуск

```powershell
# Сначала рабочие зависимости YouTube_Translator (yt-dlp в PATH)
python Channel_Translator/channel_ripper.py
```

Скрипт спросит/примет URL канала (смотри код в начале `main`).

## Зависимости

- **yt-dlp** в PATH  
- Рядом должна лежать папка `YouTube_Translator` (относительные пути в коде)
