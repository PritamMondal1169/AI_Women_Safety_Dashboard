"""
core/features.py — Spatial and temporal feature extraction for the threat engine.

Every function accepts a TrackState (or a pair of TrackStates) and returns a
scalar or small vector that the XGBoost threat model can consume.

Feature catalogue (12 features per frame, all normalised to [0, 1] or signed):
  ┌─────────────────────────────────────┬─────────────────────────────────────┐
  │ Feature name                        │ Description                         │
  ├─────────────────────────────────────┼─────────────────────────────────────┤
  │ speed_px_s                          │ mean speed of this track (px/s)     │
  │ speed_norm                          │ speed normalised by frame diagonal   │
  │ acceleration                        │ rate of speed change (px/s²)        │
  │ direction_change                    │ mean angular change between steps   │
  │ proximity_min                       │ closest approach to any other track │
  │ proximity_norm                      │ proximity / frame diagonal          │
  │ surrounding_count                   │ # persons within 150 px radius      │
  │ encirclement_score                  │ angular spread of surrounding group │
  │ isolation_score                     │ 1 if lone woman, 0 if in group      │
  │ sustained_proximity_frames          │ frames this person has been close   │
  │ velocity_toward_target              │ dot(vel, direction_to_nearest)      │
  │ track_age_s                         │ how long this track has been active │
  └─────────────────────────────────────┴─────────────────────────────────────┘

All features are computed from pixel-space coordinates; the frame diagonal
is used as a normalisation constant so the extractor is resolution-agnostic.

Usage:

    from core.features import FeatureExtractor
    fe = FeatureExtractor(frame_width=640, frame_height=480)
    feat_dict = fe.extract(state, all_states)
    feat_vector = fe.to_vector(feat_dict)   # shape (12,)
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np

from core.tracker import TrackState
from utils.logger import get_logger

log = get_logger(__name__)

# Radius (px) within which a neighbour is "surrounding" the target
_SURROUND_RADIUS_PX: float = 150.0

# Minimum history length before computing velocity-based features
_MIN_HISTORY: int = 3

# Feature vector length — must match XGBoost training schema
FEATURE_DIM: int = 20

# Named feature keys in fixed order (used by to_vector)
# First 12: spatial / temporal (unchanged)
# Last  8: pose / body-language (new)
FEATURE_KEYS: List[str] = [
    # ── Spatial / temporal (original 12) ────────────────────────────────────
    "speed_px_s",
    "speed_norm",
    "acceleration",
    "direction_change",
    "proximity_min",
    "proximity_norm",
    "surrounding_count",
    "encirclement_score",
    "isolation_score",
    "sustained_proximity_frames",
    "velocity_toward_target",
    "track_age_s",
    # ── Pose / body-language (new 8) ────────────────────────────────────────
    "arm_extension_score",      # how straight/extended the arms are (0=bent, 1=straight)
    "arm_toward_target",        # arm extension direction toward nearest person (0→1)
    "wrist_proximity_norm",     # closest wrist-to-other-person distance, normalised
    "body_facing_score",        # whether bodies are face-to-face (0=side, 1=facing)
    "shoulder_raise_score",     # shoulder height relative to normal (0=low, 1=raised)
    "elbow_angle_score",        # elbow bend: 0=open wide, 1=tight fighting stance
    "pose_symmetry_score",      # bilateral symmetry: 0=asymmetric reach, 1=symmetric
    "pose_confidence",          # mean keypoint confidence (0=no pose, 1=high quality)
]

# COCO-17 keypoint indices used by pose features
_KP = {
    "nose":       0,
    "l_eye":      1,  "r_eye":      2,
    "l_ear":      3,  "r_ear":      4,
    "l_shoulder": 5,  "r_shoulder": 6,
    "l_elbow":    7,  "r_elbow":    8,
    "l_wrist":    9,  "r_wrist":   10,
    "l_hip":     11,  "r_hip":     12,
    "l_knee":    13,  "r_knee":    14,
    "l_ankle":   15,  "r_ankle":   16,
}


class FeatureExtractor:
    """
    Stateless extractor: computes all features for one track relative to the
    full set of active tracks in the current frame.

    Args:
        frame_width:  Width of the video frame in pixels.
        frame_height: Height of the video frame in pixels.
    """

    def __init__(self, frame_width: int = 640, frame_height: int = 480) -> None:
        self._fw = frame_width
        self._fh = frame_height
        # Frame diagonal used for normalisation (Pythagorean)
        self._diag: float = math.hypot(frame_width, frame_height)
        self._pose_fe = PoseFeatureExtractor()
        log.info(
            "FeatureExtractor ready | {w}x{h} | diag={d:.1f}px | features={f}",
            w=frame_width, h=frame_height, d=self._diag, f=FEATURE_DIM,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def extract(
        self,
        target: TrackState,
        all_states: List[TrackState],
    ) -> Dict[str, float]:
        """
        Compute all 20 features for `target` given the full active-track list.

        Args:
            target:     The track we are scoring.
            all_states: Every active TrackState this frame (incl. target).

        Returns:
            Dict mapping FEATURE_KEYS → float values (20 entries).
        """
        others = [s for s in all_states if s.track_id != target.track_id]

        speed, accel = self._speed_and_accel(target)
        dir_change = self._direction_change(target)
        prox_min, prox_norm = self._proximity(target, others)
        surr_count = self._surrounding_count(target, others)
        encircle = self._encirclement_score(target, others)
        isolation = self._isolation_score(surr_count)
        sustained = self._sustained_proximity(target)
        vel_toward = self._velocity_toward_nearest(target, others)
        age = target.age_seconds

        feat: Dict[str, float] = {
            "speed_px_s":               speed,
            "speed_norm":               min(speed / max(self._diag, 1.0), 1.0),
            "acceleration":             accel,
            "direction_change":         dir_change,
            "proximity_min":            prox_min,
            "proximity_norm":           prox_norm,
            "surrounding_count":        float(surr_count),
            "encirclement_score":       encircle,
            "isolation_score":          isolation,
            "sustained_proximity_frames": float(sustained),
            "velocity_toward_target":   vel_toward,
            "track_age_s":              min(age, 300.0) / 300.0,
        }

        # ── Merge pose features ───────────────────────────────────────────────
        pose_feat = self._pose_fe.extract(target, others, self._diag)
        feat.update(pose_feat)

        log.trace(
            "Features track={id}: speed={sp:.1f} prox={pr:.0f} surr={su} enc={en:.2f} "
            "arm_ext={ae:.2f} facing={fa:.2f} pose_conf={pc:.2f}",
            id=target.track_id,
            sp=speed,
            pr=prox_min,
            su=surr_count,
            en=encircle,
            ae=feat.get("arm_extension_score", 0.0),
            fa=feat.get("body_facing_score", 0.0),
            pc=feat.get("pose_confidence", 0.0),
        )
        return feat

    def to_vector(self, feat: Dict[str, float]) -> np.ndarray:
        """
        Convert a feature dict to a fixed-order numpy array of shape (FEATURE_DIM,).
        Keys not present default to 0.0.
        """
        return np.array([feat.get(k, 0.0) for k in FEATURE_KEYS], dtype=np.float32)

    def extract_vector(
        self,
        target: TrackState,
        all_states: List[TrackState],
    ) -> np.ndarray:
        """Convenience: extract + to_vector in one call."""
        return self.to_vector(self.extract(target, all_states))

    # ── Individual feature computations ───────────────────────────────────────

    def _speed_and_accel(self, state: TrackState) -> tuple[float, float]:
        """
        Mean speed (px/s) and acceleration (px/s²) from position history.

        Uses finite differences on centre positions, weighted by actual
        elapsed time between frames (handles variable FPS correctly).
        """
        pts = state.centers_array      # (N, 2)
        ts  = state.timestamps_array   # (N,)

        if len(pts) < _MIN_HISTORY:
            return 0.0, 0.0

        # Step displacements and time deltas
        deltas = np.diff(pts, axis=0)          # (N-1, 2)
        dt     = np.diff(ts)                   # (N-1,)
        dt     = np.where(dt < 1e-6, 1e-6, dt)  # guard against zero dt

        speeds = np.linalg.norm(deltas, axis=1) / dt   # (N-1,) px/s

        mean_speed = float(np.mean(speeds))

        if len(speeds) >= 2:
            accel_vals = np.abs(np.diff(speeds)) / dt[:-1]
            mean_accel = float(np.mean(accel_vals))
        else:
            mean_accel = 0.0

        return mean_speed, mean_accel

    def _direction_change(self, state: TrackState) -> float:
        """
        Mean angular change (radians) between consecutive velocity vectors.

        High values → erratic, unpredictable movement.
        Returns value in [0, π], normalised to [0, 1].
        """
        pts = state.centers_array
        if len(pts) < _MIN_HISTORY + 1:
            return 0.0

        deltas = np.diff(pts, axis=0).astype(np.float64)    # (N-1, 2)
        # Compute angle between consecutive step vectors
        angles = []
        for i in range(len(deltas) - 1):
            v1, v2 = deltas[i], deltas[i + 1]
            n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
            if n1 < 1e-6 or n2 < 1e-6:
                continue
            cos_a = np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0)
            angles.append(math.acos(cos_a))

        if not angles:
            return 0.0
        return float(np.mean(angles)) / math.pi   # normalise to [0, 1]

    def _proximity(
        self, target: TrackState, others: List[TrackState]
    ) -> tuple[float, float]:
        """
        Minimum Euclidean distance (px) from this track's latest centre to any
        other active track's latest centre.

        Returns (raw_px, normalised_by_diagonal).
        """
        if not others or target.center is None:
            return self._diag, 1.0  # no neighbours → max distance

        tcx, tcy = target.center
        min_dist = self._diag

        for other in others:
            if other.center is None:
                continue
            ocx, ocy = other.center
            d = math.hypot(tcx - ocx, tcy - ocy)
            if d < min_dist:
                min_dist = d

        return min_dist, min(min_dist / max(self._diag, 1.0), 1.0)

    def _surrounding_count(
        self, target: TrackState, others: List[TrackState]
    ) -> int:
        """Number of other tracks within _SURROUND_RADIUS_PX of target."""
        if target.center is None:
            return 0
        tcx, tcy = target.center
        count = 0
        for other in others:
            if other.center is None:
                continue
            ocx, ocy = other.center
            if math.hypot(tcx - ocx, tcy - ocy) <= _SURROUND_RADIUS_PX:
                count += 1
        return count

    def _encirclement_score(
        self, target: TrackState, others: List[TrackState]
    ) -> float:
        """
        Measure how evenly other tracks surround the target (angular spread).

        Algorithm:
          1. Compute bearing from target to each surrounding neighbour.
          2. Sort bearings and find the largest angular gap.
          3. Encirclement = 1 − (largest_gap / 2π)

        Score → 1.0 means perfectly encircled; 0.0 means all on one side.
        Requires ≥ 2 neighbours to be meaningful.
        """
        if target.center is None or len(others) < 2:
            return 0.0

        tcx, tcy = target.center
        bearings = []
        for other in others:
            if other.center is None:
                continue
            ocx, ocy = other.center
            bearing = math.atan2(ocy - tcy, ocx - tcx)  # [-π, π]
            bearings.append(bearing)

        if len(bearings) < 2:
            return 0.0

        bearings_sorted = sorted(bearings)
        # Include wrap-around gap
        gaps = [
            bearings_sorted[i + 1] - bearings_sorted[i]
            for i in range(len(bearings_sorted) - 1)
        ]
        wrap_gap = (bearings_sorted[0] + 2 * math.pi) - bearings_sorted[-1]
        gaps.append(wrap_gap)

        largest_gap = max(gaps)
        encirclement = 1.0 - (largest_gap / (2 * math.pi))
        return max(0.0, min(1.0, encirclement))

    def _isolation_score(self, surrounding_count: int) -> float:
        """
        1.0 if the target is completely alone (no surrounding persons).
        Decreases as the group around them grows.
        """
        if surrounding_count == 0:
            return 1.0
        # Soft decay: 1/(1+n) — alone=1.0, 1 neighbour=0.5, 2=0.33, …
        return 1.0 / (1.0 + surrounding_count)

    def _sustained_proximity(self, state: TrackState) -> int:
        """
        Return the track's current sustained_count from threat engine feedback.
        This is written by threat.py and read back here as a feature, giving
        the model temporal memory of how long a condition has persisted.
        """
        return state.sustained_count

    def _velocity_toward_nearest(
        self, target: TrackState, others: List[TrackState]
    ) -> float:
        """
        Dot product of target's velocity vector with the unit direction toward
        the nearest other track.

        Positive → moving toward them.
        Negative → moving away.
        Normalised to [−1, 1] then shifted to [0, 1] for XGBoost.
        """
        pts = target.centers_array
        if len(pts) < _MIN_HISTORY or not others or target.center is None:
            return 0.5  # neutral

        # Instantaneous velocity: last two positions
        vel = pts[-1] - pts[-2]  # (2,)
        vel_norm = np.linalg.norm(vel)
        if vel_norm < 1e-6:
            return 0.5

        vel_unit = vel / vel_norm

        # Find nearest other
        tcx, tcy = target.center
        min_dist = float("inf")
        nearest_dir: Optional[np.ndarray] = None
        for other in others:
            if other.center is None:
                continue
            ocx, ocy = other.center
            d = math.hypot(tcx - ocx, tcy - ocy)
            if d < min_dist:
                min_dist = d
                delta = np.array([ocx - tcx, ocy - tcy], dtype=np.float32)
                dn = np.linalg.norm(delta)
                nearest_dir = delta / dn if dn > 1e-6 else np.zeros(2)

        if nearest_dir is None:
            return 0.5

        dot = float(np.dot(vel_unit, nearest_dir))   # [-1, 1]
        return (dot + 1.0) / 2.0                      # shift to [0, 1]


# ---------------------------------------------------------------------------
# PoseFeatureExtractor — body-language features from COCO-17 keypoints
# ---------------------------------------------------------------------------
class PoseFeatureExtractor:
    """
    Computes 8 body-language features from COCO-17 pose keypoints.

    All features return safe neutral / zero values when keypoints are
    unavailable, so the system degrades gracefully with non-pose models.

    COCO-17 indices (abbreviated):
        5=LShoulder  6=RShoulder  7=LElbow  8=RElbow
        9=LWrist    10=RWrist    11=LHip   12=RHip
    """

    # Minimum per-keypoint confidence to trust that keypoint
    _KP_CONF_THRESHOLD: float = 0.3

    def extract(
        self,
        target: TrackState,
        others: List[TrackState],
        diag: float,
    ) -> Dict[str, float]:
        """Return dict of 8 pose feature values for `target`."""
        kp = target.latest_keypoints   # (17, 3) float32 or None

        if kp is None or len(kp) < 17:
            return self._neutral()

        # Overall pose confidence (mean over all 17 keypoints)
        conf_mean = float(np.mean(kp[:, 2]))

        # Convenience accessor: returns (x, y) if confident, else None
        def pt(name: str) -> Optional[np.ndarray]:
            idx = _KP[name]
            if kp[idx, 2] >= self._KP_CONF_THRESHOLD:
                return kp[idx, :2]
            return None

        # ── 1. Arm extension score ──────────────────────────────────────────
        # Measures how straight each arm is (shoulder→elbow→wrist angle).
        # Straight arm (180°) = 1.0; fully bent (0°) = 0.0
        ext_scores = []
        for side in [("l_shoulder", "l_elbow", "l_wrist"),
                     ("r_shoulder", "r_elbow", "r_wrist")]:
            s, e, w = [pt(n) for n in side]
            if s is not None and e is not None and w is not None:
                v1 = e - s
                v2 = w - e
                n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
                if n1 > 1e-6 and n2 > 1e-6:
                    cos_a = float(np.clip(np.dot(v1/n1, v2/n2), -1.0, 1.0))
                    angle = math.acos(cos_a)             # 0=bent, π=straight
                    ext_scores.append(angle / math.pi)
        arm_extension = float(np.mean(ext_scores)) if ext_scores else 0.0

        # ── 2. Arm toward target ────────────────────────────────────────────
        # Is the extended arm pointing toward the nearest other person?
        arm_toward = 0.0
        if others and target.center is not None:
            # Find nearest other person's position
            tcx, tcy = target.center
            nearest_pos = None
            min_d = float("inf")
            for o in others:
                if o.center is None:
                    continue
                d = math.hypot(o.center[0] - tcx, o.center[1] - tcy)
                if d < min_d:
                    min_d = d
                    nearest_pos = np.array(o.center, dtype=np.float32)

            if nearest_pos is not None:
                dir_to_other = nearest_pos - np.array([tcx, tcy], dtype=np.float32)
                dn = np.linalg.norm(dir_to_other)
                if dn > 1e-6:
                    dir_unit = dir_to_other / dn
                    # Check both wrists — whichever is more extended
                    for wrist_name, shoulder_name in [
                        ("l_wrist", "l_shoulder"), ("r_wrist", "r_shoulder")
                    ]:
                        w_pt, s_pt = pt(wrist_name), pt(shoulder_name)
                        if w_pt is not None and s_pt is not None:
                            arm_vec = w_pt - s_pt
                            av_norm = np.linalg.norm(arm_vec)
                            if av_norm > 1e-6:
                                dot = float(np.dot(arm_vec / av_norm, dir_unit))
                                arm_toward = max(arm_toward, (dot + 1.0) / 2.0)

        # ── 3. Wrist proximity to other person ─────────────────────────────
        wrist_prox = 1.0  # 1.0 = far away (safe sentinel)
        for wrist_name in ("l_wrist", "r_wrist"):
            w_pt = pt(wrist_name)
            if w_pt is None:
                continue
            for o in others:
                if o.center is None:
                    continue
                d = math.hypot(w_pt[0] - o.center[0], w_pt[1] - o.center[1])
                norm_d = min(d / max(diag, 1.0), 1.0)
                wrist_prox = min(wrist_prox, norm_d)

        # ── 4. Body facing score ────────────────────────────────────────────
        # Face-to-face confrontation: shoulder vectors of the two people point
        # toward each other (dot product of normals close to -1).
        body_facing = 0.0
        ls, rs = pt("l_shoulder"), pt("r_shoulder")
        if ls is not None and rs is not None and others:
            # Target shoulder axis (left→right vector, projected XY)
            target_axis = rs - ls
            ta_norm = np.linalg.norm(target_axis)
            if ta_norm > 1e-6 and target.center is not None:
                target_axis /= ta_norm
                # Target's forward = perpendicular to shoulder axis (toward camera)
                target_fwd = np.array([-target_axis[1], target_axis[0]])
                # Direction toward nearest other
                tcx, tcy = target.center
                for o in others:
                    if o.center is None:
                        continue
                    d_vec = np.array([o.center[0] - tcx, o.center[1] - tcy],
                                     dtype=np.float32)
                    dv_norm = np.linalg.norm(d_vec)
                    if dv_norm > 1e-6:
                        dot = float(np.dot(target_fwd, d_vec / dv_norm))
                        # dot ≈ 1 → facing each other; ≈ 0 → sideways
                        body_facing = max(body_facing, (dot + 1.0) / 2.0)

        # ── 5. Shoulder raise score ─────────────────────────────────────────
        # Raised shoulders = aggressive posture.
        # Compare shoulder Y to hip Y (normalised by person height).
        shoulder_raise = 0.0
        lh, rh = pt("l_hip"), pt("r_hip")
        if ls is not None and rs is not None and lh is not None and rh is not None:
            mid_shoulder_y = float((ls[1] + rs[1]) / 2.0)
            mid_hip_y      = float((lh[1] + rh[1]) / 2.0)
            torso_h = abs(mid_hip_y - mid_shoulder_y)
            if torso_h > 1e-6:
                # In image coords Y increases downward; raised shoulders = smaller Y
                # Normally shoulders are ~0.3–0.4 × torso_h above hips
                normal_offset = 0.0
                actual_offset = (mid_hip_y - mid_shoulder_y) / torso_h
                shoulder_raise = max(0.0, min(1.0, (normal_offset - actual_offset + 1.0)))

        # ── 6. Elbow angle score ────────────────────────────────────────────
        # Tight (close to body) elbows = fighting stance; wide = relaxed
        elbow_score = 0.0
        le, re = pt("l_elbow"), pt("r_elbow")
        if ls is not None and rs is not None and le is not None and re is not None:
            shoulder_width = max(np.linalg.norm(rs - ls), 1.0)
            l_elbow_offset = abs(float(le[0] - ls[0]))
            r_elbow_offset = abs(float(re[0] - rs[0]))
            # Normalised by shoulder width; elbows tucked in = fighting stance
            l_score = max(0.0, 1.0 - l_elbow_offset / shoulder_width)
            r_score = max(0.0, 1.0 - r_elbow_offset / shoulder_width)
            elbow_score = float(np.mean([l_score, r_score]))

        # ── 7. Pose symmetry score ──────────────────────────────────────────
        # High = both arms mirrored (hug/wave); low = one arm extended (grab)
        symmetry = 1.0
        le_pt, re_pt = pt("l_elbow"), pt("r_elbow")
        lw_pt, rw_pt = pt("l_wrist"), pt("r_wrist")
        ls_pt, rs_pt = pt("l_shoulder"), pt("r_shoulder")
        if (le_pt is not None and re_pt is not None and
                lw_pt is not None and rw_pt is not None and
                ls_pt is not None and rs_pt is not None):
            mid_x = float((ls_pt[0] + rs_pt[0]) / 2.0)
            # Extension distance of each wrist from body centre
            l_ext = abs(lw_pt[0] - mid_x)
            r_ext = abs(rw_pt[0] - mid_x)
            max_ext = max(l_ext, r_ext, 1.0)
            # Asymmetry: 0=perfectly symmetric, 1=fully one-sided
            asymmetry = abs(l_ext - r_ext) / max_ext
            symmetry = 1.0 - asymmetry

        return {
            "arm_extension_score":  float(np.clip(arm_extension, 0.0, 1.0)),
            "arm_toward_target":    float(np.clip(arm_toward,    0.0, 1.0)),
            "wrist_proximity_norm": float(np.clip(wrist_prox,    0.0, 1.0)),
            "body_facing_score":    float(np.clip(body_facing,   0.0, 1.0)),
            "shoulder_raise_score": float(np.clip(shoulder_raise, 0.0, 1.0)),
            "elbow_angle_score":    float(np.clip(elbow_score,   0.0, 1.0)),
            "pose_symmetry_score":  float(np.clip(symmetry,      0.0, 1.0)),
            "pose_confidence":      float(np.clip(conf_mean,     0.0, 1.0)),
        }

    @staticmethod
    def _neutral() -> Dict[str, float]:
        """Return safe neutral defaults when pose is unavailable."""
        return {
            "arm_extension_score":  0.0,
            "arm_toward_target":    0.0,
            "wrist_proximity_norm": 1.0,   # 1.0 = far away (safe)
            "body_facing_score":    0.0,
            "shoulder_raise_score": 0.0,
            "elbow_angle_score":    0.0,
            "pose_symmetry_score":  1.0,   # 1.0 = symmetric (neutral)
            "pose_confidence":      0.0,
        }

