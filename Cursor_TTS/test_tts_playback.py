"""Playback: pause не skip'ает chunk; stop рвёт файл и чистит очередь."""
from __future__ import annotations

import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import tts_daemon as daemon


class FakeMusic:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._playing = False
        self._paused = False
        self.tick = 0
        self.length = 8

    def load(self, path: str) -> None:
        self.calls.append(("load", path))

    def set_volume(self, volume: float) -> None:
        self.calls.append(("volume", volume))

    def play(self) -> None:
        self._playing = True
        self._paused = False
        self.tick = 0
        self.calls.append(("play",))

    def pause(self) -> None:
        self._paused = True
        self._playing = False
        self.calls.append(("pause",))

    def unpause(self) -> None:
        self._paused = False
        self._playing = True
        self.calls.append(("unpause",))

    def stop(self) -> None:
        self._playing = False
        self._paused = False
        self.calls.append(("stop",))

    def unload(self) -> None:
        self.calls.append(("unload",))

    def get_busy(self) -> bool:
        if self._paused or not self._playing:
            return False
        self.tick += 1
        if self.tick >= self.length:
            self._playing = False
            return False
        return True


class TestPlaybackPause(unittest.TestCase):
    def setUp(self) -> None:
        daemon._stop_event.clear()
        daemon.set_paused(False)
        daemon.clear_speech_queue()
        self.music = FakeMusic()
        self.mixer = MagicMock()
        self.mixer.music = self.music
        self.time_mod = MagicMock()
        self.time_mod.wait = lambda _ms: time.sleep(0.005)
        self.pygame = MagicMock()
        self.pygame.mixer = self.mixer
        self.pygame.time = self.time_mod

    def tearDown(self) -> None:
        daemon._stop_event.clear()
        daemon.set_paused(False)

    def _audio_file(self) -> Path:
        tmp = __import__("tempfile").NamedTemporaryFile(delete=False)
        path = Path(tmp.name)
        tmp.close()
        path.write_bytes(b"x" * 80)
        return path

    def test_pause_resume_finishes_same_file(self) -> None:
        path = self._audio_file()
        result: dict[str, bool | None] = {"ok": None}

        def run() -> None:
            daemon._mixer_ready = True
            result["ok"] = daemon.play_file(path, 0.5)

        with patch.dict("sys.modules", {"pygame": self.pygame}):
            daemon._mixer_ready = True
            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            time.sleep(0.03)
            daemon.pause_playback()
            time.sleep(0.04)
            names_during = [c[0] for c in self.music.calls]
            self.assertIn("pause", names_during)
            self.assertNotIn("stop", names_during)
            daemon.resume_playback()
            thread.join(timeout=3)
        self.assertFalse(thread.is_alive())
        self.assertTrue(result["ok"])
        self.assertIn("unpause", [c[0] for c in self.music.calls])
        path.unlink(missing_ok=True)

    def test_stop_returns_false_and_calls_stop(self) -> None:
        path = self._audio_file()
        result: dict[str, bool | None] = {"ok": None}

        def run() -> None:
            daemon._mixer_ready = True
            result["ok"] = daemon.play_file(path, 0.5)

        with patch.dict("sys.modules", {"pygame": self.pygame}):
            daemon._mixer_ready = True
            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            time.sleep(0.02)
            daemon.stop_playback()
            thread.join(timeout=3)
        self.assertFalse(result["ok"])
        self.assertIn("stop", [c[0] for c in self.music.calls])
        path.unlink(missing_ok=True)

    def test_stop_clears_queue(self) -> None:
        daemon.enqueue_speech("aaaa")
        daemon.enqueue_speech("bbbb")
        cleared = daemon.clear_speech_queue()
        self.assertGreaterEqual(cleared, 2)
        self.assertEqual(daemon._speech_queue.qsize(), 0)


if __name__ == "__main__":
    unittest.main()
