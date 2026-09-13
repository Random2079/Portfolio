# Part 04 — Markers overlay

## Код / данные

- `data/markers.json` — заглушка сделок/точек по тикеру
- `GET /api/markers/{ticker}` в `app/main.py`
- UI: `series.setMarkers(...)` после загрузки свечей

## Формат маркера (LWC)

```json
{ "time": "2025-06-02", "position": "belowBar", "color": "#26a69a", "shape": "arrowUp", "text": "buy" }
```

## Проверка

SBER → видны buy/sell из JSON. `pytest` на API markers.
