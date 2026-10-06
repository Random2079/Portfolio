from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from hh_auto import DATA, ensure_data_dir, load_config
from hh_auto.cover import render_cover
from hh_auto.score import keywords_table, rank_vacancies
from hh_auto.search import fetch_vacancies


def cmd_search(args: argparse.Namespace) -> int:
    cfg = load_config(Path(args.config) if args.config else None)
    ensure_data_dir()
    vacancies = fetch_vacancies(cfg)
    print(f"Сырых после фильтров: {len(vacancies)}")

    tags = cfg.get("profile_tags") or []
    min_score = int(cfg.get("min_score") or 2)
    ranked = rank_vacancies(vacancies, tags, min_score=min_score)
    template = cfg.get("cover_template") or "Отклик на {title} ({company})."
    for v in ranked:
        v["cover"] = render_cover(template, v)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    raw_path = DATA / f"vacancies_{stamp}.json"
    ranked_path = DATA / f"ranked_{stamp}.csv"
    kw_path = DATA / f"keywords_{stamp}.csv"
    ranked_json = DATA / f"ranked_{stamp}.json"

    with raw_path.open("w", encoding="utf-8") as f:
        json.dump(vacancies, f, ensure_ascii=False, indent=2)
    with ranked_json.open("w", encoding="utf-8") as f:
        json.dump(ranked, f, ensure_ascii=False, indent=2)

    with ranked_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["score", "title", "company", "area", "remote", "url", "hits"],
            extrasaction="ignore",
        )
        w.writeheader()
        for v in ranked:
            row = dict(v)
            row["hits"] = " | ".join(v.get("hits") or [])
            w.writerow(row)

    kw_rows = keywords_table(vacancies, tags)
    with kw_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tag", "label", "count"])
        w.writerows(kw_rows)

    print(f"Прошли min_score={min_score}: {len(ranked)}")
    print("\nТоп-5:")
    for v in ranked[:5]:
        print(f"  [{v.get('score')}] {v.get('title')} — {v.get('company')}")
        print(f"       {v.get('url')}")
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    from hh_auto.apply import cmd_login as _login

    cfg = load_config(Path(args.config) if args.config else None)
    return _login(cfg)


def cmd_apply(args: argparse.Namespace) -> int:
    from hh_auto.apply import cmd_apply as _apply

    cfg = load_config(Path(args.config) if args.config else None)
    ranked = Path(args.ranked) if args.ranked else None
    return _apply(cfg, dry_run=bool(args.dry_run), limit=args.limit, ranked_path=ranked)


def cmd_stats(args: argparse.Namespace) -> int:
    from hh_auto.stats import format_stats_text, load_report

    cfg = load_config(Path(args.config) if args.config else None)
    report = load_report(cfg)
    print(format_stats_text(report))
    return 0


def cmd_raise_resume(args: argparse.Namespace) -> int:
    from hh_auto.resume import raise_resume

    cfg = load_config(Path(args.config) if args.config else None)
    result = raise_resume(cfg, force=bool(getattr(args, "force", False)))
    print(f"resume: {result['status']}" + (f" — {result.get('detail')}" if result.get("detail") else ""))
    code = {"raised": 0, "already_raised_skip": 0, "captcha": 2, "error": 1}.get(result["status"], 1)
    return code


def cmd_ui(args: argparse.Namespace) -> int:
    from hh_auto.ui import run_ui

    cfg_path = Path(args.config) if args.config else None
    return run_ui(cfg_path)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hh_auto")
    p.add_argument("--config", default=None, help="путь к config.json")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="слой A: поиск + score + cover")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("login", help="слой B: логин hh → storage_state")
    s.set_defaults(func=cmd_login)

    a = sub.add_parser("apply", help="слой B: Playwright отклики")
    a.add_argument("--dry-run", action="store_true", help="без клика Откликнуться")
    a.add_argument("--limit", type=int, default=None, help="потолок на этот запуск/день")
    a.add_argument("--ranked", default=None, help="путь к ranked_*.json")
    a.set_defaults(func=cmd_apply)

    st = sub.add_parser("stats", help="отчёт: сегодня / лимит / статусы")
    st.set_defaults(func=cmd_stats)

    rr = sub.add_parser("raise-resume", help="поднять резюме на hh (идемпотентно)")
    rr.add_argument("--force", action="store_true", help="игнор cooldown из state")
    rr.set_defaults(func=cmd_raise_resume)

    ui = sub.add_parser("ui", help="окно отчётности + кнопки")
    ui.set_defaults(func=cmd_ui)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
