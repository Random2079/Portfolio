# Epub2txt

Конвертер **EPUB → TXT**: вытаскивает текст глав, чистит HTML-теги, пишет обычный файл.

## Запуск

```powershell
pip install ebooklib
python Epub2txt/epub2txt.py
```

Скрипт спросит пути к `.epub` и выходному `.txt` (или смотри `if __name__` в файле).

## Зависимости

- `ebooklib`
