from __future__ import annotations

import argparse
import csv
import json
import re
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


def cmd_kwork_login(args: argparse.Namespace) -> int:
    from hh_auto.kwork_apply import cmd_login as _login

    cfg = load_config(Path(args.config) if args.config else None)
    return _login(cfg)


def cmd_kwork_tick(args: argparse.Namespace) -> int:
    from hh_auto.kwork_loop import format_tick_summary, run_tick

    cfg = load_config(Path(args.config) if args.config else None)
    summary = run_tick(
        cfg,
        dry_run=bool(args.dry_run),
        limit=args.limit,
        on_progress=lambda m: print(m),
    )
    print(format_tick_summary(summary))
    if not summary.get("ok"):
        return 1
    if any((r.get("status") == "captcha") for r in (summary.get("rows") or [])):
        return 2
    return 0


def cmd_kwork_feed(args: argparse.Namespace) -> int:
    from hh_auto.kwork_ai import load_deepseek_api_key
    from hh_auto.kwork_apply import format_kwork_feed, kwork_today_count, read_log
    from hh_auto.kwork_usage import format_usage_line

    cfg = load_config(Path(args.config) if args.config else None)
    sent, lim = kwork_today_count(cfg)
    print(f"сегодня {sent}/{lim}")
    print(format_usage_line(load_deepseek_api_key(), refresh_balance=True))
    print(format_kwork_feed(read_log(limit=int(args.limit or 40))))
    return 0


def cmd_tg_scan(args: argparse.Namespace) -> int:
    from hh_auto.tg_scan import scan_bundle
    from hh_auto.yj_resolve import resolve_many

    cfg = load_config(Path(args.config) if args.config else None)
    ensure_data_dir()
    bundle = scan_bundle(cfg)
    vacancies = list(bundle["text_vacancies"])
    print(f"Сырых текст-карточек: {len(vacancies)}")

    hh_ready: list[dict] = []
    resolve = bool(getattr(args, "resolve_hh", False))
    if resolve:
        yj_urls = bundle["yj_urls"]
        lim = getattr(args, "resolve_limit", None)
        if lim is None:
            lim = int((cfg.get("telegram") or {}).get("resolve_limit") or 20)
        print(f"Резолв YJ→HH (limit={lim}, urls={len(yj_urls)})…")
        resolved = resolve_many(yj_urls, cfg, limit=lim)
        ok_n = sum(1 for r in resolved if r.get("status") == "ok")
        print(f"YJ ok={ok_n} / tried={len(resolved)}")
        for r in resolved:
            if r.get("status") != "ok" or not r.get("hh_id"):
                continue
            title = (r.get("title") or "").split("|")[0].strip() or f"HH {r['hh_id']}"
            hh_ready.append(
                {
                    "id": str(r["hh_id"]),
                    "title": title[:160],
                    "company": "",
                    "area": "",
                    "remote": True,
                    "url": r["hh_url"],
                    "requirement": f"via YJ {r.get('yj')}",
                    "responsibility": "",
                    "source": "youngjunior",
                    "yj_url": r.get("yj") or "",
                    "level_guess": "juniorish",
                }
            )
        for u in bundle["hh_urls"]:
            m = re.search(r"/vacancy/(\d+)", u)
            if not m:
                continue
            vid = m.group(1)
            if any(x["id"] == vid for x in hh_ready):
                continue
            hh_ready.append(
                {
                    "id": vid,
                    "title": f"HH {vid}",
                    "company": "",
                    "area": "",
                    "remote": True,
                    "url": f"https://hh.ru/vacancy/{vid}",
                    "requirement": "direct link from TG",
                    "responsibility": "",
                    "source": "telegram_hh",
                    "level_guess": "juniorish",
                }
            )
        vacancies = hh_ready + vacancies

    tags = cfg.get("profile_tags") or []
    min_score = int((cfg.get("telegram") or {}).get("min_score") or cfg.get("min_score") or 1)
    # HH-карточки с пустым текстом: min_score 0 для source youngjunior/telegram_hh
    scored: list[dict] = []
    for v in vacancies:
        if v.get("source") in ("youngjunior", "telegram_hh"):
            row = dict(v)
            row["score"] = max(1, len(tags) and 1)
            row["hits"] = ["yj→hh"] if v.get("source") == "youngjunior" else ["hh-direct"]
            scored.append(row)
        else:
            ranked_one = rank_vacancies([v], tags, min_score=min_score)
            scored.extend(ranked_one)
    scored.sort(key=lambda x: (-int(x.get("score") or 0), x.get("title") or ""))

    template = cfg.get("cover_template") or "Отклик на {title} ({company})."
    for v in scored:
        v["cover"] = render_cover(template, v)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    raw_path = DATA / f"tg_vacancies_{stamp}.json"
    ranked_json = DATA / f"tg_ranked_{stamp}.json"
    apply_json = DATA / f"ranked_tg_{stamp}.json"
    ranked_csv = DATA / f"tg_ranked_{stamp}.csv"

    with raw_path.open("w", encoding="utf-8") as f:
        json.dump(vacancies, f, ensure_ascii=False, indent=2)
    with ranked_json.open("w", encoding="utf-8") as f:
        json.dump(scored, f, ensure_ascii=False, indent=2)
    # только то, что apply сможет открыть на hh
    apply_rows = [
        v
        for v in scored
        if (v.get("url") or "").startswith("https://hh.ru/vacancy/")
        and str(v.get("id") or "").isdigit()
    ]
    with apply_json.open("w", encoding="utf-8") as f:
        json.dump(apply_rows, f, ensure_ascii=False, indent=2)
    with ranked_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "score",
                "level_guess",
                "title",
                "company",
                "remote",
                "source",
                "channel",
                "url",
                "yj_url",
                "hits",
                "datetime",
            ],
            extrasaction="ignore",
        )
        w.writeheader()
        for v in scored:
            row = dict(v)
            row["hits"] = " | ".join(v.get("hits") or [])
            w.writerow(row)

    print(f"В выдаче: {len(scored)} · для apply (hh id): {len(apply_rows)}")
    print(f"→ {ranked_csv}")
    if apply_rows:
        print(f"→ apply: python -m hh_auto apply --ranked {apply_json}")
    print("\nТоп:")
    for v in scored[:15]:
        print(
            f"  [{v.get('score')}|{v.get('source') or 'tg'}] {str(v.get('title') or '')[:70]}"
        )
        print(f"       {v.get('url')}")
    return 0


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

    tg = sub.add_parser(
        "tg-scan",
        help="скан t.me/s каналов (job_python/young_june) → score + cover",
    )
    tg.add_argument(
        "--resolve-hh",
        action="store_true",
        help="YJ/прямые hh-ссылки → hh.ru/vacancy (Playwright) + ranked_tg_*.json",
    )
    tg.add_argument(
        "--resolve-limit",
        type=int,
        default=None,
        help="сколько YJ-карточек резолвить (default config/20)",
    )
    tg.set_defaults(func=cmd_tg_scan)

    kl = sub.add_parser("kwork-login", help="логин Kwork → data/kwork_storage_state.json")
    kl.set_defaults(func=cmd_kwork_login)

    kt = sub.add_parser("kwork-tick", help="один тик: поиск → DeepSeek → LIVE заявки")
    kt.add_argument("--dry-run", action="store_true", help="без отправки на биржу")
    kt.add_argument("--limit", type=int, default=None, help="потолок заявок за тик")
    kt.set_defaults(func=cmd_kwork_tick)

    kf = sub.add_parser("kwork-feed", help="лента отправленных заявок Kwork")
    kf.add_argument("--limit", type=int, default=40, help="сколько строк лога")
    kf.set_defaults(func=cmd_kwork_feed)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
