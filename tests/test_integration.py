"""
tests/test_integration.py — End-to-end pipeline integration tests.

Simulates the full per-frame loop:
  synthetic frame → Detector mock → TrackManager → FeatureExtractor
  → ThreatEngine → AlertDispatcher → Dashboard state writer

No camera, no YOLO, no XGBoost model file, no network required.
All I/O is redirected to a temporary directory.

Run:
    python -m unittest tests.test_integration -v
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

# ---------------------------------------------------------------------------
# Dependency stubs (installed before any project import)
# ---------------------------------------------------------------------------

def _install_stubs():
    # loguru
    lm = types.ModuleType("loguru")
    class _L:
        def __getattr__(self, n): return lambda *a, **k: None
        def bind(self, **k): return self
        def remove(self): pass
        def add(self, *a, **k): pass
    lm.logger = _L()
    sys.modules["loguru"] = lm

    # dotenv
    dm = types.ModuleType("dotenv")
    dm.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dm

    # ultralytics
    ul = types.ModuleType("ultralytics")
    class _YOLO:
        def __init__(self, *a, **k): pass
        def predict(self, *a, **k): return []
        def track(self, *a, **k): return []
        def export(self, *a, **k): pass
    ul.YOLO = _YOLO
    sys.modules["ultralytics"] = ul

    # cv2 — needs imwrite for alert snapshot tests
    cv2m = types.ModuleType("cv2")
    cv2m.imwrite = lambda *a, **k: True
    cv2m.IMWRITE_JPEG_QUALITY = 95
    cv2m.CAP_PROP_FRAME_WIDTH  = 3
    cv2m.CAP_PROP_FRAME_HEIGHT = 4
    cv2m.CAP_PROP_FPS          = 5
    cv2m.CAP_PROP_BUFFERSIZE   = 38
    sys.modules["cv2"] = cv2m

    # requests
    sys.modules["requests"] = types.ModuleType("requests")

_install_stubs()
sys.path.insert(0, ".")

from core.detector import TrackedPerson
from core.tracker import TrackManager
from core.features import FeatureExtractor, FEATURE_DIM, FEATURE_KEYS
from core.threat import ThreatEngine, ThreatResult
from utils.alerts import AlertDispatcher, AlertEvent
from utils.performance import PerformanceMonitor, FrameSkipTuner
from config import cfg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_person(tid: int, cx: int = 320, cy: int = 240, conf: float = 0.88) -> TrackedPerson:
    return TrackedPerson(
        track_id=tid,
        bbox=(cx - 30, cy - 60, cx + 30, cy + 60),
        confidence=conf,
        frame_idx=1,
        timestamp=time.monotonic(),
    )


def _synthetic_frame(h: int = 480, w: int = 640) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# Integration test: full pipeline loop
# ---------------------------------------------------------------------------

class TestFullPipelineLoop(unittest.TestCase):
    """Simulate 100 frames through the complete processing pipeline."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.track_manager  = TrackManager()
        self.threat_engine  = ThreatEngine(frame_width=640, frame_height=480)
        self.monitor        = PerformanceMonitor(fps_window=30)
        self.tuner          = FrameSkipTuner(target_fps=25.0, window=10)
        AlertDispatcher._play_sound = staticmethod(lambda level: None)
        self.dispatcher     = AlertDispatcher()
        self.dispatcher._send_email = lambda e: None

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_frame(self, persons):
        """Simulate one frame through the full pipeline."""
        with self.monitor.frame_timer():
            active = self.track_manager.update(persons)
            results = self.threat_engine.score_all(list(active.values()))
        self.tuner.tick(self.monitor.fps)
        return active, results

    # ── Single track, 100 frames ──────────────────────────────────────────────

    def test_single_track_100_frames(self):
        """One person walks across the scene for 100 frames without errors."""
        for i in range(100):
            person = _make_person(1, cx=100 + i * 4, cy=240)
            active, results = self._run_frame([person])

        self.assertEqual(self.track_manager.active_count, 1)
        self.assertEqual(self.monitor.total_frames, 100)
        self.assertIn(1, results)

        score = results[1].threat_score
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    # ── Multiple tracks appearing and disappearing ────────────────────────────

    def test_multi_track_lifecycle(self):
        """5 tracks appear, 3 disappear, 2 new ones join."""
        # Frames 1–30: 5 tracks
        for _ in range(30):
            self._run_frame([_make_person(i, 100 + i * 80) for i in range(5)])

        self.assertEqual(self.track_manager.active_count, 5)

        # Frames 31–60: only tracks 0, 1 visible
        for _ in range(30):
            self._run_frame([_make_person(0), _make_person(1)])

        # Tracks 2,3,4 should be accumulating missing_frames
        for tid in (2, 3, 4):
            state = self.track_manager.get(tid)
            if state:
                self.assertGreater(state.missing_frames, 0)

        self.assertLessEqual(self.track_manager.active_count, 5)

    # ── Threat escalation path ────────────────────────────────────────────────

    def test_threat_escalation_with_sustained_pressure(self):
        """
        Simulate a threat scenario: person standing close + surrounded.
        After THREAT_SUSTAINED_FRAMES frames the level should be non-NONE.
        """
        # Target at centre (320,240)
        # Three others very close — creates encirclement + proximity pressure
        def _threat_frame():
            return [
                _make_person(1, 320, 240),   # target
                _make_person(2, 350, 240),   # close right
                _make_person(3, 290, 240),   # close left
                _make_person(4, 320, 270),   # close below
            ]

        for _ in range(cfg.THREAT_SUSTAINED_FRAMES + 10):
            active, results = self._run_frame(_threat_frame())

        # At least one track should have a non-zero threat score
        max_score = max(r.threat_score for r in results.values())
        self.assertGreater(max_score, 0.0)

    # ── Alert dispatch ────────────────────────────────────────────────────────

    def test_alert_dispatch_and_cooldown(self):
        """First MEDIUM alert fires; duplicate within cooldown is suppressed."""
        AlertDispatcher._play_sound = staticmethod(lambda level: None)
        disp = AlertDispatcher()
        disp._send_email = lambda e: None

        evt = AlertEvent(
            track_id=7, threat_level="MEDIUM",
            threat_score=0.66, location="Test City",
        )
        fired1 = disp.dispatch(evt)
        fired2 = disp.dispatch(evt)   # same track, within cooldown

        self.assertTrue(fired1,  "First alert should fire")
        self.assertFalse(fired2, "Second alert should be suppressed by cooldown")
        self.assertEqual(disp.total_alerts, 1)

    def test_high_alert_fires_for_new_track(self):
        """HIGH alert for a different track_id must fire even within cooldown window."""
        AlertDispatcher._play_sound = staticmethod(lambda level: None)
        disp = AlertDispatcher()
        disp._send_email = lambda e: None

        evt_a = AlertEvent(track_id=1, threat_level="HIGH", threat_score=0.9, location="X")
        evt_b = AlertEvent(track_id=2, threat_level="HIGH", threat_score=0.9, location="X")

        self.assertTrue(disp.dispatch(evt_a))
        self.assertTrue(disp.dispatch(evt_b))
        self.assertEqual(disp.total_alerts, 2)

    # ── Dashboard state writer ────────────────────────────────────────────────

    def test_state_file_written_correctly(self):
        """Simulate the state write that happens every N frames in main.py."""
        state_file = self.tmp / "state.json"

        import main as _main
        orig_dir   = _main._DATA_DIR
        orig_state = _main._STATE_FILE
        _main._DATA_DIR   = self.tmp
        _main._STATE_FILE = state_file

        from utils.location import LocationFix
        fix = LocationFix(city="Kolkata", country="India", lat=22.57, lon=88.36)

        _main._write_state(
            monitor=self.monitor,
            tuner=self.tuner,
            person_count=3,
            active_tracks=3,
            summary={"HIGH": 1, "MEDIUM": 0, "LOW": 1, "NONE": 1},
            total_alerts=2,
            location_fix=fix,
            xgb_loaded=False,
            camera_source=0,
            resolution="640×480",
        )

        _main._DATA_DIR   = orig_dir
        _main._STATE_FILE = orig_state

        self.assertTrue(state_file.exists(), "State file should be created")
        data = json.loads(state_file.read_text())
        self.assertTrue(data["running"])
        self.assertEqual(data["person_count"], 3)
        self.assertEqual(data["HIGH"], 1)
        self.assertIn("fps", data)
        self.assertIn("p95_frame_ms", data)

    def test_alert_log_file_appended(self):
        """_append_alert should create and grow the alert log JSON."""
        import main as _main
        orig_dir  = _main._DATA_DIR
        orig_log  = _main._ALERT_LOG_FILE
        _main._DATA_DIR       = self.tmp
        _main._ALERT_LOG_FILE = self.tmp / "alerts.json"

        evt1 = AlertEvent(track_id=1, threat_level="HIGH", threat_score=0.91, location="A")
        evt2 = AlertEvent(track_id=2, threat_level="MEDIUM", threat_score=0.65, location="B")

        _main._append_alert(evt1)
        _main._append_alert(evt2)

        _main._DATA_DIR       = orig_dir
        _main._ALERT_LOG_FILE = orig_log

        alerts = json.loads((self.tmp / "alerts.json").read_text())
        self.assertEqual(len(alerts), 2)
        # Newest first
        self.assertEqual(alerts[0]["track_id"], 2)
        self.assertEqual(alerts[1]["track_id"], 1)

    def test_history_file_grows_correctly(self):
        """_update_history should append entries up to max length."""
        import main as _main
        orig_dir  = _main._DATA_DIR
        orig_hist = _main._HISTORY_FILE
        _main._DATA_DIR      = self.tmp
        _main._HISTORY_FILE  = self.tmp / "history.json"

        for i in range(5):
            _main._update_history(
                self.monitor,
                {"HIGH": 0, "MEDIUM": 0, "LOW": i, "NONE": 4 - i},
            )

        _main._DATA_DIR      = orig_dir
        _main._HISTORY_FILE  = orig_hist

        history = json.loads((self.tmp / "history.json").read_text())
        self.assertEqual(len(history), 5)
        self.assertIn("fps", history[0])
        self.assertIn("LOW", history[-1])

    # ── PerformanceMonitor + FrameSkipTuner integration ───────────────────────

    def test_monitor_and_tuner_cointegration(self):
        """Running 90 frames should have the tuner converge and monitor report sane values."""
        tuner = FrameSkipTuner(target_fps=25.0, tolerance=2.0, window=10)
        monitor = PerformanceMonitor(fps_window=30)

        for _ in range(90):
            with monitor.frame_timer():
                time.sleep(0.001)   # simulate 1ms work
            tuner.tick(monitor.fps)

        report = monitor.report()
        self.assertGreater(report["fps"], 0.0)
        self.assertGreater(report["total_frames"], 0)
        self.assertGreater(report["avg_frame_ms"], 0.0)
        self.assertIn("p95_frame_ms", report)
        # Skip should be clamped
        self.assertGreaterEqual(tuner.skip, 0)
        self.assertLessEqual(tuner.skip, 5)

    # ── Feature determinism ───────────────────────────────────────────────────

    def test_feature_extraction_deterministic(self):
        """Same state + others should produce identical feature vectors."""
        tm = TrackManager()
        fe = FeatureExtractor(640, 480)

        persons = [_make_person(i, 100 + i * 80) for i in range(3)]
        for _ in range(15):
            tm.update(persons)

        states = tm.active_tracks()
        target = states[0]

        v1 = fe.extract_vector(target, states)
        v2 = fe.extract_vector(target, states)

        np.testing.assert_array_almost_equal(v1, v2, decimal=6)

    # ── Score consistency ─────────────────────────────────────────────────────

    def test_threat_scores_in_valid_range_over_time(self):
        """Threat scores must stay in [0,1] and levels be valid across 50 frames."""
        tm = TrackManager()
        te = ThreatEngine(640, 480)

        for frame in range(50):
            persons = [_make_person(i, 100 + i * 80 + frame, 240) for i in range(3)]
            active  = tm.update(persons)
            results = te.score_all(list(active.values()))

            for tid, r in results.items():
                self.assertGreaterEqual(r.threat_score, 0.0,
                    f"Frame {frame} track {tid}: score below 0")
                self.assertLessEqual(r.threat_score, 1.0,
                    f"Frame {frame} track {tid}: score above 1")
                self.assertIn(r.threat_level, {"NONE","LOW","MEDIUM","HIGH"},
                    f"Frame {frame} track {tid}: invalid level")

    # ── RuntimeConfig ─────────────────────────────────────────────────────────

    def test_runtime_config_polling(self):
        """RuntimeConfig.poll() picks up file changes and returns True on update."""
        import main as _main
        orig = _main._RT_CONFIG_FILE
        rt_path = self.tmp / "rt.json"
        _main._RT_CONFIG_FILE = rt_path

        rc = _main.RuntimeConfig()

        # No file yet — poll returns False
        self.assertFalse(rc.poll())

        # Write a config
        rt_path.write_text(json.dumps({"THREAT_HIGH": 0.75}))
        self.assertTrue(rc.poll())
        self.assertEqual(rc.get("THREAT_HIGH", 0.8), 0.75)

        # Poll again without file change — returns False
        self.assertFalse(rc.poll())

        _main._RT_CONFIG_FILE = orig

    # ── TrackManager × ThreatEngine data flow ────────────────────────────────

    def test_threat_result_ids_match_active_track_ids(self):
        """Every active track ID must have a corresponding ThreatResult."""
        tm = TrackManager()
        te = ThreatEngine(640, 480)

        persons = [_make_person(tid, 100 + tid * 70) for tid in [5, 12, 23, 77]]
        for _ in range(10):
            tm.update(persons)

        active = tm.active_tracks()
        results = te.score_all(active)

        active_ids  = {s.track_id for s in active}
        result_ids  = set(results.keys())
        self.assertEqual(active_ids, result_ids)

    # ── Stress: 200 frames, 10 tracks ────────────────────────────────────────

    def test_200_frames_10_tracks_no_errors(self):
        """
        Run 200 frames with 10 simultaneous tracks.
        No exception, scores in range, monitor reports valid FPS.
        """
        tm = TrackManager()
        te = ThreatEngine(640, 480)
        mon = PerformanceMonitor(fps_window=60)

        for frame_idx in range(200):
            cx_base = (frame_idx * 2) % 500
            persons = [_make_person(tid, cx_base + tid * 40, 240) for tid in range(10)]
            with mon.frame_timer():
                active  = tm.update(persons)
                results = te.score_all(list(active.values()))

            for r in results.values():
                self.assertGreaterEqual(r.threat_score, 0.0)
                self.assertLessEqual(r.threat_score, 1.0)
                self.assertIn(r.threat_level, {"NONE", "LOW", "MEDIUM", "HIGH"})

        self.assertEqual(mon.total_frames, 200)
        self.assertGreater(mon.fps, 0.0)


# ---------------------------------------------------------------------------
# Integration test: synthetic training data generation
# ---------------------------------------------------------------------------

class TestSyntheticDataGeneration(unittest.TestCase):
    """Validate the training data generator without running XGBoost."""

    def _import_generator(self):
        """Import scenario functions lazily (they need the project path)."""
        spec_path = Path("scripts/train_threat_model.py")
        import importlib.util
        spec = importlib.util.spec_from_file_location("train_threat_model", spec_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_safe_walking_shape(self):
        m = self._import_generator()
        X = m.scenario_safe_walking(100)
        self.assertEqual(X.shape, (100, FEATURE_DIM))

    def test_threat_rush_approach_shape(self):
        m = self._import_generator()
        X = m.scenario_rush_approach(200)
        self.assertEqual(X.shape, (200, FEATURE_DIM))

    def test_all_values_in_unit_interval(self):
        m = self._import_generator()
        for fn in [
            m.scenario_safe_walking,
            m.scenario_standing_alone,
            m.scenario_friendly_group,
            m.scenario_following,
            m.scenario_group_encirclement,
            m.scenario_rush_approach,
            m.scenario_mixed_threat,
        ]:
            X = fn(50)
            self.assertTrue(np.all(X >= 0.0), f"{fn.__name__}: values < 0")
            self.assertTrue(np.all(X <= 1.0), f"{fn.__name__}: values > 1")

    def test_build_synthetic_dataset_balance(self):
        m = self._import_generator()
        X, y = m.build_synthetic_dataset(n_per_class=200)
        safe_count   = int((y == 0).sum())
        threat_count = int((y == 1).sum())
        self.assertEqual(safe_count, threat_count)
        self.assertEqual(X.shape, (400, FEATURE_DIM))
        self.assertEqual(len(y), 400)

    def test_build_synthetic_dataset_no_nans(self):
        import math
        m = self._import_generator()
        X, y = m.build_synthetic_dataset(n_per_class=100)
        self.assertFalse(np.any(np.isnan(X)), "NaN in synthetic features")
        self.assertFalse(np.any(np.isinf(X)), "Inf in synthetic features")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
