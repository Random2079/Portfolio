import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
import app.cache as disk_cache


client = TestClient(app)


def test_markers_sber():
    r = client.get("/api/markers/SBER")
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == "SBER"
    assert isinstance(data["markers"], list)
    assert len(data["markers"]) >= 1
    assert "time" in data["markers"][0]


def test_candles_stale_from_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(disk_cache, "CACHE_DIR", tmp_path)
    payload = {
        "ticker": "SBER",
        "board": "TQBR",
        "days": 30,
        "candles": [
            {"time": "2024-01-10", "open": 1, "high": 2, "low": 0.5, "close": 1.5}
        ],
    }
    disk_cache.write_cache("SBER", 30, payload)

    def boom(ticker, *, days=365):
        return [], "", "timeout"

    monkeypatch.setattr("app.main.fetch_daily_candles", boom)

    r = client.get("/api/candles/SBER?days=30&force=1")
    assert r.status_code == 200
    data = r.json()
    assert data["stale"] is True
    assert len(data["candles"]) == 1
    assert data["candles"][0]["time"] == "2024-01-10"


def test_candles_cache_hit_without_moex(tmp_path, monkeypatch):
    monkeypatch.setattr(disk_cache, "CACHE_DIR", tmp_path)
    payload = {
        "ticker": "GAZP",
        "board": "TQBR",
        "days": 10,
        "candles": [
            {"time": "2024-03-01", "open": 1, "high": 1, "low": 1, "close": 1}
        ],
    }
    disk_cache.write_cache("GAZP", 10, payload)

    called = {"n": 0}

    def should_not(ticker, *, days=365):
        called["n"] += 1
        return [], "", "nope"

    monkeypatch.setattr("app.main.fetch_daily_candles", should_not)
    r = client.get("/api/candles/GAZP?days=10&force=0")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "cache"
    assert data["stale"] is False
    assert called["n"] == 0
    assert len(data["candles"]) == 1
