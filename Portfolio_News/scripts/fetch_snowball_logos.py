"""Download asset logos from Snowball Yandex CDN (same URLs as in browser F12)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "portfolio_news" / "static" / "logos"
OUT.mkdir(parents=True, exist_ok=True)

PATTERNS = [
    "https://storage.yandexcloud.net/snowball-data/asset-logos/{t}-MCX-RUB-custom.png",
    "https://storage.yandexcloud.net/snowball-data/asset-logos/{t}-MCX-RUB.png",
    "https://storage.yandexcloud.net/snowball-data/asset-logos/{t}-MCX.png",
    "https://storage.yandexcloud.net/snowball-data/asset-logos/{t}.png",
]

# Snowball sometimes uses alternate ids (FIVE = X5)
ALIASES: dict[str, list[str]] = {
    "X5": ["X5", "FIVE"],
}

HDR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Referer": "https://snowball-income.com/",
}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def main() -> None:
    # smoke the exact URL from user's F12
    probe = "https://storage.yandexcloud.net/snowball-data/asset-logos/GOLD-MCX-RUB-custom.png"
    try:
        raw = fetch(probe)
        print("PROBE GOLD", len(raw), raw[:8])
    except Exception as exc:  # noqa: BLE001
        print("PROBE GOLD FAIL", exc)

    holdings = json.load(
        urllib.request.urlopen("http://127.0.0.1:8765/api/holdings", timeout=60)
    )
    ids = sorted(
        {
            str(h.get("ticker") or "").upper()
            for h in holdings.get("holdings") or []
            if str(h.get("ticker") or "").upper() not in ("", "RUB")
            and str(h.get("class_code") or "").upper() != "TQCB"
        }
    )

    ok: list[str] = []
    fail: list[str] = []
    for t in ids:
        got = False
        last_err = ""
        names = ALIASES.get(t, [t])
        for name in names:
            for pat in PATTERNS:
                url = pat.format(t=name)
                try:
                    data = fetch(url)
                except urllib.error.HTTPError as exc:
                    last_err = f"HTTP {exc.code}"
                    continue
                except Exception as exc:  # noqa: BLE001
                    last_err = type(exc).__name__
                    continue
                if data[:8].startswith(b"\x89PNG") and len(data) > 300:
                    (OUT / f"{t}.png").write_bytes(data)
                    svg = OUT / f"{t}.svg"
                    if svg.exists():
                        svg.unlink()
                    print("OK", t, len(data), url.rsplit("/", 1)[-1])
                    ok.append(t)
                    got = True
                    break
                last_err = f"bad body {len(data)}"
            if got:
                break
        if not got:
            print("FAIL", t, last_err)
            fail.append(t)

    print(f"ok={len(ok)} fail={len(fail)}")
    if fail:
        print("missing:", ", ".join(fail))


if __name__ == "__main__":
    main()
