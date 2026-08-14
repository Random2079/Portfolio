"""Unit tests for Kokoro bridge / config — без GPU и без worker."""
from __future__ import annotations

import json
import sys
import tempfile
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


if __name__ == "__main__":
    unittest.main()
