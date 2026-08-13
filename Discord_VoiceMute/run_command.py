"""CLI for layer B: text command → (optional) mute click. Still dry-run by default."""
from __future__ import annotations

import argparse
import sys

from config_util import load_config
from logging_util import setup_logging
from mute_click import perform_mute_click
from parse_command import format_command, parse_command


def main() -> None:
    ap = argparse.ArgumentParser(description="IDEA-005 layer B: parse / dry-run mute")
    ap.add_argument("text", nargs="*", help="e.g. замуть 3")
    ap.add_argument("--live", action="store_true", help="actually click (disables dry_run)")
    args = ap.parse_args()

    log = setup_logging()
    cfg = load_config()
    if args.live:
        cfg["dry_run"] = False
        log.warning("LIVE clicks enabled")

    text = " ".join(args.text).strip()
    if not text:
        text = input("команда> ").strip()

    cmd = parse_command(text)
    print(format_command(cmd))
    if cmd is None:
        sys.exit(1)

    ok = perform_mute_click(cfg, cmd.action, cmd.slot, log=log)
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
