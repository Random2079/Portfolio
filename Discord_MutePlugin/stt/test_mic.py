"""Quick mic test without Discord — 3 sec record → transcript in log."""
from __future__ import annotations

import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:39281"


def post(path: str) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    try:
        h = get("/health")
    except Exception as e:
        print("Daemon not running. Start launch\\Start-VoiceStt.ps1")
        print(e)
        return 1
    print("Engine:", h.get("engine"), "mic:", h.get("device"), "gain:", h.get("gain"))
    print("Log:", h.get("log"))
    print("Говори 3 сек…")
    post("/listen/start")
    time.sleep(3)
    j = post("/listen/stop")
    print("transcript:", repr(j.get("transcript")))
    print("partial:", repr(j.get("partial")))
    print("peak_rms:", j.get("peak_rms"))
    if (j.get("peak_rms") or 0) < 300:
        print("WARN: тихо — проверь микрофон в stt_config.json input_device")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
