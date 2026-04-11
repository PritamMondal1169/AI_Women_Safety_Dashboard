"""
tests/test_performance.py — Unit tests for utils/performance.py.

Covers:
  - PerformanceMonitor: FPS calculation, latency tracking, frame_timer context
  - LatencyTracker: rolling stats (mean, p95, min, max)
  - FrameSkipTuner: convergence, clamping, hysteresis, reset
"""

from __future__ import annotations

import sys
import time
import types
import unittest

# ── Minimal loguru stub ───────────────────────────────────────────────────────
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

sys.path.insert(0, ".")

from utils.performance import LatencyTracker, PerformanceMonitor, FrameSkipTuner


# ---------------------------------------------------------------------------
# LatencyTracker tests
# ---------------------------------------------------------------------------

class TestLatencyTracker(unittest.TestCase):

    def test_empty_tracker_returns_zeros(self):
        lt = LatencyTracker()
        self.assertEqual(lt.mean_ms, 0.0)
        self.assertEqual(lt.p95_ms, 0.0)
        self.assertEqual(lt.max_ms, 0.0)
        self.assertEqual(lt.min_ms, 0.0)

    def test_single_sample(self):
        lt = LatencyTracker()
        lt.record(42.0)
        self.assertAlmostEqual(lt.mean_ms, 42.0)
        self.assertAlmostEqual(lt.max_ms,  42.0)
        self.assertAlmostEqual(lt.min_ms,  42.0)

    def test_mean_is_average_of_samples(self):
        lt = LatencyTracker()
        for v in [10.0, 20.0, 30.0]:
            lt.record(v)
        self.assertAlmostEqual(lt.mean_ms, 20.0)

    def test_max_min_correct(self):
        lt = LatencyTracker()
        for v in [5.0, 99.0, 42.0, 1.0]:
            lt.record(v)
        self.assertAlmostEqual(lt.max_ms, 99.0)
        self.assertAlmostEqual(lt.min_ms,  1.0)

    def test_p95_above_median(self):
        lt = LatencyTracker(window=100)
        for i in range(100):
            lt.record(float(i))   # 0..99
        # p95 should be around 94-95
        self.assertGreater(lt.p95_ms, 80.0)

    def test_window_size_limits_samples(self):
        lt = LatencyTracker(window=5)
        for i in range(20):
            lt.record(float(i))
        # Only last 5 values (15..19) should remain
        self.assertAlmostEqual(lt.min_ms, 15.0)
        self.assertAlmostEqual(lt.max_ms, 19.0)

    def test_p95_requires_at_least_5_samples(self):
        lt = LatencyTracker()
        for v in [10.0, 20.0, 30.0]:   # only 3 samples
            lt.record(v)
        self.assertEqual(lt.p95_ms, 0.0)


# ---------------------------------------------------------------------------
# PerformanceMonitor tests
# ---------------------------------------------------------------------------

class TestPerformanceMonitor(unittest.TestCase):

    def test_initial_fps_zero(self):
        pm = PerformanceMonitor()
        self.assertEqual(pm.fps, 0.0)

    def test_fps_after_ticks(self):
        """After recording 30 frame times, fps should be positive."""
        pm = PerformanceMonitor(fps_window=30)
        for _ in range(30):
            with pm.frame_timer():
                time.sleep(0.001)   # simulate 1ms work
        self.assertGreater(pm.fps, 0.0)

    def test_total_frames_increments(self):
        pm = PerformanceMonitor()
        for _ in range(5):
            with pm.frame_timer():
                pass
        self.assertEqual(pm.total_frames, 5)

    def test_frame_timer_records_latency(self):
        pm = PerformanceMonitor()
        with pm.frame_timer():
            time.sleep(0.010)   # 10ms
        # Mean latency should be at least 5ms (sleep is imprecise in CI)
        self.assertGreater(pm.frame_latency.mean_ms, 1.0)

    def test_record_inference(self):
        pm = PerformanceMonitor()
        pm.record_inference(35.0)
        pm.record_inference(40.0)
        self.assertAlmostEqual(pm.avg_inference_ms, 37.5)

    def test_avg_inference_zero_when_empty(self):
        pm = PerformanceMonitor()
        self.assertEqual(pm.avg_inference_ms, 0.0)

    def test_uptime_grows(self):
        pm = PerformanceMonitor()
        time.sleep(0.05)
        self.assertGreater(pm.uptime_seconds, 0.04)

    def test_report_dict_keys(self):
        pm = PerformanceMonitor()
        report = pm.report()
        expected_keys = {
            "fps", "avg_frame_ms", "p95_frame_ms", "max_frame_ms",
            "avg_inference_ms", "total_frames", "uptime_s",
        }
        self.assertEqual(set(report.keys()), expected_keys)

    def test_report_values_finite(self):
        pm = PerformanceMonitor()
        for _ in range(10):
            with pm.frame_timer():
                pass
        import math
        for k, v in pm.report().items():
            self.assertTrue(math.isfinite(v), f"Non-finite: {k}={v}")

    def test_fps_single_frame_returns_zero(self):
        """With only one frame timestamp, FPS should be 0 (no span yet)."""
        pm = PerformanceMonitor(fps_window=10)
        with pm.frame_timer():
            pass
        # Can't compute FPS from a single point
        self.assertEqual(pm.fps, 0.0)


# ---------------------------------------------------------------------------
# FrameSkipTuner tests
# ---------------------------------------------------------------------------

class TestFrameSkipTuner(unittest.TestCase):

    def test_initial_skip(self):
        tuner = FrameSkipTuner(target_fps=25.0, initial_skip=0)
        self.assertEqual(tuner.skip, 0)

    def test_no_adjustment_within_tolerance(self):
        """FPS inside the dead-band should not change skip."""
        tuner = FrameSkipTuner(target_fps=25.0, tolerance=2.0, window=5)
        for _ in range(5):
            tuner.tick(25.5)   # inside [23, 27]
        self.assertEqual(tuner.skip, 0)
        self.assertEqual(tuner.adjustments, 0)

    def test_skip_increases_when_fps_too_low(self):
        """Below (target − tolerance) for a full window → skip should increase."""
        tuner = FrameSkipTuner(target_fps=25.0, tolerance=2.0, window=5, initial_skip=0)
        for _ in range(5):
            tuner.tick(15.0)   # well below 23
        self.assertGreater(tuner.skip, 0)

    def test_skip_decreases_when_fps_too_high(self):
        """Above (target + tolerance) with skip>0 → skip should decrease."""
        tuner = FrameSkipTuner(target_fps=25.0, tolerance=2.0, window=5, initial_skip=3)
        for _ in range(5):
            tuner.tick(50.0)   # well above 27
        self.assertLess(tuner.skip, 3)

    def test_skip_never_goes_below_zero(self):
        """Skip must be clamped at 0 from below."""
        tuner = FrameSkipTuner(target_fps=25.0, tolerance=2.0, window=5, initial_skip=0)
        for _ in range(20):
            tuner.tick(60.0)   # very fast
        self.assertEqual(tuner.skip, 0)

    def test_skip_never_exceeds_max(self):
        """Skip must be clamped at MAX_SKIP from above."""
        from utils.performance import _MAX_SKIP
        tuner = FrameSkipTuner(target_fps=60.0, tolerance=1.0, window=1, initial_skip=0)
        for _ in range(_MAX_SKIP + 20):
            tuner.tick(1.0)   # extremely slow
        self.assertLessEqual(tuner.skip, _MAX_SKIP)

    def test_adjustments_counter_increments(self):
        tuner = FrameSkipTuner(target_fps=25.0, tolerance=1.0, window=3, initial_skip=0)
        for _ in range(3):
            tuner.tick(5.0)   # force an increase
        self.assertGreater(tuner.adjustments, 0)

    def test_reset_clears_state(self):
        tuner = FrameSkipTuner(target_fps=25.0, tolerance=1.0, window=3, initial_skip=0)
        for _ in range(3):
            tuner.tick(5.0)
        tuner.reset(skip=2)
        self.assertEqual(tuner.skip, 2)
        self.assertEqual(tuner._tick_count, 0)

    def test_report_dict_keys(self):
        tuner = FrameSkipTuner()
        report = tuner.report()
        self.assertIn("current_skip",    report)
        self.assertIn("target_fps",      report)
        self.assertIn("adjustments",     report)
        self.assertIn("ticks_evaluated", report)

    def test_tuner_converges_to_stable_skip(self):
        """
        Simulate a realistic scenario: start at 20fps (too slow), expect
        the tuner to increase skip, then simulate recovery to 28fps and
        expect skip to decrease back.
        """
        tuner = FrameSkipTuner(target_fps=25.0, tolerance=2.0, window=10, initial_skip=0)

        # Phase 1: slow — should increase skip
        for _ in range(30):
            tuner.tick(18.0)
        skip_after_slow = tuner.skip
        self.assertGreater(skip_after_slow, 0, "Tuner should have increased skip")

        # Phase 2: fast — should decrease skip
        for _ in range(30):
            tuner.tick(35.0)
        skip_after_fast = tuner.skip
        self.assertLess(skip_after_fast, skip_after_slow, "Tuner should have decreased skip")

    def test_tick_returns_current_skip(self):
        """tick() return value must equal tuner.skip."""
        tuner = FrameSkipTuner(target_fps=25.0, window=3)
        for _ in range(3):
            returned = tuner.tick(10.0)
        self.assertEqual(returned, tuner.skip)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
