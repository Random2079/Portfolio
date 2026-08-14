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
    def test_old_engines_become_kokoro(self) -> None:
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
                self.assertEqual(data["engine"], "kokoro")
                self.assertEqual(data["kokoro_voice"], "sveta")
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


if __name__ == "__main__":
    unittest.main()
