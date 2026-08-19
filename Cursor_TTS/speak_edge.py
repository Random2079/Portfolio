"""
Клиент озвучки: шлёт текст в tts_daemon (тёплый процесс).
Запуск: python speak_edge.py путь.txt
         python speak_edge.py --stop
         python speak_edge.py --pause / --resume / --pause-toggle
         python speak_edge.py --warmup
         python speak_edge.py --restart-daemon --warmup
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
        sock.settimeout(timeout)
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


def _daemon_busy(status: dict) -> bool:
    phase = str(status.get("phase", "idle")).strip().lower()
    return (
        phase in {"preparing", "synthesizing", "playing"}
        or bool(status.get("warming"))
        or int(status.get("queue", 0) or 0) > 0
    )


def stop_daemon(*, force: bool = False) -> None:
    """Убить процесс демона, чтобы следующий ensure подхватил новый код."""
    if not force:
        try:
            status = send_command({"cmd": "status"}, timeout=0.5)
        except (OSError, ValueError, json.JSONDecodeError):
            status = {}
        if status.get("ok") and _daemon_busy(status):
            phase = str(status.get("phase", "busy"))
            current = int(status.get("current", 0) or 0)
            total = int(status.get("total", 0) or 0)
            chunk = f" chunk={current}/{total}" if total else ""
            raise RuntimeError(
                f"TTS daemon is {phase}{chunk}; refusing to cut active speech"
            )

    pid_file = ROOT / "tts_daemon.pid"
    pid = ""
    if pid_file.is_file():
        try:
            pid = pid_file.read_text(encoding="ascii").strip()
        except OSError:
            pid = ""
    flags = 0x08000000 if sys.platform == "win32" else 0
    if pid.isdigit():
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", pid],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    for _ in range(25):
        if not daemon_alive():
            break
        time.sleep(0.1)
    pid_file.unlink(missing_ok=True)


def reboot_daemon() -> None:
    """Убить демон даже на warmup и поднять заново под текущий config."""
    stop_daemon(force=True)
    ensure_daemon()


def ensure_daemon(*, restart: bool = False) -> None:
    if restart:
        stop_daemon(force=True)
    elif daemon_alive():
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


def warmup_backend(timeout: float = 180.0, *, restart: bool = False) -> dict:
    """Поднять демон и прогреть Silero/Piper / убедиться что демон жив (edge)."""
    ensure_daemon(restart=restart)
    return send_command({"cmd": "warmup"}, timeout=timeout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("text_file", nargs="?", help="UTF-8 file with text to speak")
    parser.add_argument("--stop", action="store_true", help="Stop current speech and clear queue")
    parser.add_argument("--pause", action="store_true", help="Pause playback (keep queue)")
    parser.add_argument("--resume", action="store_true", help="Resume after pause")
    parser.add_argument(
        "--pause-toggle",
        action="store_true",
        help="Toggle pause/resume",
    )
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="Start daemon and preload local TTS model",
    )
    parser.add_argument(
        "--restart-daemon",
        action="store_true",
        help="Kill running daemon so the next start loads new code",
    )
    parser.add_argument("--voice", help="Ignored here; set in tts_config.json / panel")
    parser.add_argument("--volume", type=int, help="Ignored here; set in tts_config.json / panel")
    args = parser.parse_args()

    if args.warmup:
        try:
            reply = warmup_backend(restart=args.restart_daemon)
        except (OSError, RuntimeError) as exc:
            print(f"warmup failed: {exc}", file=sys.stderr)
            return 1
        return 0 if reply.get("ok") else 1

    if args.restart_daemon:
        stop_daemon()
        try:
            ensure_daemon()
        except RuntimeError as exc:
            print(f"restart failed: {exc}", file=sys.stderr)
            return 1
        return 0

    ensure_daemon()

    def _print_pause_state(reply: dict) -> int:
        """Явный статус в stdout для AHK/панели: PAUSED или PLAYING."""
        if not reply.get("ok"):
            print("ERROR", file=sys.stderr)
            return 1
        paused = bool(reply.get("paused"))
        print("PAUSED" if paused else "PLAYING")
        return 0

    if args.stop:
        warming = False
        try:
            reply = send_command({"cmd": "stop"})
            try:
                st = send_command({"cmd": "status"}, timeout=0.5)
                warming = bool(st.get("warming"))
            except OSError:
                warming = False
        except OSError as exc:
            reply = {"ok": False, "error": str(exc)}
            warming = True
        if warming:
            stop_daemon(force=True)
        if reply.get("ok") or warming:
            print("PLAYING")
            return 0
        return 1

    if args.pause:
        try:
            reply = send_command({"cmd": "pause"})
        except OSError as exc:
            reply = {"ok": False, "error": str(exc)}
        return _print_pause_state(reply)

    if args.resume:
        try:
            reply = send_command({"cmd": "resume"})
        except OSError as exc:
            reply = {"ok": False, "error": str(exc)}
        return _print_pause_state(reply)

    if args.pause_toggle:
        try:
            reply = send_command({"cmd": "pause_toggle"})
        except OSError as exc:
            reply = {"ok": False, "error": str(exc)}
        return _print_pause_state(reply)

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
