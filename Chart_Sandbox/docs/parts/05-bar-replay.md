# Part 05 — Bar Replay (перемотка)

Референс: [TradingView Bar Replay](https://www.tradingview.com/support/solutions/43000474024-how-do-i-turn-bar-replay-on/).

## Код

`static/index.html` (только UI; API не меняем)

## Поведение (MVP)

1. Кнопка **Replay** — вход в режим (выбор точки / панель управления).
2. Клик по свече на основном графике — playhead; бары **правее скрыты**.
3. Панель: шаг назад, Play/Pause, шаг вперёд, скорость (0.5x–4x), scrubber, дата, **Exit** (полный ряд = «Jump to real-time» у TV).
Референс: вертикальная линия playhead (синяя) на cutoff — как линия выбора старта / «где останавливается время» у TV Bar Replay.

## Не делаем

- Paper trading / ордера TV
- Смена replay-interval vs timeframe графика
- Сохранение сессии replay на диск

## Проверка

1. Load SBER.
2. Replay → клик по середине → Play.
3. Бары появляются по одному; RSI двигается согласованно.
4. Exit → снова все бары.
