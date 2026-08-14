from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)


def notify_toast(title: str, message: str, url: str = "") -> None:
    """Show a Windows toast. No-op-ish fallback on non-Windows."""
    body = message if not url else f"{message}\n{url}"
    body = body[:250]
    title = title[:60] or "Portfolio News"

    if sys.platform != "win32":
        log.info("toast skipped (not Windows): %s — %s", title, body)
        return

    try:
        from winotify import Notification, audio

        toast = Notification(
            app_id="Portfolio News",
            title=title,
            msg=body,
            duration="short",
        )
        toast.set_audio(audio.Default, loop=False)
        if url:
            toast.add_actions(label="Открыть", launch=url)
        toast.show()
    except Exception as exc:  # noqa: BLE001 — toast must never kill poller
        log.warning("toast failed: %s", exc)
        print(f"[toast] {title}: {body}", flush=True)
