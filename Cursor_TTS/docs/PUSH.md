# Публикация на GitHub

Push падает с `Repository not found`, пока **пустой репозиторий не создан** на GitHub.

## 1. Создай репо (30 сек)

https://github.com/new

| Поле | Значение |
|------|----------|
| Repository name | `Cursor-TTS` |
| Public | да |
| README / .gitignore / license | **не** добавлять (у нас уже есть) |

Create repository.

## 2. Push

```powershell
cd C:\Users\Home\OneDrive\Desktop\DS_Projects\Cursor_TTS
git push -u origin main
```

Remote уже настроен: `https://github.com/Random2079/Cursor-TTS.git`

## Если auth через gh

Установлен GitHub CLI. Однократный логин:

```powershell
& "C:\Program Files\GitHub CLI\gh.exe" auth login -p https -w
```

Создание репо из CLI (альтернатива шагу 1):

```powershell
cd C:\Users\Home\OneDrive\Desktop\DS_Projects\Cursor_TTS
& "C:\Program Files\GitHub CLI\gh.exe" repo create Cursor-TTS --public --source=. --remote=origin --push
```

## После push

README с демо: https://github.com/Random2079/Cursor-TTS
