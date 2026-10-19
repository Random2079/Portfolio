"""Tool-окно отчётности HH_AutoApply (CustomTkinter)."""

from __future__ import annotations

import argparse
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from typing import Any

from hh_auto import load_config, playwright_headless, save_config
from hh_auto.stats import archive_and_clear_log, format_stats_text, load_report

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
    app.geometry(opts["geometry"] if opts["geometry"] != "720x560" else "780x720")
    app.minsize(700, 560)

    mono = ctk.CTkFont(family=opts["font_family"], size=opts["font_size"])
    title_font = ctk.CTkFont(size=max(16, opts["font_size"] + 7), weight="bold")
    sub_font = ctk.CTkFont(size=max(11, opts["font_size"]))

    header = ctk.CTkLabel(app, text="📍 HH AutoApply + Kwork", font=title_font)
    header.pack(padx=16, pady=(14, 4), anchor="w")

    stamp = _code_stamp()
    headless_on = playwright_headless(cfg)
    kw_lim = int((cfg.get("kwork") or {}).get("daily_limit") or 15)
    sub = ctk.CTkLabel(
        app,
        text=(
            f"🎯 HH {cfg.get('daily_limit', 100)}/день · Kwork {kw_lim}/день · "
            f"📖 ui.py @ {stamp}"
        ),
        font=sub_font,
        text_color=("gray30", "gray70"),
    )
    sub.pack(padx=16, pady=(0, 4), anchor="w")

    status_var = tk.StringVar(value="🟡 готово")
    status_lbl = ctk.CTkLabel(app, textvariable=status_var, anchor="w", font=sub_font)
    status_lbl.pack(padx=16, pady=(0, 4), fill="x")

    mode_row = ctk.CTkFrame(app, fg_color="transparent")
    mode_row.pack(padx=16, pady=(0, 4), fill="x")
    headless_var = tk.BooleanVar(value=headless_on)
    mode_hint = tk.StringVar(
        value="🙈 браузер в фоне" if headless_on else "👀 окно Chromium"
    )

    def on_headless_toggle() -> None:
        on = bool(headless_var.get())
        cfg.setdefault("playwright", {})["headless"] = on
        try:
            save_config(cfg)
            mode_hint.set("🙈 браузер в фоне" if on else "👀 окно Chromium")
            status_var.set("✅ режим браузера сохранён")
        except Exception as e:
            status_var.set(f"❌ config: {e}")

    ctk.CTkSwitch(
        mode_row,
        text="фон без окна",
        variable=headless_var,
        command=on_headless_toggle,
        font=sub_font,
    ).pack(side="left")
    ctk.CTkLabel(mode_row, textvariable=mode_hint, font=sub_font, text_color=("gray30", "gray70")).pack(
        side="left", padx=(12, 0)
    )

    batch_row = ctk.CTkFrame(app, fg_color="transparent")
    batch_row.pack(padx=16, pady=(0, 6), fill="x")
    ctk.CTkLabel(batch_row, text="за раз:", font=sub_font).pack(side="left")
    limit_entry = ctk.CTkEntry(batch_row, width=56, font=sub_font)
    limit_entry.insert(0, "20")
    limit_entry.pack(side="left", padx=(8, 0))
    ctk.CTkLabel(
        batch_row,
        text="(LIVE откликов за один запуск)",
        font=sub_font,
        text_color=("gray40", "gray60"),
    ).pack(side="left", padx=(10, 0))

    text = ctk.CTkTextbox(app, font=mono, state="disabled")
    text.pack(padx=16, pady=8, fill="both", expand=True)

    btn_row = ctk.CTkFrame(app, fg_color="transparent")
    btn_row.pack(padx=16, pady=(0, 8), fill="x")
    btn_row2 = ctk.CTkFrame(app, fg_color="transparent")
    btn_row2.pack(padx=16, pady=(0, 14), fill="x")

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
                status_var.set("⏸ уже идёт задача — Отмена или подожди")
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
        status_var.set("⏸ отмена…")

    def _batch_limit() -> int:
        try:
            n = int(limit_entry.get().strip())
        except ValueError:
            n = 20
        return max(1, min(n, int(cfg.get("daily_limit") or 100)))

    def do_search() -> None:
        if not _begin_job("🟡 поиск вакансий…"):
            return

        def worker() -> None:
            try:
                from hh_auto.__main__ import cmd_search

                code = cmd_search(argparse.Namespace(config=None))
                app.after(
                    0,
                    lambda: status_var.set(
                        f"{'✅' if code == 0 else '❌'} поиск exit={code} · список обновлён"
                    ),
                )
                app.after(0, refresh_stats)
            except Exception as e:
                app.after(0, lambda: status_var.set(f"❌ search: {e}"))
            finally:
                _end_job()

        threading.Thread(target=worker, daemon=True).start()

    def do_apply_live() -> None:
        lim = _batch_limit()
        if not _begin_job(f"🟡 LIVE отклики ×{lim}…"):
            return

        def worker() -> None:
            try:
                from hh_auto.apply import cmd_apply

                code = cmd_apply(
                    cfg,
                    dry_run=False,
                    limit=lim,
                    ranked_path=None,
                    cancel_event=cancel_event,
                )
                if code == 3:
                    msg = "⏸ LIVE отменён"
                elif code == 2:
                    msg = "❌ LIVE стоп: капча"
                elif code == 1:
                    msg = "❌ LIVE: нет login/storage — python -m hh_auto login"
                else:
                    msg = f"✅ LIVE готово exit={code}"
                app.after(0, lambda: status_var.set(msg))
                app.after(0, refresh_stats)
            except Exception as e:
                app.after(0, lambda: status_var.set(f"❌ apply: {e}"))
            finally:
                _end_job()

        threading.Thread(target=worker, daemon=True).start()

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
                st = result["status"]
                icon = {
                    "raised": "✅",
                    "already_raised_skip": "⏭️",
                    "captcha": "❌",
                    "error": "❌",
                }.get(st, "🧩")
                app.after(
                    0,
                    lambda: status_var.set(f"{icon} resume: {st} — {result.get('detail') or ''}"),
                )
                app.after(0, refresh_stats)
            except Exception as e:
                app.after(0, lambda: status_var.set(f"❌ resume: {e}"))
            finally:
                _end_job()

        threading.Thread(target=worker, daemon=True).start()

    def do_clear_log() -> None:
        try:
            dest = archive_and_clear_log()
            if dest:
                status_var.set(f"🗑 лог сброшен → {dest.name}")
            else:
                status_var.set("🗑 лог уже пуст")
            refresh_stats()
        except Exception as e:
            status_var.set(f"❌ сброс лога: {e}")

    ctk.CTkButton(btn_row, text="🔍 Поиск", width=100, command=do_search).pack(side="left", padx=(0, 8))
    ctk.CTkButton(
        btn_row,
        text="📨 Отклики LIVE",
        width=140,
        fg_color=("#2B6B3F", "#1E4D2E"),
        hover_color=("#34824C", "#266038"),
        command=do_apply_live,
    ).pack(side="left", padx=(0, 8))
    ctk.CTkButton(btn_row, text="📄 Резюме↑", width=110, command=do_raise).pack(side="left", padx=(0, 8))
    ctk.CTkButton(
        btn_row,
        text="⏸ Отмена",
        width=100,
        fg_color=("#8B3A3A", "#6B2B2B"),
        hover_color=("#A04545", "#7A3333"),
        command=request_cancel,
    ).pack(side="left", padx=(0, 8))

    ctk.CTkButton(btn_row2, text="🔄 Статистика", width=120, command=refresh_stats).pack(
        side="left", padx=(0, 8)
    )
    ctk.CTkButton(btn_row2, text="🗑 Сброс лога", width=120, command=do_clear_log).pack(
        side="left", padx=(0, 8)
    )

    # --- Kwork LIVE цикл ---
    kw_frame = ctk.CTkFrame(app, fg_color=("gray90", "gray18"))
    kw_frame.pack(padx=16, pady=(0, 8), fill="x")
    ctk.CTkLabel(kw_frame, text="🧩 Kwork (DeepSeek → LIVE)", font=sub_font).pack(
        padx=10, pady=(8, 4), anchor="w"
    )
    kw_status = tk.StringVar(value="⏸ цикл выкл")
    ctk.CTkLabel(kw_frame, textvariable=kw_status, font=sub_font, text_color=("gray30", "gray70")).pack(
        padx=10, pady=(0, 4), anchor="w"
    )
    kw_btns = ctk.CTkFrame(kw_frame, fg_color="transparent")
    kw_btns.pack(padx=10, pady=(0, 10), fill="x")

    kwork_loop_on = {"v": False}
    kwork_after_id = {"id": None}
    interval_min = int((cfg.get("kwork") or {}).get("interval_minutes") or 60)

    def refresh_kwork_feed() -> None:
        try:
            from hh_auto.kwork_ai import load_deepseek_api_key
            from hh_auto.kwork_apply import format_kwork_feed, kwork_today_count, read_log
            from hh_auto.kwork_usage import format_usage_line

            sent, lim = kwork_today_count(cfg)
            usage = format_usage_line(load_deepseek_api_key())
            body = (
                f"📍 Kwork сегодня {sent}/{lim}\n{usage}\n\n"
                + format_kwork_feed(read_log(40))
            )
            _set_report(body)
            kw_status.set(usage[:90] + ("…" if len(usage) > 90 else ""))
            status_var.set(f"✅ Kwork лента · сегодня {sent}/{lim}")
        except Exception as e:
            status_var.set(f"❌ kwork feed: {e}")

    def _schedule_next_tick() -> None:
        if kwork_after_id["id"] is not None:
            try:
                app.after_cancel(kwork_after_id["id"])
            except Exception:
                pass
            kwork_after_id["id"] = None
        if not kwork_loop_on["v"]:
            return
        ms = max(60_000, interval_min * 60_000)
        kw_status.set(f"▶ цикл · следующий тик через {interval_min} мин")
        kwork_after_id["id"] = app.after(ms, _kwork_timer_fire)

    def _kwork_timer_fire() -> None:
        if not kwork_loop_on["v"]:
            return
        do_kwork_tick(dry_run=False, from_timer=True)

    def do_kwork_tick(*, dry_run: bool = False, from_timer: bool = False) -> None:
        label = "🟡 Kwork dry-run…" if dry_run else "🟡 Kwork LIVE тик…"
        if not _begin_job(label):
            if from_timer:
                _schedule_next_tick()
            return

        def worker() -> None:
            try:
                from hh_auto.kwork_loop import format_tick_summary, run_tick

                summary = run_tick(
                    cfg,
                    dry_run=dry_run,
                    cancel_event=cancel_event,
                    on_progress=lambda m: app.after(0, lambda msg=m: status_var.set(msg)),
                )
                msg = format_tick_summary(summary).split("\n")[0]
                app.after(0, lambda: status_var.set(msg[:120]))
                app.after(0, refresh_kwork_feed)
            except Exception as e:
                app.after(0, lambda: status_var.set(f"❌ kwork tick: {e}"))
            finally:
                _end_job()
                if from_timer or kwork_loop_on["v"]:
                    app.after(0, _schedule_next_tick)

        threading.Thread(target=worker, daemon=True).start()

    def kwork_start_loop() -> None:
        kwork_loop_on["v"] = True
        kw_status.set("▶ цикл включён · тик сейчас…")
        do_kwork_tick(dry_run=False, from_timer=True)

    def kwork_stop_loop() -> None:
        kwork_loop_on["v"] = False
        if kwork_after_id["id"] is not None:
            try:
                app.after_cancel(kwork_after_id["id"])
            except Exception:
                pass
            kwork_after_id["id"] = None
        kw_status.set("⏸ цикл выкл")
        status_var.set("⏸ Kwork цикл остановлен")

    def do_kwork_login() -> None:
        if not _begin_job("🟡 Kwork login (окно Chromium)…"):
            return

        def worker() -> None:
            try:
                code = _gui_kwork_login(cfg)
                app.after(
                    0,
                    lambda: status_var.set(
                        f"{'✅' if code == 0 else '❌'} kwork-login exit={code}"
                    ),
                )
            except Exception as e:
                app.after(0, lambda: status_var.set(f"❌ kwork login: {e}"))
            finally:
                _end_job()

        threading.Thread(target=worker, daemon=True).start()

    ctk.CTkButton(
        kw_btns,
        text="▶ Старт цикла",
        width=120,
        fg_color=("#2B6B3F", "#1E4D2E"),
        hover_color=("#34824C", "#266038"),
        command=kwork_start_loop,
    ).pack(side="left", padx=(0, 8))
    ctk.CTkButton(
        kw_btns,
        text="⏸ Стоп",
        width=80,
        fg_color=("#8B3A3A", "#6B2B2B"),
        hover_color=("#A04545", "#7A3333"),
        command=kwork_stop_loop,
    ).pack(side="left", padx=(0, 8))
    ctk.CTkButton(
        kw_btns,
        text="🔄 Тик сейчас",
        width=110,
        command=lambda: do_kwork_tick(dry_run=False),
    ).pack(side="left", padx=(0, 8))
    ctk.CTkButton(
        kw_btns,
        text="🧪 Dry-run",
        width=90,
        command=lambda: do_kwork_tick(dry_run=True),
    ).pack(side="left", padx=(0, 8))
    ctk.CTkButton(kw_btns, text="🔑 Login", width=80, command=do_kwork_login).pack(
        side="left", padx=(0, 8)
    )
    ctk.CTkButton(kw_btns, text="📨 Лента", width=80, command=refresh_kwork_feed).pack(
        side="left", padx=(0, 8)
    )

    refresh_stats()
    app.mainloop()
    return 0


def _gui_kwork_login(cfg: dict[str, Any]) -> int:
    """Login без input() в терминале: окно Chromium + messagebox."""
    from tkinter import messagebox

    from playwright.sync_api import sync_playwright

    from hh_auto import ensure_data_dir
    from hh_auto.kwork_apply import _logged_in, _visible_captcha
    from hh_auto.kwork_search import storage_state_path

    state_file = storage_state_path(cfg)
    ensure_data_dir()
    slow = int((cfg.get("playwright") or {}).get("slow_mo_ms") or 0)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=slow)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://kwork.ru/login", wait_until="domcontentloaded")
        messagebox.showinfo(
            "Kwork login",
            "Залогинься в открывшемся Chromium.\nКогда кабинет открыт — нажми OK.",
        )
        try:
            page.goto("https://kwork.ru/seller", wait_until="domcontentloaded")
        except Exception:
            pass
        if _visible_captcha(page):
            browser.close()
            return 2
        if not _logged_in(page):
            browser.close()
            return 1
        context.storage_state(path=str(state_file))
        browser.close()
    return 0
