# Промпт для нового чата — IDEA-003 Portfolio_News

> Workspace: `Portfolio_News`  
> Путь: `C:\Users\Home\OneDrive\Desktop\DS_Projects\Portfolio_News`

```
Ты в Portfolio_News (IDEA-003, новостник портфеля).

Сначала прочитай:
- docs/TZ.md
- docs/PROMPT_FOR_AGENT.md
- docs/parts/INDEX.md
- нужный docs/parts/NN-….md под задачу

Смысл: тикеры → RU-новости → SQLite дедуп → Windows toast + UI localhost.
Плюс сырой MOEX и опционально БКС read-only. Не инвест-консультант.

Статус: A–D ✅. Фокус — трек K «свой БКС» (K0 токен+список → K1 история → K2 кэш → K3 графики → K4 разбор).
E–J (live-лента, ИИ, watch, телефон…) — низкий приоритет, пока не скажут иначе.

Не делаем: trade-api-write; советы купи/продай; MAX/VK/Telegram вслепую; VPS;
секреты в git/чат; не переписывать A–D с нуля.

Git: не коммить и не пушь без просьбы. Не коммитить .env, data/, токены БКС.

Код — маленькими шагами K0, K1… после «делаем K0» / «погнали».
```

## Куда смотреть по задаче

| Задача | Part |
|--------|------|
| Свой БКС: история/графики | **10** + 07 |
| Позиции БКС сейчас | 07 |
| Poll / toast / scope | 04 |
| UI / API | 05 |
| MOEX | 06 |
| ИИ-чистка | 08 |
| Автозапуск / телефон | 09 |
