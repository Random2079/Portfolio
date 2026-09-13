"""Dump BCS portfolio shape (types/keys only, no full dump)."""
from __future__ import annotations

from pathlib import Path

import requests

env = Path(__file__).resolve().parent / ".env"
tok = ""
for line in env.read_text(encoding="utf-8").splitlines():
    if line.startswith("BCS_TRADE_REFRESH_TOKEN="):
        tok = line.split("=", 1)[1].strip().strip("\"'")
        break

s = requests.Session()
r = s.post(
    "https://be.broker.ru/trade-api-keycloak/realms/tradeapi/protocol/openid-connect/token",
    data={
        "grant_type": "refresh_token",
        "refresh_token": tok,
        "client_id": "trade-api-read",
    },
    timeout=30,
)
access = r.json()["access_token"]
h = {"Authorization": f"Bearer {access}", "Accept": "application/json"}
raw = s.get(
    "https://be.broker.ru/trade-api-bff-portfolio/api/v1/portfolio",
    headers=h,
    timeout=30,
).json()

print("root", type(raw).__name__, "len", len(raw) if isinstance(raw, list) else "n/a")
if isinstance(raw, list):
    for i, item in enumerate(raw[:30]):
        if isinstance(item, dict):
            t = item.get("type") or item.get("Type") or "?"
            keys = sorted(item.keys())[:12]
            print(f"[{i}] type={t!r} keys={keys}")
        else:
            print(f"[{i}] {type(item).__name__}")
    print("total items", len(raw))
elif isinstance(raw, dict):
    print("keys", sorted(raw.keys()))
