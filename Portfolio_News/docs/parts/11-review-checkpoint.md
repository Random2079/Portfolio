# 11 · Сверка / факты в разборе (чек-поинт UI)

| | |
|---|---|
| **Код** | `review_facts.py` · `fundamentals_smartlab.py` · `bonds_dohod.py` · `api.py` · `static/dashboard-demo.html` |
| **Слой** | **KS** |
| **Статус** | API+кэш ✅ · SmartLab/Dohod ✅ · growth←revenue YoY 2026-09-19 |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |
| **Правила владельца (вне репо)** | `Инвестиции/Investing/rules/чек-поинт*.md` — не копировать в git |

## Прогресс

| Шаг | Статус |
|-----|--------|
| План в TZ | ✅ |
| UI-макет | ✅ |
| API `/api/review` + SQLite `review_cache` | ✅ 2026-09-14 (BCS + MOEX + calendar) |
| SmartLab fundamental / Dohod облиг | ✅ 2026-09-14 (+ FCF/CAPEX field tables) |
| Карта источников / дырок | ✅ 2026-09-17 |

## На чём держатся источники (сейчас)

| Источник | Что даёт | Кэш | Типичный промах |
|----------|----------|-----|-----------------|
| **BCS** | qty, доля, имя позиции | holdings live | нет «кэша на добор» (это не брокер) |
| **MOEX ISS** | last, див.%, купон, НКД, matdate, YTM, listlevel | metrics на лету | таймаут → слоты missing, кэш review спасает |
| **calendar_own** | ближ. див/купон по своим | `calendar_cache` | пусто если нет будущих выплат в кэше |
| **SmartLab** `/q/shares_fundamental/` + `?field=fcf\|…\|revenue\|pending_*` | P/E P/B ROE долг/EBITDA див.% FCF CAPEX **выручка YoY** контракты | `smartlab_fundamentals_cache` (~12ч) | банки часто без FCF; HTML/блок; префы → alias (TATNP→TATN) |
| **Dohod** `getbondinfo` по ISIN | оферта, рейтинг, фикс/флоат, YTM | `dohod_bond_cache` | нет ISIN / пустой ответ → оферта/рейтинг missing |

Поток: `GET /api/review/{ticker}` → кэш review → иначе BCS+MOEX+calendar+SmartLab/Dohod → `build_review_payload` → слоты сектора.

## Что пустое и почему

| Слот / место | Почему пусто | Закрываем как |
|--------------|--------------|---------------|
| **Эскроу** (девелоп) | «Денег на эскроу» в SmartLab нет | **Контракты на продажу** млрд ₽ / тыс м² (`pending_apartment_sales*`) + долг/EBITDA — прокси пайплайна. PIKK может отсутствовать в таблице. |
| **Рост YoY** (IT) | было: только период `отчёт` | **Выручка г/г** с `?field=revenue` (`revenue_yoy`) + млрд ₽ + отчёт |
| **TER фонда** | ЦБ витрина ПИФ (xlsx) по ISIN | `УК x% · макс. y%` · кэш SQLite `fund_ter_universe_cache` (~7д); без ISIN — investfunds autocomplete |
| **Кэш на добор** | Твоя политика, не API | Подпись «вручную» |
| **Красные флаги** | Заглушки UI | Ручной клик; авто-скоринг запрещён |
| **FCF у банков** | SmartLab часто не считает | Ок для banks (P/B ROE) |
| **Ближ. див/купон** | Нет события ≥ today в calendar | Пересбор календаря |
| Вся сверка пустая | Таймаут / холодный кэш | Повтор / force; stale review cache |

## Как закрываем пустоту (очередь)

1. **Сделано:** SmartLab multiples+FCF/CAPEX; Dohod; growth←revenue YoY; эскроу←контракты; **TER фондов ← ЦБ ПИФ xlsx** (2026-09-19).
2. **Дальше по желанию:** без команды — флаги/F/KV.
3. **Не делаем:** выдуманный cash-на-эскроу; таргеты; авто-балл; платный API.

## Цель

Под карточкой позиции (K4) — блок **«Сверка / факты»**. Не совет купить/продать. K4/клик не ломать.

## Итог разбора

`тезис жив` · `ослаб` · `hold` · `PASS-кэш` · `WATCH` · `[НЕТ ДАННЫХ]` — ручной; авто-балл запрещён.

## Поля по kind

### Акция

| Сектор | Слоты | Чем заполняем |
|--------|-------|---------------|
| ресурсы | FCF · CAPEX · див.% · P/E | SmartLab (+ MOEX div) |
| банки | P/B · ROE · P/E · див.% | SmartLab |
| ритейл/телеком | FCF · NetDebt/EBITDA · див.% · P/E | SmartLab |
| IT | путь к FCF · рост (выручка YoY) · P/E · див.% | SmartLab `field=revenue` + отчёт |
| девелоп | эскроу/долг · NetDebt/EBITDA · див.% | контракты SmartLab + долг; не cash-эскроу |
| неизвестен | див.% · P/E · P/B | SmartLab / MOEX |

### Облигация

MOEX + Dohod + calendar.

### Фонд

| Фонд | Имя/тема; **TER** = УК% + макс. расходы из витрины ЦБ (кэш) |

## Запреты

- «Покупай / продавай» / балл-скоринг · React-рерайт · секреты / чек-поинт из `Инвестиции/` в git

## Проверка

```powershell
pytest tests/test_review_facts.py tests/test_ks_sources.py -q
```
