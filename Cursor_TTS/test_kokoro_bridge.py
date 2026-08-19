"""Unit tests for Kokoro bridge / config — без GPU и без worker."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class NormalizeVoiceTests(unittest.TestCase):
    def test_known_voices(self) -> None:
        from speak_kokoro import normalize_voice

        self.assertEqual(normalize_voice("sveta"), "sveta")
        self.assertEqual(normalize_voice("MASHA"), "masha")
        self.assertEqual(normalize_voice("dima"), "dima")

    def test_unknown_falls_back(self) -> None:
        from speak_kokoro import normalize_voice

        self.assertEqual(normalize_voice("../etc/passwd"), "sveta")
        self.assertEqual(normalize_voice(""), "sveta")
        self.assertEqual(normalize_voice(None), "sveta")


class WorkerConstantsTests(unittest.TestCase):
    def test_dima_uses_separate_checkpoint(self) -> None:
        # Импорт worker без torch (тяжёлое — только при вызовах)
        micro = ROOT / "micro_wife"
        if str(micro) not in sys.path:
            sys.path.insert(0, str(micro))
        import kokoro_worker as kw

        self.assertEqual(kw.VOICE_MODELS["sveta"], "kokoro-ru-v2-base.pth")
        self.assertEqual(kw.VOICE_MODELS["masha"], "kokoro-ru-v2-base.pth")
        self.assertEqual(kw.VOICE_MODELS["dima"], "kokoro-ru-v2-dima.pth")

    def test_worker_rejects_bad_voice(self) -> None:
        micro = ROOT / "micro_wife"
        if str(micro) not in sys.path:
            sys.path.insert(0, str(micro))
        import kokoro_worker as kw

        with self.assertRaises(ValueError):
            kw._normalize_voice("../x")
        with self.assertRaises(ValueError):
            kw._normalize_voice("not_a_voice")


class ConfigMigrationTests(unittest.TestCase):
    def test_old_engines_become_local(self) -> None:
        import TTS_Panel as panel

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "tts_config.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "engine": "piper",
                        "piper_model": "models/ru_RU-dmitri-medium.onnx",
                        "voice": "ru-RU-DmitryNeural",
                        "volume": 50,
                    }
                ),
                encoding="utf-8",
            )
            old = panel.CONFIG_FILE
            try:
                panel.CONFIG_FILE = cfg_path
                data = panel.load_config()
                self.assertEqual(data["engine"], "local")
                self.assertEqual(data["local_speaker"], "xenia")
            finally:
                panel.CONFIG_FILE = old

    def test_dict_and_en_collapses(self) -> None:
        import TTS_Panel as panel

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "tts_config.json"
            cfg_path.write_text(
                json.dumps({"engine": "kokoro", "hybrid_mode": "dict_and_en"}),
                encoding="utf-8",
            )
            old = panel.CONFIG_FILE
            try:
                panel.CONFIG_FILE = cfg_path
                data = panel.load_config()
                self.assertEqual(data["hybrid_mode"], "dict_only")
            finally:
                panel.CONFIG_FILE = old


class StopCancelTests(unittest.TestCase):
    def test_stop_worker_does_not_wait_on_request_lock(self) -> None:
        """Stop должен убить worker, даже если synth держит _request_lock."""
        import speak_kokoro as sk

        held = threading.Event()
        released = threading.Event()

        def hold_request_lock() -> None:
            with sk._request_lock:
                held.set()
                released.wait(timeout=5)

        t = threading.Thread(target=hold_request_lock, daemon=True)
        t.start()
        self.assertTrue(held.wait(timeout=2))
        gen_before = sk._generation
        started = time.monotonic()
        sk.stop_worker()
        elapsed = time.monotonic() - started
        released.set()
        t.join(timeout=2)
        self.assertLess(elapsed, 1.0, "stop_worker blocked on request lock")
        self.assertGreater(sk._generation, gen_before)


class ProgressStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        import tts_daemon as daemon

        daemon.set_warmup_active(False)
        daemon.set_paused(False)

    def test_daemon_reports_chunk_progress(self) -> None:
        import tts_daemon as daemon

        daemon.set_progress("synthesizing", engine="qwen", current=3, total=11)
        status = daemon.progress_snapshot()
        self.assertEqual(status["phase"], "synthesizing")
        self.assertEqual(status["engine"], "qwen")
        self.assertEqual(status["current"], 3)
        self.assertEqual(status["total"], 11)

    def test_elapsed_freezes_while_paused(self) -> None:
        import tts_daemon as daemon

        daemon.set_paused(False)
        daemon.set_progress("playing", engine="kokoro", current=1, total=1)
        time.sleep(0.05)
        before = int(daemon.progress_snapshot()["elapsed_sec"])
        daemon.set_paused(True)
        time.sleep(0.25)
        during = int(daemon.progress_snapshot()["elapsed_sec"])
        self.assertEqual(during, before)
        daemon.set_paused(False)
        time.sleep(0.15)
        after = int(daemon.progress_snapshot()["elapsed_sec"])
        self.assertGreaterEqual(after, during)

    def test_panel_formats_synthesis_and_queue(self) -> None:
        import TTS_Panel as panel

        text = panel.format_daemon_progress(
            {
                "phase": "synthesizing",
                "engine": "qwen",
                "current": 3,
                "total": 11,
                "queue": 2,
                "warming": False,
                "paused": False,
                "elapsed_sec": 12,
            }
        )
        self.assertIn("синтез 3 из 11", text)
        self.assertIn("12 с", text)
        self.assertIn("в очереди: 2", text)
        self.assertNotIn("%", text)
        value, maximum, indeterminate, title = panel.progress_bar_state(
            {
                "phase": "synthesizing",
                "current": 3,
                "total": 11,
                "elapsed_sec": 12,
                "warming": False,
                "paused": False,
            }
        )
        self.assertTrue(indeterminate)
        self.assertEqual(maximum, 0)
        self.assertIn("3/11", title)

    def test_single_chunk_synth_is_indeterminate(self) -> None:
        import TTS_Panel as panel

        text = panel.format_daemon_progress(
            {
                "phase": "synthesizing",
                "engine": "kokoro",
                "current": 1,
                "total": 1,
                "queue": 0,
                "warming": False,
                "paused": False,
                "elapsed_sec": 22,
            }
        )
        self.assertIn("ждём звук", text)
        self.assertIn("22 с", text)
        self.assertNotIn("%", text)
        _value, _maximum, indeterminate, title = panel.progress_bar_state(
            {
                "phase": "synthesizing",
                "current": 1,
                "total": 1,
                "elapsed_sec": 22,
                "warming": False,
                "paused": False,
            }
        )
        self.assertTrue(indeterminate)
        self.assertIn("22с", title)

    def test_playing_multi_chunk_uses_chunk_bar(self) -> None:
        import TTS_Panel as panel

        value, maximum, indeterminate, title = panel.progress_bar_state(
            {
                "phase": "playing",
                "current": 2,
                "total": 5,
                "elapsed_sec": 3,
                "warming": False,
                "paused": False,
            }
        )
        self.assertFalse(indeterminate)
        self.assertEqual(value, 2)
        self.assertEqual(maximum, 5)
        self.assertIn("2/5", title)

    def test_warmup_elapsed_resets_on_new_warmup(self) -> None:
        import tts_daemon as daemon

        old = daemon.set_warmup_active(True, engine="qwen")
        started = daemon._warmup_started
        time.sleep(0.05)
        new = daemon.set_warmup_active(True, engine="local")
        snap = daemon.progress_snapshot()
        self.assertGreater(daemon._warmup_started, started)
        self.assertEqual(int(snap["elapsed_sec"]), 0)
        self.assertEqual(snap["engine"], "local")
        self.assertTrue(snap["warming"])
        daemon.end_warmup(old)
        self.assertTrue(daemon.progress_snapshot()["warming"])
        daemon.end_warmup(new)
        self.assertFalse(daemon.progress_snapshot()["warming"])

    def test_panel_hides_old_engine_warmup_seconds(self) -> None:
        import TTS_Panel as panel

        text = panel.format_daemon_progress(
            {
                "phase": "idle",
                "engine": "local",
                "current": 0,
                "total": 0,
                "queue": 0,
                "warming": True,
                "paused": False,
                "elapsed_sec": 0,
            }
        )
        self.assertIn("загрузка модели", text)
        self.assertIn("0 с", text)
        self.assertIn("LOCAL", text)

    def test_preview_blocked_while_warming(self) -> None:
        import TTS_Panel as panel

        self.assertFalse(
            panel.preview_allowed({"warming": True, "phase": "idle"})
        )
        self.assertTrue(
            panel.preview_allowed({"warming": False, "phase": "idle"})
        )
        self.assertTrue(
            panel.preview_allowed({"warming": False, "phase": "playing"})
        )

    def test_warmup_stale_after_limit(self) -> None:
        import TTS_Panel as panel

        self.assertFalse(
            panel.warmup_is_stale({"warming": True, "elapsed_sec": 30})
        )
        self.assertTrue(
            panel.warmup_is_stale(
                {"warming": True, "elapsed_sec": panel.WARMUP_STALE_SEC}
            )
        )
        text = panel.format_daemon_progress(
            {
                "phase": "idle",
                "engine": "qwen",
                "current": 0,
                "total": 0,
                "queue": 0,
                "warming": True,
                "paused": False,
                "elapsed_sec": panel.WARMUP_STALE_SEC,
            }
        )
        self.assertIn("зависла", text)
        self.assertIn("Silero", text)
        _v, _m, _ind, title = panel.progress_bar_state(
            {
                "phase": "idle",
                "warming": True,
                "elapsed_sec": panel.WARMUP_STALE_SEC,
            }
        )
        self.assertIn("зависла", title)

    def test_warmup_stale_flag_from_daemon(self) -> None:
        import TTS_Panel as panel

        self.assertTrue(
            panel.warmup_is_stale(
                {"warming": True, "elapsed_sec": 10, "warmup_stale": True}
            )
        )

    def test_try_begin_warmup_is_single_flight(self) -> None:
        import tts_daemon as daemon

        token = daemon.try_begin_warmup("qwen")
        self.assertIsInstance(token, int)
        self.assertGreater(token, 0)
        self.assertIsNone(daemon.try_begin_warmup("qwen"))
        self.assertEqual(daemon.try_begin_warmup("local"), daemon.WARMUP_BUSY_OTHER)
        snap = daemon.progress_snapshot()
        self.assertTrue(snap["warming"])
        self.assertEqual(snap["engine"], "qwen")
        self.assertFalse(snap["warmup_stale"])
        daemon.end_warmup(token)
        self.assertFalse(daemon.progress_snapshot()["warming"])
        local = daemon.try_begin_warmup("local")
        self.assertGreater(local, 0)
        daemon.end_warmup(local)


if __name__ == "__main__":
    unittest.main()
