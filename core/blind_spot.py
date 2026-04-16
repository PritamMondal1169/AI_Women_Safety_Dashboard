"""
core/blind_spot.py — Blind-spot anomaly detection between linked cameras.

When a tracked person exits Camera N's field of view (reaches the frame edge),
the monitor starts a timer.  If Camera N+1 does not detect a matching entry
within the expected transit window, a BlindSpotAnomaly is raised.

Expected transit time formula:
    T_expected = (distance_m / avg_walking_speed) × buffer_factor
    Default: (distance / 1.35 m/s) × 1.4

Design:
  - Each edge node runs its own BlindSpotMonitor instance.
  - Camera topology (linked pairs + distances) is loaded from coordinator or config.
  - The monitor keeps a dict of pending transits keyed by (exit_camera, track_id).
  - On each frame tick, it checks which transits have exceeded the deadline.

Usage:
    monitor = BlindSpotMonitor(camera_id="cam-1", topology=topology)
    
    # In the frame loop:
    anomalies = monitor.tick(
        current_tracks=active_track_ids,
        exited_tracks=exited_track_ids,
        frame_width=640,
        frame_height=480,
    )
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class CameraLink:
    """Describes the blind-spot link between two cameras."""
    from_camera: str
    to_camera: str
    distance_m: float
    walking_speed_mps: float = 1.35
    buffer_factor: float = 1.4

    @property
    def expected_transit_s(self) -> float:
        """Expected transit time with safety buffer (seconds)."""
        if self.distance_m <= 0:
            return 0.0
        return (self.distance_m / self.walking_speed_mps) * self.buffer_factor


@dataclass
class PendingTransit:
    """A person who exited one camera and is expected at the next."""
    track_id: int
    exit_camera: str
    target_camera: str
    exit_time: float
    deadline: float  # exit_time + expected_transit_s
    exit_position: Tuple[float, float] = (0.0, 0.0)


@dataclass
class BlindSpotAnomaly:
    """Raised when a person fails to appear at the expected camera on time."""
    track_id: int
    exit_camera: str
    target_camera: str
    exit_time: float
    deadline: float
    delay_s: float  # how much past the deadline
    severity: str = "MEDIUM"  # "LOW", "MEDIUM", "HIGH"


class BlindSpotMonitor:
    """
    Monitors blind-spot transits for a single camera node.
    
    Args:
        camera_id: This camera's unique identifier.
        topology: List of CameraLink objects describing connected cameras.
    """

    # Edge detection margin — track is "exiting" if within this many pixels of frame border
    _EDGE_MARGIN_PX: int = 25

    # After this many seconds past deadline with no appearance, severity escalates
    _HIGH_DELAY_S: float = 30.0
    _MEDIUM_DELAY_S: float = 15.0

    def __init__(
        self,
        camera_id: str,
        topology: Optional[List[CameraLink]] = None,
    ) -> None:
        self.camera_id = camera_id
        self._links: Dict[str, CameraLink] = {}
        self._pending: Dict[Tuple[str, int], PendingTransit] = {}  # (target_cam, track_id)
        self._recently_seen: Set[int] = set()  # track IDs visible this frame

        if topology:
            for link in topology:
                if link.from_camera == camera_id:
                    self._links[link.to_camera] = link
            log.info(
                "BlindSpotMonitor[%s] ready | %d linked cameras",
                camera_id, len(self._links),
            )

    def set_topology(self, topology: List[CameraLink]) -> None:
        """Update topology (e.g. after coordinator refresh)."""
        self._links.clear()
        for link in topology:
            if link.from_camera == self.camera_id:
                self._links[link.to_camera] = link

    def on_track_exit(
        self,
        track_id: int,
        exit_position: Tuple[float, float],
    ) -> None:
        """
        Called when a track reaches the edge of this camera's frame (exiting).
        Starts a pending transit timer for linked cameras.
        """
        now = time.monotonic()
        for target_cam, link in self._links.items():
            key = (target_cam, track_id)
            if key in self._pending:
                continue  # already tracking this transit

            transit = PendingTransit(
                track_id=track_id,
                exit_camera=self.camera_id,
                target_camera=target_cam,
                exit_time=now,
                deadline=now + link.expected_transit_s,
                exit_position=exit_position,
            )
            self._pending[key] = transit
            log.info(
                "BlindSpot | Track %d exited %s → expecting at %s in %.1fs",
                track_id, self.camera_id, target_cam, link.expected_transit_s,
            )

    def on_track_entry(self, track_id: int) -> None:
        """
        Called when a new track appears at THIS camera — may resolve a pending transit.
        
        Note: In a multi-camera setup each node notifies the coordinator,
        which then calls on_track_entry on the appropriate monitor.
        For MVP (single process), we check directly.
        """
        keys_to_remove = []
        for key, transit in self._pending.items():
            if transit.target_camera == self.camera_id and transit.track_id == track_id:
                elapsed = time.monotonic() - transit.exit_time
                log.info(
                    "BlindSpot | Track %d arrived at %s in %.1fs (deadline %.1fs) ✓",
                    track_id, self.camera_id, elapsed, transit.deadline - transit.exit_time,
                )
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._pending[key]

    def tick(
        self,
        active_track_ids: Set[int],
        frame_width: int = 640,
        frame_height: int = 480,
        track_positions: Optional[Dict[int, Tuple[float, float]]] = None,
    ) -> List[BlindSpotAnomaly]:
        """
        Called every frame. Check for:
        1. Tracks that are at the frame edge (potential exits)
        2. Pending transits that have exceeded their deadline

        Args:
            active_track_ids: Set of currently visible track IDs.
            frame_width, frame_height: Current frame dimensions.
            track_positions: Dict of track_id → (cx, cy) for edge detection.

        Returns:
            List of BlindSpotAnomaly instances for overdue transits.
        """
        now = time.monotonic()

        # ── Detect exits (tracks near frame edge) ────────────────────────────
        if track_positions and self._links:
            prev_seen = self._recently_seen.copy()
            self._recently_seen = active_track_ids.copy()

            # Tracks that vanished this frame
            vanished = prev_seen - active_track_ids
            for tid in vanished:
                pos = track_positions.get(tid)
                if pos:
                    cx, cy = pos
                    at_edge = (
                        cx < self._EDGE_MARGIN_PX
                        or cx > frame_width - self._EDGE_MARGIN_PX
                        or cy < self._EDGE_MARGIN_PX
                        or cy > frame_height - self._EDGE_MARGIN_PX
                    )
                    if at_edge:
                        self.on_track_exit(tid, pos)

        # ── Check overdue transits ───────────────────────────────────────────
        anomalies: List[BlindSpotAnomaly] = []
        expired_keys = []

        for key, transit in self._pending.items():
            if now > transit.deadline:
                delay = now - transit.deadline
                severity = "LOW"
                if delay > self._HIGH_DELAY_S:
                    severity = "HIGH"
                elif delay > self._MEDIUM_DELAY_S:
                    severity = "MEDIUM"

                anomalies.append(BlindSpotAnomaly(
                    track_id=transit.track_id,
                    exit_camera=transit.exit_camera,
                    target_camera=transit.target_camera,
                    exit_time=transit.exit_time,
                    deadline=transit.deadline,
                    delay_s=delay,
                    severity=severity,
                ))

                # Remove after HIGH severity (stop re-alerting)
                if severity == "HIGH":
                    expired_keys.append(key)

        for key in expired_keys:
            del self._pending[key]

        if anomalies:
            for a in anomalies:
                log.warning(
                    "⚠ BlindSpot ANOMALY | Track %d | %s→%s | delay=%.1fs | severity=%s",
                    a.track_id, a.exit_camera, a.target_camera, a.delay_s, a.severity,
                )

        return anomalies

    @property
    def pending_count(self) -> int:
        return len(self._pending)
