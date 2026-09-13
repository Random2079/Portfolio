"""Fetch offline logos for portfolio equities from T-Invest CDN (ISIN)."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "portfolio_news" / "static" / "logos"
OUT.mkdir(parents=True, exist_ok=True)

hdr = {"User-Agent": "Mozilla/5.0", "Accept": "image/*"}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=hdr)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def main() -> None:
    holdings = json.load(
        urllib.request.urlopen("http://127.0.0.1:8765/api/holdings?force=1", timeout=60)
    )
    tickers = json.load(
        urllib.request.urlopen("http://127.0.0.1:8765/api/tickers", timeout=15)
    )
    by_isin = {
        str(t["id"]).upper(): str(t.get("isin") or "").upper()
        for t in tickers
        if t.get("id")
    }

    want: dict[str, str] = {}
    for h in holdings.get("holdings") or []:
        t = str(h.get("ticker") or "").upper()
        cc = str(h.get("class_code") or "").upper()
        if not t or t == "RUB" or cc == "TQCB":
            continue
        isin = str(h.get("isin") or by_isin.get(t) or "").upper()
        if not isin and t.startswith("RU000"):
            isin = t
        if isin:
            want[t] = isin

    ok, fail = [], []
    for t, isin in sorted(want.items()):
        path = OUT / f"{t}.png"
        url = f"https://invest-brands.cdn-tinkoff.ru/{isin}x160.png"
        try:
            data = fetch(url)
        except Exception as exc:  # noqa: BLE001
            fail.append((t, isin, getattr(exc, "code", type(exc).__name__)))
            continue
        if not data.startswith(b"\x89PNG") or len(data) < 200:
            fail.append((t, isin, f"bad:{len(data)}"))
            continue
        path.write_bytes(data)
        ok.append((t, len(data)))
        print("OK", t, len(data))

    print("--- fail ---")
    for row in fail:
        print("FAIL", *row)
    print(f"ok={len(ok)} fail={len(fail)} total={len(want)}")


if __name__ == "__main__":
    main()
