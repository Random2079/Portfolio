"""Tests for catalog shuffle index picker."""

from __future__ import annotations

import random
import unittest

from overlay_player import pick_random_playlist_index


class CatalogShuffleTests(unittest.TestCase):
    def test_empty_or_single(self) -> None:
        self.assertEqual(pick_random_playlist_index(0), 0)
        self.assertEqual(pick_random_playlist_index(1, 0), 0)

    def test_avoids_current_when_possible(self) -> None:
        rng = random.Random(0)
        for _ in range(50):
            idx = pick_random_playlist_index(5, current=2, rng=rng)
            self.assertNotEqual(idx, 2)
            self.assertGreaterEqual(idx, 0)
            self.assertLess(idx, 5)

    def test_invalid_current_still_in_range(self) -> None:
        rng = random.Random(1)
        idx = pick_random_playlist_index(3, current=99, rng=rng)
        self.assertIn(idx, (0, 1, 2))


if __name__ == "__main__":
    unittest.main()
