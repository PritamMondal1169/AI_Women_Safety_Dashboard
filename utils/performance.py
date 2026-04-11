"""
utils/performance.py — Real-time performance monitoring and auto-tuner.

Two responsibilities:

1. PerformanceMonitor
   Tracks frame latency, inference time, and system resource usage.
   Exposes a `report()` dict consumed by main.py every N frames and by
   the dashboard history writer.

2. FrameSkipTuner
   Adaptive frame-skip controller.  Target: keep the pipeline at or above
   a configurable FPS floor (default 25 fps).

   Algorithm (simple integral controller):
     - Every `window` frames, measure actual FPS.
     - If FPS < target − tolerance  →  increment skip (drop more frames).
     - If FPS > target + tolerance  →  decrement skip (run more frames).
     - Skip is clamped to [0, MAX_SKIP].
     - A hysteresis band (tolerance) prevents oscillation.

   This is intentionally simple: on a laptop running yolov8n at ~30ms/frame
   the tuner typically converges to skip=0 or skip=1 within 3–5 windows.

Usage:
    from utils.performance import PerformanceMonitor, FrameSkipTuner

    monitor = PerformanceMonitor()
    tuner   = FrameSkipTuner(target_fps=25.0)

    # --- inside frame loop ---
    with monitor.frame_timer():
        persons = detector.detect(frame)

    tuner.tick(monitor.fps)
    detector.skip_frames = tuner.skip
"""

from __future__ import annotations

import contextlib
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional

from utils.logger import get_logger

log = get_logger(__name__)

# Maximum skip value the auto-tuner will set
_MAX_SKIP: int = 5

# Minimum frames between tuner adjustments (prevents rapid oscillation)
_TUNER_WINDOW: int = 30


# ---------------------------------------------------------------------------
# Frame latency tracker
# ---------------------------------------------------------------------------
class LatencyTracker:
    """Rolling window of frame-processing durations (wall-clock ms)."""

    def __init__(self, window: int = 120) -> None:
        self._samples: Deque[float] = deque(maxlen=window)

    def record(self, ms: float) -> None:
        self._samples.append(ms)

    @property
    def mean_ms(self) -> float:
        if not self._samples:
            return 0.0
        return sum(self._samples) / len(self._samples)

    @property
    def p95_ms(self) -> float:
        """95th-percentile latency — spot degradation spikes."""
        if len(self._samples) < 5:
            return 0.0
        sorted_s = sorted(self._samples)
        idx = int(len(sorted_s) * 0.95)
        return sorted_s[min(idx, len(sorted_s) - 1)]

    @property
    def max_ms(self) -> float:
        return max(self._samples) if self._samples else 0.0

    @property
    def min_ms(self) -> float:
        return min(self._samples) if self._samples else 0.0


# ---------------------------------------------------------------------------
# Performance monitor
# ---------------------------------------------------------------------------
class PerformanceMonitor:
    """
    Aggregates per-frame timing into rolling statistics.

    Thread note: designed for single-threaded use in the main CV loop.
    """

    def __init__(self, fps_window: int = 60) -> None:
        self._frame_times: Deque[float] = deque(maxlen=fps_window)
        self._frame_start: float = 0.0
        self.frame_latency  = LatencyTracker(window=120)
        self.inference_times: Deque[float] = deque(maxlen=120)
        self.total_frames: int = 0
        self._start_wall: float = time.time()

    @contextlib.contextmanager
    def frame_timer(self):
        """Context manager: time the full frame pipeline."""
        t0 = time.monotonic()
        try:
            yield
        finally:
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            self.frame_latency.record(elapsed_ms)
            now = time.monotonic()
            self._frame_times.append(now)
            self.total_frames += 1

    def record_inference(self, ms: float) -> None:
        """Record a single YOLO inference duration."""
        self.inference_times.append(ms)

    @property
    def fps(self) -> float:
        """Rolling FPS estimate."""
        if len(self._frame_times) < 2:
            return 0.0
        span = self._frame_times[-1] - self._frame_times[0]
        if span <= 0:
            return 0.0
        return (len(self._frame_times) - 1) / span

    @property
    def avg_inference_ms(self) -> float:
        if not self.inference_times:
            return 0.0
        return sum(self.inference_times) / len(self.inference_times)

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_wall

    def report(self) -> dict:
        """Return a snapshot dict suitable for JSON serialisation."""
        return {
            "fps":               round(self.fps, 2),
            "avg_frame_ms":      round(self.frame_latency.mean_ms, 2),
            "p95_frame_ms":      round(self.frame_latency.p95_ms, 2),
            "max_frame_ms":      round(self.frame_latency.max_ms, 2),
            "avg_inference_ms":  round(self.avg_inference_ms, 2),
            "total_frames":      self.total_frames,
            "uptime_s":          round(self.uptime_seconds, 1),
        }

    def log_summary(self) -> None:
        """Emit a structured log line with the current performance snapshot."""
        r = self.report()
        log.info(
            "Perf | FPS={fps} FrameAvg={avg}ms P95={p95}ms "
            "InfAvg={inf}ms Frames={f} Uptime={u}s",
            fps=r["fps"],
            avg=r["avg_frame_ms"],
            p95=r["p95_frame_ms"],
            inf=r["avg_inference_ms"],
            f=r["total_frames"],
            u=r["uptime_s"],
        )


# ---------------------------------------------------------------------------
# Frame-skip auto-tuner
# ---------------------------------------------------------------------------
class FrameSkipTuner:
    """
    Adaptive controller that adjusts `skip_frames` to maintain a target FPS.

    Args:
        target_fps:   Desired minimum FPS (default 25).
        tolerance:    Dead-band around target; avoids constant adjustments.
        window:       Number of frames between evaluation cycles.
        initial_skip: Starting skip value.
        verbose:      Log each adjustment.
    """

    def __init__(
        self,
        target_fps: float = 25.0,
        tolerance: float  = 2.0,
        window: int        = _TUNER_WINDOW,
        initial_skip: int  = 0,
        verbose: bool      = True,
    ) -> None:
        self.target_fps  = target_fps
        self.tolerance   = tolerance
        self._window     = window
        self._skip       = initial_skip
        self._verbose    = verbose
        self._tick_count = 0
        self._adjustments: int = 0

        log.info(
            "FrameSkipTuner | target={t}fps ±{tol} window={w} init_skip={s}",
            t=target_fps, tol=tolerance, w=window, s=initial_skip,
        )

    @property
    def skip(self) -> int:
        """Current recommended skip value for Detector."""
        return self._skip

    def tick(self, current_fps: float) -> int:
        """
        Called once per frame with the current rolling FPS.

        Evaluates every `window` frames whether skip should be adjusted.

        Returns:
            The (possibly updated) skip value.
        """
        self._tick_count += 1

        if self._tick_count % self._window != 0:
            return self._skip

        # ── Evaluation ────────────────────────────────────────────────────────
        lower = self.target_fps - self.tolerance
        upper = self.target_fps + self.tolerance

        old_skip = self._skip

        if current_fps < lower and self._skip < _MAX_SKIP:
            # Too slow → skip more frames
            self._skip = min(self._skip + 1, _MAX_SKIP)
        elif current_fps > upper and self._skip > 0:
            # Fast enough → recover quality
            self._skip = max(self._skip - 1, 0)

        if self._skip != old_skip:
            self._adjustments += 1
            if self._verbose:
                direction = "▲ increased" if self._skip > old_skip else "▼ decreased"
                log.info(
                    "FrameSkipTuner {dir} skip {old}→{new} | fps={fps:.1f} target={t}",
                    dir=direction,
                    old=old_skip,
                    new=self._skip,
                    fps=current_fps,
                    t=self.target_fps,
                )

        return self._skip

    def reset(self, skip: int = 0) -> None:
        """Manually reset skip (e.g. after camera source change)."""
        self._skip = skip
        self._tick_count = 0
        log.debug("FrameSkipTuner reset to skip={s}", s=skip)

    @property
    def adjustments(self) -> int:
        """Total number of skip adjustments made."""
        return self._adjustments

    def report(self) -> dict:
        return {
            "current_skip":   self._skip,
            "target_fps":     self.target_fps,
            "adjustments":    self._adjustments,
            "ticks_evaluated": self._tick_count // self._window,
        }
