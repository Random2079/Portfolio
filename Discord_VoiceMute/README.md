# Discord VoiceMute — IDEA-005 (слой A)

Скрин сайдбара Discord → OCR → в консоль: **lobby / me / others**.

Твой ник в конфиге: `Ищу работу (Python Dev)`. Mute/клики — потом.

## Установка

```powershell
cd Discord_VoiceMute
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy config.example.json config.json
```

Первый запуск EasyOCR качает модели (нужен интернет, может занять время).

## Захват окна (просто, без усложнений)

Дефолт: `capture_mode: "game"` в `config.json`.

| Можно | Нельзя |
|-------|--------|
| Discord **открыт** на **этом** рабочем столе | Сворачивать в трей |
| Лежит **под** аниме/игрой/Cursor | Другой виртуальный стол (Task View) |
| PrintWindow без кражи фокуса | Ждать магии «невидимый Discord» |

Если окно-призрак / другой стол → `status: discord_unavailable` (фокус не трогаем).  
Для отладки дома: `"capture_mode": "normal"` или `python detect_lobby.py --once --mode normal` (можно restore/topmost).

## Запуск

```powershell
cd Discord_VoiceMute
.\.venv\Scripts\Activate.ps1
python detect_lobby.py --once
```

Лобби часто из заголовка (`🟣・22 | Lounge`). Ник — OCR (в т.ч. обрезанный).  
Дебаг: `debug_last_capture.png`, `voicemute.log`.


## Слой B (пока dry-run)

```powershell
python test_parse_command.py
python run_command.py замуть 3
```

По умолчанию `dry_run: true` — только лог координат. Живые клики: `--live` после калибровки `mute_slot1` / `mute_slot_dy`.

```text
lobby: 12
me: Ищу работу (Python Dev)
others: ['vladswaga', 'дима билан', 'Куратор']
```

## Ограничения

- OCR врёт на мелком шрифте / тёмной теме — подкрути ROI и масштаб Discord.
- Кого не видно в сайдбаре (скролл) — того нет в списке.
- Это ещё не mute, только глаза.
