"""
Клиент озвучки: шлёт текст в tts_daemon (тёплый процесс).
Запуск: python speak_edge.py путь.txt
         python speak_edge.py --stop
Если демон не запущен — поднимает его сам.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DAEMON = ROOT / "tts_daemon.py"
HOST = "127.0.0.1"
PORT = 47391


def send_command(payload: dict, timeout: float = 2.0) -> dict:
    raw = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    with socket.create_connection((HOST, PORT), timeout=timeout) as sock:
        sock.sendall(raw)
        data = b""
        while not data.endswith(b"\n"):
            piece = sock.recv(4096)
            if not piece:
                break
            data += piece
    if not data:
        return {"ok": False, "error": "empty response"}
    return json.loads(data.decode("utf-8").strip())


def daemon_alive() -> bool:
    try:
        reply = send_command({"cmd": "ping"}, timeout=0.4)
        return bool(reply.get("ok"))
    except OSError:
        return False


def ensure_daemon() -> None:
    if daemon_alive():
        return

    flags = 0x08000000 if sys.platform == "win32" else 0
    env = os.environ.copy()
    env["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    # pythonw — без консоли; если нет — обычный python
    exe = sys.executable
    if sys.platform == "win32":
        candidate = Path(exe).with_name("pythonw.exe")
        if candidate.is_file():
            exe = str(candidate)

    subprocess.Popen(
        [exe, str(DAEMON)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        env=env,
    )

    for _ in range(40):
        time.sleep(0.1)
        if daemon_alive():
            return
    raise RuntimeError("TTS daemon did not start")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("text_file", nargs="?", help="UTF-8 file with text to speak")
    parser.add_argument("--stop", action="store_true", help="Stop current speech")
    parser.add_argument("--voice", help="Ignored here; set in tts_config.json / panel")
    parser.add_argument("--volume", type=int, help="Ignored here; set in tts_config.json / panel")
    args = parser.parse_args()

    ensure_daemon()

    if args.stop:
        # #region agent log
        try:
            _dbg = Path(__file__).resolve().parent.parent / "debug-45ab72.log"
            with _dbg.open("a", encoding="utf-8") as _f:
                _f.write(
                    json.dumps(
                        {
                            "sessionId": "45ab72",
                            "hypothesisId": "C",
                            "location": "speak_edge.py:stop",
                            "message": "client --stop before send",
                            "data": {},
                            "timestamp": int(time.time() * 1000),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except OSError:
            pass
        # #endregion
        try:
            reply = send_command({"cmd": "stop"})
        except OSError as exc:
            reply = {"ok": False, "error": str(exc)}
        # #region agent log
        try:
            with _dbg.open("a", encoding="utf-8") as _f:
                _f.write(
                    json.dumps(
                        {
                            "sessionId": "45ab72",
                            "hypothesisId": "C",
                            "location": "speak_edge.py:stop",
                            "message": "client --stop reply",
                            "data": {"reply": reply},
                            "timestamp": int(time.time() * 1000),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except OSError:
            pass
        # #endregion
        return 0 if reply.get("ok") else 1

    if not args.text_file:
        parser.print_help()
        return 1

    path = Path(args.text_file)
    if not path.is_file():
        return 1

    text = path.read_text(encoding="utf-8").strip()
    path.unlink(missing_ok=True)
    if len(text) < 2:
        return 1

    # Стоп только если в конфиге включён обрыв; иначе очередь в демоне.
    interrupt = False
    config_path = ROOT / "tts_config.json"
    if config_path.is_file():
        try:
            interrupt = bool(
                json.loads(config_path.read_text(encoding="utf-8")).get(
                    "interrupt_on_new", False
                )
            )
        except (json.JSONDecodeError, OSError, TypeError):
            interrupt = False

    if interrupt:
        send_command({"cmd": "stop"})
    send_command({"cmd": "speak", "text": text})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
