"""
tests/test_tracker.py — Unit and integration tests for core/tracker.py.

Covers:
  - TrackManager: create, update, missing-frame counting, stale pruning
  - TrackState: history growth, center property, missing/stale logic
  - Multi-frame sequences with appearing/disappearing tracks
  - Edge cases: empty frame, single track, 50+ simultaneous tracks
"""

from __future__ import annotations

import sys
import time
import types
import unittest

# ── Minimal stubs ─────────────────────────────────────────────────────────────
lm = types.ModuleType("loguru")
class _L:
    def __getattr__(self, n): return lambda *a, **k: None
    def bind(self, **k): return self
    def remove(self): pass
    def add(self, *a, **k): pass
lm.logger = _L()
sys.modules["loguru"] = lm

dm = types.ModuleType("dotenv")
dm.load_dotenv = lambda *a, **k: None
sys.modules["dotenv"] = dm

ul = types.ModuleType("ultralytics")
class _YOLO:
    def __init__(self, *a, **k): pass
ul.YOLO = _YOLO
sys.modules["ultralytics"] = ul
sys.modules["cv2"] = types.ModuleType("cv2")

sys.path.insert(0, ".")

from core.tracker import TrackState, TrackManager, _MAX_MISSING_FRAMES
from core.detector import TrackedPerson


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _person(tid: int, cx: int = 320, cy: int = 240) -> TrackedPerson:
    """Construct a minimal TrackedPerson for testing."""
    return TrackedPerson(
        track_id=tid,
        bbox=(cx - 30, cy - 60, cx + 30, cy + 60),
        confidence=0.88,
        frame_idx=1,
        timestamp=time.monotonic(),
    )


def _update_n(manager: TrackManager, persons, n: int):
    """Call manager.update(persons) n times in a loop."""
    for _ in range(n):
        manager.update(persons)


# ---------------------------------------------------------------------------
# TrackState tests
# ---------------------------------------------------------------------------

class TestTrackState(unittest.TestCase):

    def test_initial_state_clean(self):
        s = TrackState(track_id=1)
        self.assertEqual(s.track_id, 1)
        self.assertEqual(s.missing_frames, 0)
        self.assertEqual(s.threat_level, "NONE")
        self.assertEqual(s.threat_score, 0.0)
        self.assertFalse(s.alert_sent)
        self.assertIsNone(s.center)

    def test_update_appends_history(self):
        s = TrackState(track_id=1)
        s.update(_person(1, 100, 200))
        s.update(_person(1, 110, 205))
        self.assertEqual(len(s.history), 2)
        cx, cy = s.center
        self.assertAlmostEqual(cx, 110.0)
        self.assertAlmostEqual(cy, 205.0)

    def test_missing_frames_reset_on_update(self):
        s = TrackState(track_id=1)
        for _ in range(10):
            s.mark_missing()
        self.assertEqual(s.missing_frames, 10)
        s.update(_person(1))
        self.assertEqual(s.missing_frames, 0)

    def test_mark_missing_increments_counter(self):
        s = TrackState(track_id=1)
        for i in range(1, 6):
            s.mark_missing()
            self.assertEqual(s.missing_frames, i)

    def test_is_stale_exactly_at_threshold(self):
        s = TrackState(track_id=1)
        for _ in range(_MAX_MISSING_FRAMES - 1):
            s.mark_missing()
        self.assertFalse(s.is_stale)
        s.mark_missing()
        self.assertTrue(s.is_stale)

    def test_centers_array_shape_and_values(self):
        import numpy as np
        s = TrackState(track_id=1)
        positions = [(100 + i * 5, 240) for i in range(10)]
        t0 = time.monotonic()
        for i, (cx, cy) in enumerate(positions):
            s.history.append((float(cx), float(cy), t0 + i * 0.033))
        arr = s.centers_array
        self.assertEqual(arr.shape, (10, 2))
        self.assertAlmostEqual(arr[0, 0], 100.0)
        self.assertAlmostEqual(arr[-1, 0], 145.0)

    def test_timestamps_array_monotonic(self):
        import numpy as np
        s = TrackState(track_id=1)
        t0 = time.monotonic()
        for i in range(5):
            s.history.append((320.0, 240.0, t0 + i * 0.033))
        ts = s.timestamps_array
        self.assertEqual(ts.shape, (5,))
        # Must be strictly increasing
        self.assertTrue(all(ts[i] < ts[i+1] for i in range(len(ts)-1)))

    def test_age_seconds_positive(self):
        s = TrackState(track_id=1)
        s.first_seen = time.monotonic() - 2.0
        s.last_seen  = time.monotonic()
        self.assertGreater(s.age_seconds, 1.9)

    def test_area_and_height_from_person(self):
        p = _person(1, 320, 240)   # bbox (290,180,350,300) → 60×120
        s = TrackState(track_id=1)
        s.update(p)
        # After update, check that bboxes deque holds the bbox
        self.assertEqual(len(s.bboxes), 1)
        x1, y1, x2, y2 = s.bboxes[0]
        self.assertEqual(x2 - x1, 60)
        self.assertEqual(y2 - y1, 120)

    def test_history_maxlen_respected(self):
        """History deque should not grow beyond 60 entries."""
        from core.tracker import _HISTORY_LEN
        s = TrackState(track_id=1)
        for i in range(_HISTORY_LEN + 20):
            s.update(_person(1, i, 240))
        self.assertLessEqual(len(s.history), _HISTORY_LEN)

    def test_alert_cooldown_reset(self):
        from config import cfg
        s = TrackState(track_id=1)
        s.alert_sent    = True
        s.alert_sent_at = time.monotonic() - (cfg.ALERT_COOLDOWN + 5)
        s.reset_alert_if_cooled()
        self.assertFalse(s.alert_sent)

    def test_alert_not_reset_within_cooldown(self):
        s = TrackState(track_id=1)
        s.alert_sent    = True
        s.alert_sent_at = time.monotonic()
        s.reset_alert_if_cooled()
        self.assertTrue(s.alert_sent)


# ---------------------------------------------------------------------------
# TrackManager tests
# ---------------------------------------------------------------------------

class TestTrackManager(unittest.TestCase):

    def setUp(self):
        self.tm = TrackManager()

    # ── Creation ──────────────────────────────────────────────────────────────

    def test_empty_update_returns_empty(self):
        result = self.tm.update([])
        self.assertEqual(len(result), 0)

    def test_new_track_created_on_first_appearance(self):
        self.tm.update([_person(1)])
        self.assertIn(1, self.tm._tracks)

    def test_multiple_new_tracks_created(self):
        persons = [_person(i) for i in range(5)]
        self.tm.update(persons)
        self.assertEqual(self.tm.active_count, 5)

    def test_total_tracks_seen_cumulative(self):
        """total_tracks_seen counts all IDs ever seen, not just current."""
        self.tm.update([_person(1), _person(2)])
        # Let track 2 go stale (missing for max frames)
        for _ in range(_MAX_MISSING_FRAMES):
            self.tm.update([_person(1)])
        # Track 2 pruned but total_tracks_seen still 2
        self.assertEqual(self.tm.total_tracks_seen, 2)

    # ── Update / persistence ──────────────────────────────────────────────────

    def test_existing_track_history_grows(self):
        for i in range(5):
            self.tm.update([_person(1, 320 + i * 10, 240)])
        state = self.tm.get(1)
        self.assertIsNotNone(state)
        self.assertEqual(len(state.history), 5)

    def test_track_id_persists_across_frames(self):
        for _ in range(10):
            self.tm.update([_person(42)])
        self.assertIn(42, self.tm._tracks)
        self.assertEqual(self.tm._tracks[42].missing_frames, 0)

    # ── Missing / stale ───────────────────────────────────────────────────────

    def test_missing_frames_increase_when_absent(self):
        self.tm.update([_person(1)])
        # Next frames: only person 2 visible
        for _ in range(5):
            self.tm.update([_person(2)])
        self.assertEqual(self.tm._tracks[1].missing_frames, 5)

    def test_stale_track_pruned_after_max_missing(self):
        self.tm.update([_person(1)])
        for _ in range(_MAX_MISSING_FRAMES):
            self.tm.update([])   # empty frame — track 1 accumulates missing frames
        self.assertNotIn(1, self.tm._tracks)

    def test_track_recovers_after_reappearance(self):
        self.tm.update([_person(1)])
        for _ in range(5):
            self.tm.update([])
        self.assertEqual(self.tm._tracks[1].missing_frames, 5)
        # Track reappears before stale threshold
        self.tm.update([_person(1)])
        self.assertEqual(self.tm._tracks[1].missing_frames, 0)

    # ── active_tracks() ───────────────────────────────────────────────────────

    def test_active_tracks_list_length(self):
        persons = [_person(i) for i in range(10)]
        self.tm.update(persons)
        self.assertEqual(len(self.tm.active_tracks()), 10)

    def test_active_tracks_returns_list_not_dict(self):
        self.tm.update([_person(1)])
        result = self.tm.active_tracks()
        self.assertIsInstance(result, list)

    # ── get() ─────────────────────────────────────────────────────────────────

    def test_get_existing_returns_state(self):
        self.tm.update([_person(7)])
        state = self.tm.get(7)
        self.assertIsNotNone(state)
        self.assertEqual(state.track_id, 7)

    def test_get_missing_returns_none(self):
        result = self.tm.get(9999)
        self.assertIsNone(result)

    # ── reset() ───────────────────────────────────────────────────────────────

    def test_reset_clears_all_tracks(self):
        self.tm.update([_person(i) for i in range(5)])
        self.tm.reset()
        self.assertEqual(self.tm.active_count, 0)

    # ── Stress: many tracks ───────────────────────────────────────────────────

    def test_fifty_simultaneous_tracks(self):
        """Manager should handle 50 tracks without errors."""
        persons = [_person(i, 10 * i, 240) for i in range(50)]
        self.tm.update(persons)
        self.assertEqual(self.tm.active_count, 50)
        # Run 10 more frames keeping all tracks
        for _ in range(10):
            self.tm.update(persons)
        self.assertEqual(self.tm.active_count, 50)

    def test_tracks_disappear_and_new_ones_appear(self):
        """Simulates a dynamic crowd: some leave, some enter each frame."""
        # Frame 1: tracks 0–9
        self.tm.update([_person(i) for i in range(10)])
        # Frames 2–50: tracks 5–14 (5 overlap, 5 new, 5 disappear)
        for _ in range(_MAX_MISSING_FRAMES):
            self.tm.update([_person(i) for i in range(5, 15)])
        # Original tracks 0–4 should be pruned; 5–14 should remain
        for i in range(5):
            self.assertNotIn(i, self.tm._tracks, f"Track {i} should be pruned")
        for i in range(5, 15):
            self.assertIn(i, self.tm._tracks, f"Track {i} should be active")

    # ── Frame counter ─────────────────────────────────────────────────────────

    def test_frame_count_increments(self):
        for i in range(7):
            self.tm.update([_person(1)])
        self.assertEqual(self.tm.frame_count, 7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
