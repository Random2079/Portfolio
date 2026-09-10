"""Снять зависшие Subtitle_App / pythonw по этому проекту."""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.dirname(__file__))


def main() -> int:
    killed: list[str] = []
    try:
        import psutil
    except ImportError:
        psutil = None

    if psutil is not None:
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name not in ("python.exe", "pythonw.exe"):
                    continue
                cmd = " ".join(proc.info.get("cmdline") or [])
                low = cmd.replace("\\", "/").lower()
                if "subtitle_app.py" not in low and "youtube_translator" not in low:
                    continue
                print(f"kill {proc.pid}: {cmd[:140]}")
                proc.kill()
                killed.append(str(proc.pid))
            except (psutil.Error, OSError, ProcessLookupError):
                continue
    else:
        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | "
            "Where-Object { $_.CommandLine -match 'Subtitle_App\\.py' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; "
            "Write-Output $_.ProcessId }"
        )
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps],
                text=True,
                errors="replace",
                timeout=20,
            )
            killed = [ln.strip() for ln in out.splitlines() if ln.strip()]
            for pid in killed:
                print(f"kill {pid}")
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"fail: {exc}")
            return 1

    print(f"done, killed={killed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
