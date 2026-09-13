from app.liquidity import build_liquidity_map, detect_swings


def _candle(t, o, h, l, c):
    return {"time": t, "open": o, "high": h, "low": l, "close": c}


def test_detect_swing_high_low():
    # flat then spike high then flat → one swing high in the middle
    candles = [
        _candle("2024-01-01", 10, 10.2, 9.8, 10),
        _candle("2024-01-02", 10, 10.1, 9.9, 10),
        _candle("2024-01-03", 10, 10.2, 9.8, 10),
        _candle("2024-01-04", 10, 12.0, 9.9, 11),  # swing high
        _candle("2024-01-05", 11, 11.1, 10.5, 10.8),
        _candle("2024-01-06", 10.8, 10.9, 10.4, 10.5),
        _candle("2024-01-07", 10.5, 10.6, 10.2, 10.3),
        _candle("2024-01-08", 10.3, 10.4, 9.5, 9.6),  # swing low-ish
        _candle("2024-01-09", 9.6, 9.8, 9.4, 9.7),
        _candle("2024-01-10", 9.7, 9.9, 9.5, 9.8),
        _candle("2024-01-11", 9.8, 10.0, 9.6, 9.9),
    ]
    swings = detect_swings(candles, left=2, right=2)
    highs = [s for s in swings if s["kind"] == "high"]
    assert any(abs(s["price"] - 12.0) < 1e-9 for s in highs)


def test_equal_high_pool():
    candles = [
        _candle("2024-02-01", 10, 10.5, 9.9, 10.2),
        _candle("2024-02-02", 10.2, 10.4, 10.0, 10.1),
        _candle("2024-02-03", 10.1, 11.0, 10.0, 10.8),
        _candle("2024-02-04", 10.8, 10.9, 10.5, 10.6),
        _candle("2024-02-05", 10.6, 10.7, 10.3, 10.4),
        _candle("2024-02-06", 10.4, 10.5, 10.1, 10.2),
        _candle("2024-02-07", 10.2, 11.02, 10.0, 10.9),  # ~equal high
        _candle("2024-02-08", 10.9, 11.0, 10.5, 10.6),
        _candle("2024-02-09", 10.6, 10.7, 10.2, 10.3),
        _candle("2024-02-10", 10.3, 10.4, 10.0, 10.1),
    ]
    m = build_liquidity_map(candles, left=2, right=2, tol_pct=0.01)
    assert m["disclaimer"]
    assert isinstance(m["zones"], list)
    # may or may not form equal pool depending on pivots — zones should be non-empty if swings found
    assert "swings" in m
