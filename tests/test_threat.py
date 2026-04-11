"""
tests/test_threat.py — Unit tests for core/features.py and core/threat.py.

Run with:
    python -m pytest tests/ -v
    python -m pytest tests/test_threat.py -v --tb=short

These tests are dependency-light:
  - No camera, no YOLO, no XGBoost model file required.
  - All objects are constructed with synthetic data.
  - Tests cover boundary conditions, normalisation, and scoring logic.
"""

from __future__ import annotations

import math
import time
import unittest
from collections import deque
from typing import List

import numpy as np

# ---------------------------------------------------------------------------
# Minimal stubs so tests run without the full package installed
# ---------------------------------------------------------------------------

# Stub config with default values (avoids dotenv / .env dependency in CI)
import sys
import types

# Build a minimal cfg stub if the real one is unavailable
try:
    from config import cfg
except Exception:
    _stub = types.SimpleNamespace(
        CAMERA_WIDTH=640, CAMERA_HEIGHT=480,
        THREAT_LOW=0.35, THREAT_MEDIUM=0.60, THREAT_HIGH=0.80,
        THREAT_SUSTAINED_FRAMES=15, ALERT_COOLDOWN=60,
    )
    sys.modules.setdefault("config", types.ModuleType("config"))
    sys.modules["config"].cfg = _stub
    cfg = _stub

from core.tracker import TrackState
from core.features import FeatureExtractor, FEATURE_KEYS, FEATURE_DIM
from core.threat import ThreatEngine, ThreatResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(
    track_id: int = 1,
    positions: List[tuple] = None,
    threat_level: str = "NONE",
    sustained_count: int = 0,
) -> TrackState:
    """
    Construct a TrackState with a pre-populated history.

    Args:
        positions: List of (cx, cy) tuples. Timestamps are synthesised at
                   33ms intervals (≈ 30 fps).
    """
    state = TrackState(track_id=track_id)
    state.threat_level = threat_level
    state.sustained_count = sustained_count

    positions = positions or [(320, 240)]
    t0 = time.monotonic()
    for i, (cx, cy) in enumerate(positions):
        ts = t0 + i * 0.033
        state.history.append((float(cx), float(cy), ts))
        state.confidences.append(0.85)
        state.bboxes.append((int(cx - 30), int(cy - 60), int(cx + 30), int(cy + 60)))

    state.last_seen = t0 + (len(positions) - 1) * 0.033
    return state


# ---------------------------------------------------------------------------
# FeatureExtractor tests
# ---------------------------------------------------------------------------

class TestFeatureExtractor(unittest.TestCase):

    def setUp(self):
        self.fe = FeatureExtractor(frame_width=640, frame_height=480)

    # ── Vector shape & completeness ───────────────────────────────────────────

    def test_feature_vector_length(self):
        """Extracted vector must have exactly FEATURE_DIM elements."""
        state = _make_state(positions=[(100, 100)] * 10)
        vec = self.fe.extract_vector(state, [state])
        self.assertEqual(vec.shape, (FEATURE_DIM,))

    def test_feature_keys_match_dim(self):
        """FEATURE_KEYS list length must equal FEATURE_DIM constant."""
        self.assertEqual(len(FEATURE_KEYS), FEATURE_DIM)

    def test_all_features_finite(self):
        """No feature should be NaN or Inf."""
        state = _make_state(positions=[(x * 10, 240) for x in range(20)])
        others = [_make_state(2, [(200, 300)] * 20)]
        feat = self.fe.extract(state, [state] + others)
        for k, v in feat.items():
            self.assertTrue(math.isfinite(v), f"Feature '{k}' is not finite: {v}")

    def test_to_vector_missing_keys_default_zero(self):
        """to_vector should default missing keys to 0.0, not raise."""
        vec = self.fe.to_vector({"speed_px_s": 5.0})  # most keys missing
        self.assertEqual(vec.shape[0], FEATURE_DIM)
        self.assertEqual(float(vec[FEATURE_KEYS.index("speed_px_s")]), 5.0)
        # All other keys should be 0.0
        for i, k in enumerate(FEATURE_KEYS):
            if k != "speed_px_s":
                self.assertEqual(float(vec[i]), 0.0, f"Expected 0 for '{k}'")

    # ── Speed ─────────────────────────────────────────────────────────────────

    def test_stationary_person_speed_near_zero(self):
        """A person who doesn't move should have speed ≈ 0."""
        state = _make_state(positions=[(320, 240)] * 20)
        feat = self.fe.extract(state, [state])
        self.assertAlmostEqual(feat["speed_px_s"], 0.0, places=2)

    def test_moving_person_speed_positive(self):
        """A person moving right at 10px/frame ≈ 303 px/s at 30fps."""
        positions = [(10 * i, 240) for i in range(20)]
        state = _make_state(positions=positions)
        feat = self.fe.extract(state, [state])
        # Speed should be clearly above 0
        self.assertGreater(feat["speed_px_s"], 50.0)

    def test_speed_norm_bounded(self):
        """Normalised speed must stay in [0, 1]."""
        positions = [(i * 100, 240) for i in range(20)]  # very fast movement
        state = _make_state(positions=positions)
        feat = self.fe.extract(state, [state])
        self.assertGreaterEqual(feat["speed_norm"], 0.0)
        self.assertLessEqual(feat["speed_norm"], 1.0)

    # ── Proximity ─────────────────────────────────────────────────────────────

    def test_no_neighbours_max_proximity(self):
        """With no other tracks, proximity_norm should equal 1.0."""
        state = _make_state()
        feat = self.fe.extract(state, [state])  # only self
        self.assertAlmostEqual(feat["proximity_norm"], 1.0, places=5)

    def test_close_neighbour_low_proximity_norm(self):
        """A neighbour 50px away should yield low proximity_norm."""
        target = _make_state(1, [(320, 240)] * 5)
        neighbour = _make_state(2, [(370, 240)] * 5)   # 50 px away
        feat = self.fe.extract(target, [target, neighbour])
        self.assertLess(feat["proximity_norm"], 0.1)

    def test_distant_neighbour_high_proximity_norm(self):
        """A neighbour at the far edge should yield high proximity_norm."""
        target = _make_state(1, [(0, 0)] * 5)
        neighbour = _make_state(2, [(639, 479)] * 5)
        feat = self.fe.extract(target, [target, neighbour])
        self.assertGreater(feat["proximity_norm"], 0.9)

    # ── Encirclement ──────────────────────────────────────────────────────────

    def test_no_neighbours_zero_encirclement(self):
        state = _make_state()
        feat = self.fe.extract(state, [state])
        self.assertAlmostEqual(feat["encirclement_score"], 0.0, places=5)

    def test_perfectly_encircled(self):
        """
        4 persons at N/E/S/W at 100px should give encirclement ≈ 1.0.
        (largest gap = 90° = π/2, so score = 1 − (π/2)/(2π) = 0.75)
        """
        target = _make_state(1, [(320, 240)] * 5)
        n = _make_state(2, [(320, 140)] * 5)   # North
        e = _make_state(3, [(420, 240)] * 5)   # East
        s = _make_state(4, [(320, 340)] * 5)   # South
        w = _make_state(5, [(220, 240)] * 5)   # West
        feat = self.fe.extract(target, [target, n, e, s, w])
        self.assertGreater(feat["encirclement_score"], 0.70)

    def test_one_sided_group_low_encirclement(self):
        """All neighbours on the same side → low encirclement."""
        target = _make_state(1, [(320, 240)] * 5)
        # All neighbours slightly to the right
        others = [_make_state(i + 2, [(350 + i * 10, 240)] * 5) for i in range(4)]
        feat = self.fe.extract(target, [target] + others)
        self.assertLess(feat["encirclement_score"], 0.5)

    # ── Isolation ─────────────────────────────────────────────────────────────

    def test_isolated_person_isolation_one(self):
        """Person alone (surrounding_count=0) → isolation_score=1.0."""
        state = _make_state()
        feat = self.fe.extract(state, [state])
        self.assertAlmostEqual(feat["isolation_score"], 1.0, places=5)

    def test_surrounded_person_low_isolation(self):
        """Person with 4 close neighbours → isolation drops."""
        target = _make_state(1, [(320, 240)] * 5)
        others = [_make_state(i + 2, [(320 + 30 * i, 240)] * 5) for i in range(4)]
        feat = self.fe.extract(target, [target] + others)
        self.assertLess(feat["isolation_score"], 0.5)

    # ── Direction change ──────────────────────────────────────────────────────

    def test_straight_path_low_direction_change(self):
        """Perfectly straight movement → direction_change ≈ 0."""
        positions = [(i * 5, 240) for i in range(20)]  # purely horizontal
        state = _make_state(positions=positions)
        feat = self.fe.extract(state, [state])
        self.assertLess(feat["direction_change"], 0.05)

    def test_zigzag_path_high_direction_change(self):
        """Sharp alternating turns → high direction_change."""
        positions = [(320 + ((-1) ** i) * 80, 240 + i * 5) for i in range(20)]
        state = _make_state(positions=positions)
        feat = self.fe.extract(state, [state])
        self.assertGreater(feat["direction_change"], 0.3)


# ---------------------------------------------------------------------------
# ThreatEngine tests
# ---------------------------------------------------------------------------

class TestThreatEngine(unittest.TestCase):

    def setUp(self):
        self.engine = ThreatEngine(frame_width=640, frame_height=480)

    def _score(self, target: TrackState, others: List[TrackState] = None) -> ThreatResult:
        all_states = [target] + (others or [])
        results = self.engine.score_all(all_states)
        return results[target.track_id]

    # ── Score bounds ──────────────────────────────────────────────────────────

    def test_score_in_unit_interval(self):
        """Composite threat score must always be in [0, 1]."""
        state = _make_state(positions=[(320, 240)] * 10)
        result = self._score(state)
        self.assertGreaterEqual(result.threat_score, 0.0)
        self.assertLessEqual(result.threat_score, 1.0)

    def test_score_all_returns_all_ids(self):
        """score_all must return one result per input track."""
        states = [_make_state(i, [(i * 50, 240)] * 10) for i in range(5)]
        results = self.engine.score_all(states)
        self.assertEqual(set(results.keys()), {s.track_id for s in states})

    # ── Threat levels ─────────────────────────────────────────────────────────

    def test_lone_stationary_person_none_or_low(self):
        """A single stationary person should score NONE or LOW."""
        state = _make_state(positions=[(320, 240)] * 30)
        result = self._score(state)
        self.assertIn(result.threat_level, {"NONE", "LOW"})

    def test_threshold_boundaries(self):
        """_score_to_level must respect configured thresholds exactly."""
        levels = [
            (cfg.THREAT_HIGH,        "HIGH"),
            (cfg.THREAT_MEDIUM,      "MEDIUM"),
            (cfg.THREAT_LOW,         "LOW"),
            (cfg.THREAT_LOW - 0.01,  "NONE"),
        ]
        for score, expected in levels:
            actual = self.engine._score_to_level(score)
            self.assertEqual(
                actual, expected,
                f"Score {score:.3f} → expected {expected}, got {actual}",
            )

    # ── Sustained gating ──────────────────────────────────────────────────────

    def test_promotion_requires_sustained_frames(self):
        """
        A NEW high-threat state (sustained_count < THRESHOLD) should NOT
        immediately promote to HIGH — it should cap at MEDIUM.
        """
        state = _make_state(threat_level="NONE", sustained_count=0)
        # Force a high raw level
        result = self.engine._apply_sustained_gating(state, "HIGH")
        # With sustained_count=0 < THRESHOLD, should be capped at "MEDIUM"
        self.assertEqual(result, "MEDIUM")

    def test_promotion_fires_after_sustained_threshold(self):
        """After sustained_count ≥ threshold, promotion to HIGH should happen."""
        state = _make_state(
            threat_level="MEDIUM",
            sustained_count=cfg.THREAT_SUSTAINED_FRAMES,
        )
        result = self.engine._apply_sustained_gating(state, "HIGH")
        self.assertEqual(result, "HIGH")

    def test_demotion_is_immediate(self):
        """Going from HIGH → NONE must happen without sustained gating."""
        state = _make_state(threat_level="HIGH", sustained_count=0)
        result = self.engine._apply_sustained_gating(state, "NONE")
        self.assertEqual(result, "NONE")

    # ── Heuristic sanity checks ───────────────────────────────────────────────

    def test_heuristic_score_bounded(self):
        """Heuristic must return a value in [0, 1]."""
        feat = {k: 0.5 for k in FEATURE_KEYS}
        target = _make_state(1, [(320, 240)] * 10)
        other = _make_state(2, [(350, 240)] * 10)
        score = self.engine._heuristic_score(feat, target, [target, other])
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_heuristic_all_zero_features_low_score(self):
        """All-zero features (no threat signals) → near-zero heuristic."""
        feat = {k: 0.0 for k in FEATURE_KEYS}
        # isolation_score=0 and proximity_norm=0 would indicate max prox,
        # so reset those to benign values
        feat["proximity_norm"] = 1.0      # far away
        feat["isolation_score"] = 1.0     # alone
        target = _make_state(1, [(320, 240)] * 10)
        score = self.engine._heuristic_score(feat, target, [target])
        self.assertLess(score, 0.15)

    def test_heuristic_max_threat_signals_high_score(self):
        """All threat signals maxed → heuristic score should be high."""
        feat = {k: 1.0 for k in FEATURE_KEYS}
        feat["proximity_norm"] = 0.0      # very close
        feat["isolation_score"] = 0.0     # surrounded
        feat["velocity_toward_target"] = 1.0
        target = _make_state(1, [(320, 240)] * 10)
        other = _make_state(2, [(350, 240)] * 10)
        score = self.engine._heuristic_score(feat, target, [target, other])
        self.assertGreater(score, 0.50)

    # ── Color map ─────────────────────────────────────────────────────────────

    def test_build_color_map_returns_bgr_tuples(self):
        """build_color_map should return 3-element BGR tuples for each ID."""
        states = [_make_state(i) for i in range(3)]
        results = self.engine.score_all(states)
        color_map = ThreatEngine.build_color_map(results)
        self.assertEqual(set(color_map.keys()), {s.track_id for s in states})
        for tid, color in color_map.items():
            self.assertEqual(len(color), 3, f"Track {tid} color not 3-tuple")
            for ch in color:
                self.assertGreaterEqual(ch, 0)
                self.assertLessEqual(ch, 255)

    # ── Summarise ─────────────────────────────────────────────────────────────

    def test_summarise_counts_correct(self):
        """summarise() should count tracks at each level correctly."""
        # Manually construct results with known levels
        def _make_result(tid, level):
            return ThreatResult(
                track_id=tid, threat_level=level, threat_score=0.5,
                xgb_score=-1.0, heuristic_score=0.5,
                features={}, sustained_frames=0,
            )
        results = {
            1: _make_result(1, "HIGH"),
            2: _make_result(2, "HIGH"),
            3: _make_result(3, "MEDIUM"),
            4: _make_result(4, "NONE"),
        }
        summary = ThreatEngine.summarise(results)
        self.assertEqual(summary["HIGH"],   2)
        self.assertEqual(summary["MEDIUM"], 1)
        self.assertEqual(summary["NONE"],   1)
        self.assertEqual(summary["LOW"],    0)


# ---------------------------------------------------------------------------
# TrackState tests
# ---------------------------------------------------------------------------

class TestTrackState(unittest.TestCase):

    def test_center_returns_latest_position(self):
        state = _make_state(positions=[(100, 200), (110, 210), (120, 220)])
        self.assertEqual(state.center, (120.0, 220.0))

    def test_center_none_when_no_history(self):
        state = TrackState(track_id=99)
        self.assertIsNone(state.center)

    def test_centers_array_shape(self):
        positions = [(i * 10, 240) for i in range(15)]
        state = _make_state(positions=positions)
        arr = state.centers_array
        self.assertEqual(arr.shape, (15, 2))

    def test_is_stale_after_max_missing(self):
        """Track marked missing 45+ times should be flagged as stale."""
        state = TrackState(track_id=1)
        for _ in range(45):
            state.mark_missing()
        self.assertTrue(state.is_stale)

    def test_is_not_stale_below_threshold(self):
        state = TrackState(track_id=2)
        for _ in range(10):
            state.mark_missing()
        self.assertFalse(state.is_stale)

    def test_age_seconds_increases(self):
        """age_seconds should grow as last_seen advances."""
        state = TrackState(track_id=3)
        state.first_seen = time.monotonic() - 5.0
        state.last_seen  = time.monotonic()
        self.assertGreater(state.age_seconds, 4.9)

    def test_alert_cooldown_reset(self):
        """alert_sent should clear after ALERT_COOLDOWN seconds."""
        state = TrackState(track_id=4)
        state.alert_sent = True
        # Backdate alert to well beyond cooldown
        state.alert_sent_at = time.monotonic() - (cfg.ALERT_COOLDOWN + 5)
        state.reset_alert_if_cooled()
        self.assertFalse(state.alert_sent)

    def test_alert_not_reset_within_cooldown(self):
        state = TrackState(track_id=5)
        state.alert_sent = True
        state.alert_sent_at = time.monotonic()   # just now
        state.reset_alert_if_cooled()
        self.assertTrue(state.alert_sent)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
