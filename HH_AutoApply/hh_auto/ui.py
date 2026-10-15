"""Tool-окно отчётности HH_AutoApply (CustomTkinter)."""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from typing import Any

from hh_auto import load_config
from hh_auto.stats import format_stats_text, load_report

# D2: метка живого кода — ярлык/pythonw всегда тянет этот файл с диска
_UI_FILE = Path(__file__).resolve()

_THEMES = frozenset({"blue", "green", "dark-blue"})
_MODES = frozenset({"dark", "light", "system"})


def _code_stamp() -> str:
    try:
        mtime = datetime.fromtimestamp(_UI_FILE.stat().st_mtime)
        return mtime.strftime("%Y-%m-%d %H:%M")
    except OSError:
        return "?"


def _ui_opts(cfg: dict[str, Any]) -> dict[str, Any]:
    raw = cfg.get("ui") or {}
    mode = str(raw.get("appearance_mode") or "dark").lower()
    theme = str(raw.get("color_theme") or "dark-blue").lower()
    if mode not in _MODES:
        mode = "dark"
    if theme not in _THEMES:
        theme = "dark-blue"
    geo = str(raw.get("geometry") or "720x560")
    font_family = str(raw.get("font_family") or "Consolas")
    try:
        font_size = int(raw.get("font_size") or 13)
    except (TypeError, ValueError):
        font_size = 13
    font_size = max(10, min(22, font_size))
    title = str(raw.get("window_title") or "HH AutoApply — отчёт")
    return {
        "appearance_mode": mode,
        "color_theme": theme,
        "geometry": geo,
        "font_family": font_family,
        "font_size": font_size,
        "window_title": title,
    }


def run_ui(config_path: Path | None = None) -> int:
    try:
        import customtkinter as ctk
    except ImportError:
        print("Нужен customtkinter: pip install customtkinter")
        return 1

    cfg = load_config(config_path)
    opts = _ui_opts(cfg)
    ctk.set_appearance_mode(opts["appearance_mode"])
    ctk.set_default_color_theme(opts["color_theme"])

    app = ctk.CTk()
    app.title(opts["window_title"])
    app.geometry(opts["geometry"])
    app.minsize(560, 420)

    mono = ctk.CTkFont(family=opts["font_family"], size=opts["font_size"])
    title_font = ctk.CTkFont(size=max(16, opts["font_size"] + 7), weight="bold")
    sub_font = ctk.CTkFont(size=max(11, opts["font_size"]))

    header = ctk.CTkLabel(app, text="📍 HH AutoApply", font=title_font)
    header.pack(padx=16, pady=(14, 4), anchor="w")

    stamp = _code_stamp()
    sub = ctk.CTkLabel(
        app,
        text=f"🎯 отклики · лимит · резюме · 📖 код ui.py @ {stamp}",
        font=sub_font,
        text_color=("gray30", "gray70"),
    )
    sub.pack(padx=16, pady=(0, 8), anchor="w")

    status_var = tk.StringVar(value="🟡 готово")
    status_lbl = ctk.CTkLabel(app, textvariable=status_var, anchor="w", font=sub_font)
    status_lbl.pack(padx=16, pady=(0, 6), fill="x")

    # Только просмотр отчёта — не редактор
    text = ctk.CTkTextbox(app, font=mono, state="disabled")
    text.pack(padx=16, pady=8, fill="both", expand=True)

    btn_row = ctk.CTkFrame(app, fg_color="transparent")
    btn_row.pack(padx=16, pady=(0, 14), fill="x")

    cancel_event = threading.Event()
    busy_lock = threading.Lock()
    job_running = {"v": False}

    def set_busy(msg: str) -> None:
        status_var.set(msg)
        app.update_idletasks()

    def _set_report(body: str) -> None:
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", body)
        text.configure(state="disabled")

    def refresh_stats() -> None:
        set_busy("🟡 обновляю…")
        try:
            report = load_report(cfg)
            _set_report(format_stats_text(report))
            rem = report["remaining"]
            sent = report["sent_today"]
            lim = report["daily_limit"]
            status_var.set(f"✅ сегодня {sent}/{lim} · осталось {rem}")
        except Exception as e:
            status_var.set(f"❌ stats: {e}")

    def _begin_job(label: str) -> bool:
        with busy_lock:
            if job_running["v"]:
                status_var.set("⏸ уже идёт задача — сначала Отмена или дождись")
                return False
            job_running["v"] = True
            cancel_event.clear()
        set_busy(label)
        return True

    def _end_job() -> None:
        with busy_lock:
            job_running["v"] = False

    def request_cancel() -> None:
        if not job_running["v"]:
            status_var.set("📖 нечего отменять")
            return
        cancel_event.set()
        status_var.set("⏸ отмена… дождусь конца текущего шага")

    def do_raise() -> None:
        if not _begin_job("🟡 поднимаю резюме…"):
            return

        def worker() -> None:
            try:
                if cancel_event.is_set():
                    app.after(0, lambda: status_var.set("⏸ отменено до старта"))
                    return
                from hh_auto.resume import raise_resume

                result = raise_resume(cfg)
                if cancel_event.is_set():
                    app.after(0, lambda: status_var.set("⏸ отменено (после клика могло успеть)"))
                    app.after(0, refresh_stats)
                    return
                st = result["status"]
                icon = {
                    "raised": "✅",
                    "already_raised_skip": "⏭️",
                    "captcha": "❌",
                    "error": "❌",
                }.get(st, "🧩")
                app.after(0, lambda: status_var.set(f"{icon} resume: {st} — {result.get('detail') or ''}"))
                app.after(0, refresh_stats)
            except Exception as e:
                app.after(0, lambda: status_var.set(f"❌ resume: {e}"))
            finally:
                _end_job()

        threading.Thread(target=worker, daemon=True).start()

    def do_apply_dry() -> None:
        if not _begin_job("🟡 apply --dry-run…"):
            return

        def worker() -> None:
            try:
                from hh_auto.apply import cmd_apply

                code = cmd_apply(
                    cfg,
                    dry_run=True,
                    limit=5,
                    ranked_path=None,
                    cancel_event=cancel_event,
                )
                if code == 3:
                    msg = "⏸ apply отменён"
                else:
                    msg = f"{'✅' if code == 0 else '❌'} apply dry-run exit={code}"
                app.after(0, lambda: status_var.set(msg))
                app.after(0, refresh_stats)
            except Exception as e:
                app.after(0, lambda: status_var.set(f"❌ apply: {e}"))
            finally:
                _end_job()

        threading.Thread(target=worker, daemon=True).start()

    ctk.CTkButton(btn_row, text="🔄 Обновить", width=110, command=refresh_stats).pack(side="left", padx=(0, 8))
    ctk.CTkButton(btn_row, text="📄 Поднять резюме", width=150, command=do_raise).pack(side="left", padx=(0, 8))
    ctk.CTkButton(btn_row, text="🧪 Dry-run×5", width=120, command=do_apply_dry).pack(side="left", padx=(0, 8))
    ctk.CTkButton(
        btn_row,
        text="⏸ Отмена",
        width=100,
        fg_color=("#8B3A3A", "#6B2B2B"),
        hover_color=("#A04545", "#7A3333"),
        command=request_cancel,
    ).pack(side="left", padx=(0, 8))
    ctk.CTkLabel(btn_row, text="📖 CLI жив", text_color=("gray40", "gray60")).pack(side="right")

    refresh_stats()
    app.mainloop()
    return 0
