"""
Global PTT (works while Discord is unfocused — game / browser).
Middle mouse and Shift+K → STATE.start/stop → command queue for the plugin to poll.

IMPORTANT: never run start/stop/decode on the pynput callback thread —
that freezes the whole Windows input stack (lag on every click).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

LOG = logging.getLogger("voicemute_stt")

_listeners_started = False
_shift_down = False
_lock = threading.Lock()
# idle | arming | recording | stopping
_state = "idle"
_end_requested = False
_hold_started = 0.0
_MIN_HOLD_MS = 280.0


def start_global_ptt(
    *,
    on_begin: Callable[[], dict],
    on_end: Callable[[], dict],
    mouse_button: str = "middle",
    enable_shift_k: bool = True,
) -> bool:
    """Start background pynput listeners. Returns False if pynput missing."""
    global _listeners_started
    if _listeners_started:
        return True
    try:
        from pynput import keyboard, mouse
    except ImportError:
        LOG.error("pynput not installed — pip install pynput (global PTT off)")
        return False

    btn = mouse.Button.middle
    if mouse_button == "x1":
        btn = mouse.Button.x1
    elif mouse_button == "x2":
        btn = mouse.Button.x2

    def _arm() -> None:
        global _state, _end_requested, _hold_started
        with _lock:
            if _state != "idle":
                return
            _state = "arming"
            _end_requested = False
            _hold_started = time.monotonic()
        LOG.info("Global PTT down")
        # #region agent log
        try:
            from pathlib import Path
            import json as _json
            import time as _time

            _p = Path(r"C:\Users\Home\OneDrive\Desktop\DS_Projects\Discord_MutePlugin\debug-121a69.log")
            with _p.open("a", encoding="utf-8") as _f:
                _f.write(
                    _json.dumps(
                        {
                            "sessionId": "121a69",
                            "hypothesisId": "C",
                            "location": "global_ptt.py:_arm",
                            "message": "ptt_down",
                            "data": {},
                            "timestamp": int(_time.time() * 1000),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception:
            pass
        # #endregion

        def work() -> None:
            global _state, _end_requested
            try:
                on_begin()
            except Exception:
                LOG.exception("global PTT begin failed")
                with _lock:
                    _state = "idle"
                    _end_requested = False
                return
            with _lock:
                if _end_requested:
                    _state = "stopping"
                    do_stop = True
                else:
                    _state = "recording"
                    do_stop = False
            if do_stop:
                _run_stop(on_end)

        threading.Thread(target=work, daemon=True, name="ptt-begin").start()

    def _release() -> None:
        global _state, _end_requested
        with _lock:
            if _state == "idle":
                return
            if _state == "arming":
                _end_requested = True
                LOG.info("Global PTT up (while arming) — will stop after start")
                return
            if _state != "recording":
                return
            held_ms = (time.monotonic() - _hold_started) * 1000.0
            _state = "stopping"
        if held_ms < _MIN_HOLD_MS:
            LOG.info("Global PTT too short (%.0fms) — ignore", held_ms)
            # #region agent log
            try:
                from pathlib import Path
                import json as _json
                import time as _time

                _p = Path(r"C:\Users\Home\OneDrive\Desktop\DS_Projects\Discord_MutePlugin\debug-121a69.log")
                with _p.open("a", encoding="utf-8") as _f:
                    _f.write(
                        _json.dumps(
                            {
                                "sessionId": "121a69",
                                "hypothesisId": "E",
                                "location": "global_ptt.py:_release",
                                "message": "ptt_too_short",
                                "data": {"held_ms": round(held_ms)},
                                "timestamp": int(_time.time() * 1000),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            except Exception:
                pass
            # #endregion
            try:
                # still stop mic to clean up
                on_end()
            except Exception:
                LOG.exception("global PTT short-stop failed")
            with _lock:
                _state = "idle"
                _end_requested = False
            return
        LOG.info("Global PTT up → stop+decode (async)")
        # #region agent log
        try:
            from pathlib import Path
            import json as _json
            import time as _time

            _p = Path(r"C:\Users\Home\OneDrive\Desktop\DS_Projects\Discord_MutePlugin\debug-121a69.log")
            with _p.open("a", encoding="utf-8") as _f:
                _f.write(
                    _json.dumps(
                        {
                            "sessionId": "121a69",
                            "hypothesisId": "C",
                            "location": "global_ptt.py:_release",
                            "message": "ptt_up_async_decode",
                            "data": {},
                            "timestamp": int(_time.time() * 1000),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception:
            pass
        # #endregion
        threading.Thread(target=_run_stop, args=(on_end,), daemon=True, name="ptt-end").start()

    def _run_stop(end_fn: Callable[[], dict]) -> None:
        global _state, _end_requested
        try:
            end_fn()
        except Exception:
            LOG.exception("global PTT end failed")
        finally:
            with _lock:
                _state = "idle"
                _end_requested = False

    def on_click(_x, _y, button, pressed):
        if button != btn:
            return
        # Return immediately — never block the OS mouse hook
        if pressed:
            _arm()
        else:
            _release()

    def on_press(key):
        global _shift_down
        if not enable_shift_k:
            return
        if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            _shift_down = True
            return
        if not _shift_down:
            return
        try:
            ch = getattr(key, "char", None)
            if ch and ch.lower() == "k":
                _arm()
        except Exception:
            pass

    def on_release(key):
        global _shift_down
        if not enable_shift_k:
            return
        if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            _shift_down = False
            _release()
            return
        try:
            ch = getattr(key, "char", None)
            if ch and ch.lower() == "k":
                _release()
        except Exception:
            pass

    mouse.Listener(on_click=on_click, daemon=True).start()
    if enable_shift_k:
        keyboard.Listener(on_press=on_press, on_release=on_release, daemon=True).start()

    _listeners_started = True
    LOG.info(
        "Global PTT armed: mouse=%s shift+k=%s (async, no input-hook lag)",
        mouse_button,
        enable_shift_k,
    )
    return True
