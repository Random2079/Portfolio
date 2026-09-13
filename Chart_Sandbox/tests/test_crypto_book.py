from app.crypto_book import fetch_futures_orderbook


def test_fetch_btcusdt_orderbook_live():
    book, err = fetch_futures_orderbook("BTCUSDT", limit=20)
    assert err == "", err
    assert book["symbol"] == "BTCUSDT"
    assert book["venue"] == "binance_usdm"
    assert len(book["bids"]) > 0
    assert len(book["asks"]) > 0
    assert book["bids"][0]["price"] < book["asks"][0]["price"]
    assert book["bids"][0]["cum"] >= book["bids"][0]["qty"]
