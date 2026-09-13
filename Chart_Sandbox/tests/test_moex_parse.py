from app.moex import rows_to_candles


def test_rows_to_candles_ok():
    rows = [
        {
            "begin": "2024-01-15 00:00:00",
            "open": 100,
            "high": 110,
            "low": 95,
            "close": 105,
            "volume": 1000,
        }
    ]
    out = rows_to_candles(rows)
    assert len(out) == 1
    assert out[0]["time"] == "2024-01-15"
    assert out[0]["open"] == 100.0
    assert out[0]["high"] == 110.0
    assert out[0]["low"] == 95.0
    assert out[0]["close"] == 105.0
    assert out[0]["volume"] == 1000.0


def test_rows_skip_incomplete():
    rows = [
        {"begin": "", "open": 1, "high": 2, "low": 0.5, "close": 1.5},
        {"begin": "2024-02-01", "open": None, "high": 2, "low": 1, "close": 1.5},
        {"begin": "2024-02-02 12:00:00", "open": 1, "high": 2, "low": 1, "close": 1.5},
    ]
    out = rows_to_candles(rows)
    assert len(out) == 1
    assert out[0]["time"] == "2024-02-02"
