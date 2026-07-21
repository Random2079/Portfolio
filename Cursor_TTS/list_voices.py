"""Показать доступные голоса edge-tts. Запуск: python list_voices.py [ru|en|all]"""
from __future__ import annotations

import asyncio
import sys

import edge_tts


async def main() -> int:
    locale = sys.argv[1] if len(sys.argv) > 1 else "ru"
    voices = await edge_tts.list_voices()

    for voice in sorted(voices, key=lambda item: item["ShortName"]):
        loc = voice["Locale"]
        if locale != "all" and not loc.lower().startswith(locale.lower()):
            continue
        print(
            f"{voice['ShortName']}\t{voice['Gender']}\t{voice['FriendlyName']}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
