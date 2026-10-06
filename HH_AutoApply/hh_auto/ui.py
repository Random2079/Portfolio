"""Tool-окно отчётности HH_AutoApply (CustomTkinter)."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from hh_auto import load_config
from hh_auto.stats import format_stats_text, load_report


def run_ui(config_path: Path | None = None) -> int:
    try:
        import customtkinter as ctk
    except ImportError:
        print("Нужен customtkinter: pip install customtkinter")
        return 1

    cfg = load_config(config_path)
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    app = ctk.CTk()
    app.title("HH AutoApply — отчёт")
    app.geometry("720x560")
    app.minsize(560, 420)

    header = ctk.CTkLabel(app, text="📍 HH AutoApply", font=ctk.CTkFont(size=20, weight="bold"))
    header.pack(padx=16, pady=(14, 4), anchor="w")

    sub = ctk.CTkLabel(
        app,
        text="🎯 отклики · лимит дня · поднятие резюме",
        font=ctk.CTkFont(size=13),
        text_color=("gray30", "gray70"),
    )
    sub.pack(padx=16, pady=(0, 8), anchor="w")

    status_var = tk.StringVar(value="🟡 готово")
    status_lbl = ctk.CTkLabel(app, textvariable=status_var, anchor="w")
    status_lbl.pack(padx=16, pady=(0, 6), fill="x")

    text = ctk.CTkTextbox(app, font=ctk.CTkFont(family="Consolas", size=13))
    text.pack(padx=16, pady=8, fill="both", expand=True)

    btn_row = ctk.CTkFrame(app, fg_color="transparent")
    btn_row.pack(padx=16, pady=(0, 14), fill="x")

    def set_busy(msg: str) -> None:
        status_var.set(msg)
        app.update_idletasks()

    def refresh_stats() -> None:
        set_busy("🟡 обновляю…")
        try:
            report = load_report(cfg)
            text.delete("1.0", "end")
            text.insert("1.0", format_stats_text(report))
            rem = report["remaining"]
            sent = report["sent_today"]
            lim = report["daily_limit"]
            status_var.set(f"✅ сегодня {sent}/{lim} · осталось {rem}")
        except Exception as e:
            status_var.set(f"❌ stats: {e}")

    def do_raise() -> None:
        def worker() -> None:
            set_busy("🟡 поднимаю резюме…")
            try:
                from hh_auto.resume import raise_resume

                result = raise_resume(cfg)
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

        threading.Thread(target=worker, daemon=True).start()

    def do_apply_dry() -> None:
        def worker() -> None:
            set_busy("🟡 apply --dry-run…")
            try:
                from hh_auto.apply import cmd_apply

                code = cmd_apply(cfg, dry_run=True, limit=5, ranked_path=None)
                app.after(0, lambda: status_var.set(f"{'✅' if code == 0 else '❌'} apply dry-run exit={code}"))
                app.after(0, refresh_stats)
            except Exception as e:
                app.after(0, lambda: status_var.set(f"❌ apply: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    ctk.CTkButton(btn_row, text="🔄 Обновить", width=120, command=refresh_stats).pack(side="left", padx=(0, 8))
    ctk.CTkButton(btn_row, text="📄 Поднять резюме", width=160, command=do_raise).pack(side="left", padx=(0, 8))
    ctk.CTkButton(btn_row, text="🧪 Apply dry-run×5", width=150, command=do_apply_dry).pack(side="left", padx=(0, 8))
    ctk.CTkLabel(btn_row, text="📖 CLI без UI жив", text_color=("gray40", "gray60")).pack(side="right")

    refresh_stats()
    app.mainloop()
    return 0
