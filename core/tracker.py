"""
core/tracker.py — Per-track state history manager.

Maintains a rolling history of TrackedPerson observations for every active
track ID.  The threat engine and feature extractor consume this history to
compute velocity, direction, sustained-frame counts, and group membership.

Design:
  - TrackState   : dataclass holding the N-frame history for one track ID.
  - TrackManager : dict-of-TrackState, updated each frame, pruning stale tracks.

The TrackManager is the single source of truth for "what has track X been
doing over the last T frames?" — it insulates the threat engine from raw
detector output and from missing-ID edge cases.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Deque, List, Optional, Tuple

import numpy as np

from config import cfg
from core.detector import TrackedPerson
from utils.logger import get_logger

log = get_logger(__name__)

# How many frames of history to keep per track (≈ 2 s at 30 fps)
_HISTORY_LEN: int = 60

# A track is considered "lost" if unseen for this many frames
_MAX_MISSING_FRAMES: int = 45


# ---------------------------------------------------------------------------
# Per-track state
# ---------------------------------------------------------------------------
@dataclass
class TrackState:
    """
    Rolling history and derived state for one persistent track ID.

    Attributes:
        track_id:        Unique BoT-SORT track ID.
        history:         Deque of (cx, cy, timestamp) tuples — bounding-box
                         centres over the last _HISTORY_LEN frames.
        confidences:     Deque of YOLO confidence scores.
        bboxes:          Deque of (x1,y1,x2,y2) raw bounding boxes.
        first_seen:      monotonic timestamp of first observation.
        last_seen:       monotonic timestamp of most recent observation.
        missing_frames:  Consecutive frames this track was not detected.
        threat_score:    Most recent composite threat score [0, 1].
        threat_level:    "NONE" | "LOW" | "MEDIUM" | "HIGH".
        sustained_count: Frames the current threat level has been sustained.
        alert_sent:      Whether an alert has been dispatched for this track.
        alert_sent_at:   Timestamp of last alert dispatch.
    """

    track_id: int
    history: Deque[Tuple[float, float, float]] = field(
        default_factory=lambda: deque(maxlen=_HISTORY_LEN)
    )
    confidences: Deque[float] = field(
        default_factory=lambda: deque(maxlen=_HISTORY_LEN)
    )
    bboxes: Deque[Tuple[int, int, int, int]] = field(
        default_factory=lambda: deque(maxlen=_HISTORY_LEN)
    )
    # Pose keypoints history: each entry is (17, 3) or None
    keypoints: Deque[Optional["np.ndarray"]] = field(
        default_factory=lambda: deque(maxlen=_HISTORY_LEN)
    )
    first_seen: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)
    missing_frames: int = 0

    # Threat state (written by threat.py)
    threat_score: float = 0.0
    threat_level: str = "NONE"
    sustained_count: int = 0
    alert_sent: bool = False
    alert_sent_at: float = 0.0

    # ── Derived helpers ───────────────────────────────────────────────────────

    @property
    def age_seconds(self) -> float:
        """How long this track has been active (seconds)."""
        return self.last_seen - self.first_seen

    @property
    def center(self) -> Optional[Tuple[float, float]]:
        """Most recent centre point, or None if no history."""
        if not self.history:
            return None
        cx, cy, _ = self.history[-1]
        return cx, cy

    @property
    def centers_array(self) -> np.ndarray:
        """
        All recorded centres as a (N, 2) float32 array [cx, cy].
        Useful for vectorised feature computation.
        """
        if not self.history:
            return np.empty((0, 2), dtype=np.float32)
        return np.array([[cx, cy] for cx, cy, _ in self.history], dtype=np.float32)

    @property
    def timestamps_array(self) -> np.ndarray:
        """All recorded timestamps as a (N,) float64 array."""
        if not self.history:
            return np.empty(0, dtype=np.float64)
        return np.array([t for _, _, t in self.history], dtype=np.float64)

    def update(self, person: TrackedPerson) -> None:
        """Append a new observation from the detector."""
        cx, cy = person.center
        self.history.append((cx, cy, person.timestamp))
        self.confidences.append(person.confidence)
        self.bboxes.append(person.bbox)
        self.keypoints.append(person.keypoints)   # may be None for non-pose models
        self.last_seen = person.timestamp
        self.missing_frames = 0

    @property
    def latest_keypoints(self) -> "Optional[np.ndarray]":
        """Return most recent non-None keypoints array (17, 3), or None."""
        for kp in reversed(self.keypoints):
            if kp is not None:
                return kp
        return None

    def mark_missing(self) -> None:
        """Called when this track ID is not present in the current frame."""
        self.missing_frames += 1
        self.last_seen = time.monotonic()

    @property
    def is_stale(self) -> bool:
        """True if the track has been absent too long and should be pruned."""
        return self.missing_frames >= _MAX_MISSING_FRAMES

    def reset_alert_if_cooled(self) -> None:
        """Clear alert_sent flag once the cooldown period has elapsed."""
        if self.alert_sent:
            elapsed = time.monotonic() - self.alert_sent_at
            if elapsed >= cfg.ALERT_COOLDOWN:
                self.alert_sent = False
                log.debug(
                    "Track {id}: alert cooldown expired after {e:.0f}s.",
                    id=self.track_id, e=elapsed,
                )


# ---------------------------------------------------------------------------
# Track manager
# ---------------------------------------------------------------------------
class TrackManager:
    """
    Maintains a registry of TrackState objects, one per active track ID.

    Call `update(persons)` once per frame with the list returned by
    Detector.detect().  The manager will:
      1. Create new TrackState for previously unseen IDs.
      2. Append observations to existing states.
      3. Increment missing_frames for absent tracks.
      4. Prune stale tracks that have been absent too long.
    """

    def __init__(self) -> None:
        self._tracks: Dict[int, TrackState] = {}
        self._frame_count: int = 0
        self._total_tracks_seen: int = 0
        log.info("TrackManager initialised.")

    # ── Public API ────────────────────────────────────────────────────────────

    def update(self, persons: List[TrackedPerson]) -> Dict[int, TrackState]:
        """
        Ingest a list of TrackedPerson from the current frame.

        Args:
            persons: Output of Detector.detect() for the current frame.

        Returns:
            The full current track registry (active + recently missing).
        """
        self._frame_count += 1
        seen_ids = {p.track_id for p in persons}

        # ── Update existing / create new tracks ──────────────────────────────
        for person in persons:
            tid = person.track_id
            if tid not in self._tracks:
                self._tracks[tid] = TrackState(track_id=tid)
                self._total_tracks_seen += 1
                log.debug("New track ID={id} detected.", id=tid)
            self._tracks[tid].update(person)

        # ── Mark absent tracks + prune stale ones ────────────────────────────
        stale_ids = []
        for tid, state in self._tracks.items():
            if tid not in seen_ids:
                state.mark_missing()
                if state.is_stale:
                    stale_ids.append(tid)

        for tid in stale_ids:
            log.debug(
                "Pruning stale track ID={id} (missing {n} frames).",
                id=tid, n=self._tracks[tid].missing_frames,
            )
            del self._tracks[tid]

        # ── Refresh alert cooldowns ───────────────────────────────────────────
        for state in self._tracks.values():
            state.reset_alert_if_cooled()

        if self._frame_count % 150 == 0:
            log.debug(
                "TrackManager | active={a} | total_seen={t} | frame={f}",
                a=len(self._tracks),
                t=self._total_tracks_seen,
                f=self._frame_count,
            )

        return self._tracks

    def get(self, track_id: int) -> Optional[TrackState]:
        """Return the TrackState for a given ID, or None if not tracked."""
        return self._tracks.get(track_id)

    def active_tracks(self) -> List[TrackState]:
        """Return all currently active (non-stale) TrackState objects."""
        return list(self._tracks.values())

    def reset(self) -> None:
        """Clear all track history (e.g. on camera source change)."""
        self._tracks.clear()
        log.info("TrackManager reset.")

    # ── Stats ─────────────────────────────────────────────────────────────────

    @property
    def active_count(self) -> int:
        return len(self._tracks)

    @property
    def total_tracks_seen(self) -> int:
        return self._total_tracks_seen

    @property
    def frame_count(self) -> int:
        return self._frame_count
