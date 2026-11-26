import tempfile
import unittest
from types import SimpleNamespace
from core.blockchain import (
    Blockchain,
    POW_HARDENING_HEIGHT,
    HARDENED_BASE_DIFFICULTY,
    HARDENED_MIN_DIFFICULTY,
    MAX_DIFFICULTY,
    TARGET_BLOCK_TIME,
)


def _dummy_blocks(count: int, zeros: int = 3, step: float = 20.0, start_ts: float = 1_700_000_000.0):
    h = ("0" * zeros) + ("a" * (64 - zeros))
    return [SimpleNamespace(hash=h, timestamp=start_ts + i * step) for i in range(count)]


class TestPoWDifficultyHardening(unittest.TestCase):
    def test_legacy_height_preserves_historical_difficulty_and_stall_recovery(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            bc = Blockchain(data_dir=tmp, auto_mine=False)
            chain = _dummy_blocks(50, zeros=3, step=TARGET_BLOCK_TIME)
            self.assertEqual(bc.compute_lwma_difficulty(chain, now_ts=chain[-1].timestamp + 5.0), 3)
            self.assertEqual(bc.compute_lwma_difficulty(chain, now_ts=chain[-1].timestamp + 3600.0), 1)

    def test_hardened_height_enforces_base_5_and_stall_floor_4(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            bc = Blockchain(data_dir=tmp, auto_mine=False)
            chain = _dummy_blocks(POW_HARDENING_HEIGHT, zeros=3, step=TARGET_BLOCK_TIME)
            diff_normal = bc.compute_lwma_difficulty(chain, now_ts=chain[-1].timestamp + 10.0)
            self.assertEqual(diff_normal, HARDENED_BASE_DIFFICULTY)
            self.assertEqual(diff_normal, 5)

            # Even after a 10-hour idle gap, stall recovery NEVER drops below HARDENED_MIN_DIFFICULTY (4)
            diff_stalled = bc.compute_lwma_difficulty(chain, now_ts=chain[-1].timestamp + 36000.0)
            self.assertEqual(diff_stalled, HARDENED_MIN_DIFFICULTY)
            self.assertEqual(diff_stalled, 4)

            # Fast blocks push difficulty above 5 up to MAX_DIFFICULTY (8)
            fast_chain = _dummy_blocks(POW_HARDENING_HEIGHT, zeros=5, step=2.0)
            diff_fast = bc.compute_lwma_difficulty(fast_chain, now_ts=fast_chain[-1].timestamp + 2.0)
            self.assertEqual(diff_fast, 6)
            self.assertLessEqual(diff_fast, MAX_DIFFICULTY)


if __name__ == "__main__":
    unittest.main()
