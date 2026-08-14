from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from portfolio_news.config import get_settings
from portfolio_news.db import make_session_factory
from portfolio_news.import_tickers import (
    load_tickers_from_json,
    load_tickers_from_snowball_csv,
    upsert_tickers,
)
from portfolio_news.poller import poll_once

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("portfolio_news")


def cmd_import(args: argparse.Namespace) -> int:
    settings = get_settings()
    Session = make_session_factory(settings.database_url)
    path = Path(args.path) if args.path else settings.tickers_json
    if not path.exists():
        log.error("file not found: %s", path)
        return 1
    if path.suffix.lower() == ".csv":
        items = load_tickers_from_snowball_csv(path)
    else:
        items = load_tickers_from_json(path)
    with Session() as session:
        n = upsert_tickers(session, items)
    log.info("imported %s tickers from %s", n, path)
    return 0


def cmd_once(args: argparse.Namespace) -> int:
    settings = get_settings()
    Session = make_session_factory(settings.database_url)
    # seed if empty
    with Session() as session:
        from sqlalchemy import select
        from portfolio_news.db import Ticker

        if session.scalar(select(Ticker.id).limit(1)) is None:
            upsert_tickers(session, load_tickers_from_json(settings.tickers_json))
        stats = poll_once(
            session,
            limit=args.limit if args.limit is not None else settings.poll_limit,
            notify=not args.quiet,
        )
    log.info("poll done: %s", stats)
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    settings = get_settings()
    interval = args.interval or settings.poll_interval_sec
    log.info("watch every %s sec", interval)
    while True:
        code = cmd_once(args)
        if code != 0:
            return code
        time.sleep(interval)


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "portfolio_news.api:app",
        host=args.host or settings.host,
        port=args.port or settings.port,
        reload=args.reload,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="portfolio_news", description="IDEA-003 portfolio news monitor")
    sub = p.add_subparsers(dest="cmd", required=True)

    imp = sub.add_parser("import-tickers", help="Load tickers JSON or Snowball CSV into SQLite")
    imp.add_argument("path", nargs="?", default=None, help="Path to tickers.example.json or Snowball CSV")
    imp.set_defaults(func=cmd_import)

    once = sub.add_parser("once", help="One poll pass")
    once.add_argument("--limit", type=int, default=None, help="Max tickers this run")
    once.add_argument("--quiet", action="store_true", help="Do not show toasts")
    once.set_defaults(func=cmd_once)

    watch = sub.add_parser("watch", help="Poll in a loop")
    watch.add_argument("--interval", type=int, default=None)
    watch.add_argument("--limit", type=int, default=None)
    watch.add_argument("--quiet", action="store_true")
    watch.set_defaults(func=cmd_watch)

    serve = sub.add_parser("serve", help="Run FastAPI (uvicorn)")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
