"""
core/threat.py — XGBoost + hybrid threat scoring engine.

Threat pipeline per track per frame:
  1. FeatureExtractor → 12 spatial/temporal features
  2. XGBoost model score (if model file present)
  3. Heuristic score (always runs as fallback/blend)
  4. Hybrid = α × xgb + (1−α) × heuristic
  5. Sustained-frame gate before level escalation
  6. Levels: NONE → LOW → MEDIUM → HIGH

Calibration targets (heuristic-only, no XGBoost):
  • 1 person alone, stationary          → ~0.00  (NONE)
  • 2 people walking normally           → ~0.15  (NONE)
  • 2 people within 80px               → ~0.25  (LOW)
  • 1 person approaching another fast  → ~0.45  (MEDIUM)
  • 3 people surrounding 1             → ~0.65  (HIGH)
"""

from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from config import cfg
from core.features import FeatureExtractor
from core.tracker import TrackState
from core.interaction import InteractionAnalyzer
from utils.logger import get_logger

log = get_logger(__name__)

# XGBoost blend weight (only used when model is loaded)
# Kept low because the model is trained on SYNTHETIC data — give heuristic
# the majority vote to avoid false positives on real-world footage.
_XGB_ALPHA: float = 0.35

# BGR colours per threat level
THREAT_COLORS: Dict[str, Tuple[int, int, int]] = {
    "NONE":   (0, 200,   0),   # green
    "LOW":    (0, 200, 255),   # yellow
    "MEDIUM": (0, 120, 255),   # orange
    "HIGH":   (0,   0, 255),   # red
}

# ── Proximity danger zones (fraction of frame diagonal) ──────────────────────
# Calibrated for 640×480 (diagonal ≈800px)
_CLOSE_ZONE  = 0.10   # < 10% diagonal  → very close  (~80px)
_MEDIUM_ZONE = 0.20   # < 20% diagonal  → close       (~160px)
_FAR_ZONE    = 0.35   # < 35% diagonal  → in range    (~280px)


# ---------------------------------------------------------------------------
# ThreatResult
# ---------------------------------------------------------------------------
@dataclass
class ThreatResult:
    track_id:        int
    threat_level:    str
    threat_score:    float
    xgb_score:       float
    heuristic_score: float
    features:        Dict[str, float]
    sustained_frames: int
    interaction_type: str = "NEUTRAL"   # from InteractionAnalyzer
    timestamp: float = field(default_factory=time.monotonic)

    @property
    def color_bgr(self) -> Tuple[int, int, int]:
        return THREAT_COLORS.get(self.threat_level, THREAT_COLORS["NONE"])

    @property
    def is_actionable(self) -> bool:
        """HIGH always fires; MEDIUM fires after sustained threshold."""
        if self.threat_level == "HIGH":
            return True
        if self.threat_level == "MEDIUM" and self.sustained_frames >= cfg.THREAT_SUSTAINED_FRAMES:
            return True
        return False


# ---------------------------------------------------------------------------
# ThreatEngine
# ---------------------------------------------------------------------------
class ThreatEngine:
    """
    Scores every active track with a hybrid XGBoost + heuristic engine.

    The heuristic is calibrated to produce meaningful scores with as few as
    2 people in frame — no XGBoost model required for useful detections.
    """

    def __init__(self, frame_width: int = 640, frame_height: int = 480) -> None:
        self._fw = frame_width
        self._fh = frame_height
        self._diag = (frame_width**2 + frame_height**2) ** 0.5
        self._fe = FeatureExtractor(frame_width, frame_height)
        self._ia = InteractionAnalyzer(self._diag)
        self._xgb_model = None
        self._xgb_available = False
        self._load_xgb_model()

        # Per-track proximity frame counter (how many consecutive frames each
        # pair has been within the danger zone)
        self._proximity_counters: Dict[int, int] = {}

        log.info(
    "ThreatEngine ready | xgb={x} | diag={d:.0f}px | "
    "thresholds=({lo},{me},{hi}) | sustained={s}",
    x=self._xgb_available,
    d=self._diag,
    lo=cfg.THREAT_LOW,
    me=cfg.THREAT_MEDIUM,
    hi=cfg.THREAT_HIGH,
    s=cfg.THREAT_SUSTAINED_FRAMES,
)

    # ── Model loading ─────────────────────────────────────────────────────────

    def _load_xgb_model(self) -> None:
        try:
            import xgboost as xgb
            model_path = cfg.threat_model_abs_path
            if not model_path.exists():
                log.info(
                    "XGBoost model not found at {p} — heuristic-only mode.",
                    p=model_path,
                )
                return
            booster = xgb.Booster()
            booster.load_model(str(model_path))
            self._xgb_model = booster
            self._xgb_available = True
            log.success("XGBoost model loaded from {p}.", p=model_path)
        except ImportError:
            log.warning("xgboost not importable — heuristic-only mode.")
        except Exception:
            log.exception("XGBoost load failed — heuristic-only mode.")

    # ── Public API ────────────────────────────────────────────────────────────

    def score_all(
        self, active_states: List[TrackState]
    ) -> Dict[int, ThreatResult]:
        """Score every active track. Returns Dict[track_id → ThreatResult]."""
        results: Dict[int, ThreatResult] = {}
        
        # Pre-compute interaction pairs for the whole scene once
        interactions = self._ia.analyze_scene(active_states)

        # Remove proximity counters for tracks that no longer exist
        active_ids = {s.track_id for s in active_states}
        stale = [tid for tid in self._proximity_counters if tid not in active_ids]
        for tid in stale:
            del self._proximity_counters[tid]

        for state in active_states:
            interaction_res = interactions.get(state.track_id)
            result = self._score_one(state, active_states, interaction_res)
            
            # Write threat state back into TrackState for feature feedback
            prev_level = state.threat_level
            state.threat_score = result.threat_score
            state.threat_level = result.threat_level
            if result.threat_level == prev_level:
                state.sustained_count += 1
            else:
                state.sustained_count = 1
            results[state.track_id] = result

        high_count = sum(1 for r in results.values() if r.threat_level == "HIGH")
        if high_count:
            log.warning("⚠ HIGH threat on {n} track(s).", n=high_count)

        return results

    # ── Core scoring pipeline ─────────────────────────────────────────────────

    def _score_one(
        self, target: TrackState, all_states: List[TrackState], interaction=None
    ) -> ThreatResult:
        feat_dict = self._fe.extract(target, all_states)
        feat_vec  = self._fe.to_vector(feat_dict)

        xgb_score  = self._xgb_score(feat_vec)
        heuristic  = self._heuristic_score(feat_dict, target, all_states)

        if self._xgb_available and xgb_score >= 0.0:
            composite = _XGB_ALPHA * xgb_score + (1.0 - _XGB_ALPHA) * heuristic
        else:
            composite = heuristic

        # Add Interaction Boost
        interaction_type = "NEUTRAL"
        if interaction is not None:
            composite += interaction.boost
            interaction_type = interaction.interaction_type
            # Add interaction features to the dict for the dashboard/logs
            feat_dict.update(interaction.features)

        composite  = float(np.clip(composite, 0.0, 1.0))
        raw_level  = self._score_to_level(composite)
        final_level = self._apply_sustained_gating(target, raw_level)

        log.debug(
            "Track={t} score={s:.3f} h={h:.3f} IA={ia:.2f} level={l} "
            "prox_n={p:.3f} enc={e:.3f} surr={sr}",
            t=target.track_id,
            s=composite,
            h=heuristic,
            ia=getattr(interaction, 'boost', 0.0),
            l=final_level,
            p=feat_dict.get("proximity_norm", 1.0),
            e=feat_dict.get("encirclement_score", 0.0),
            sr=int(feat_dict.get("surrounding_count", 0)),
        )

        return ThreatResult(
            track_id=target.track_id,
            threat_level=final_level,
            threat_score=composite,
            xgb_score=xgb_score,
            heuristic_score=heuristic,
            features=feat_dict,
            sustained_frames=target.sustained_count,
            interaction_type=interaction_type,
        )

    # ── XGBoost inference ─────────────────────────────────────────────────────

    def _xgb_score(self, feat_vec: np.ndarray) -> float:
        if not self._xgb_available or self._xgb_model is None:
            return -1.0
        try:
            import xgboost as xgb
            from core.features import FEATURE_KEYS
            dmat = xgb.DMatrix(feat_vec.reshape(1, -1), feature_names=FEATURE_KEYS)
            pred = self._xgb_model.predict(dmat)
            return float(np.clip(pred[0], 0.0, 1.0))
        except Exception:
            log.exception("XGBoost inference failed.")
            return -1.0

    # ── Heuristic scorer ──────────────────────────────────────────────────────

    def _heuristic_score(
        self,
        feat: Dict[str, float],
        target: TrackState,
        all_states: List[TrackState],
    ) -> float:
        """
        Calibrated heuristic score.

        Key design decisions:
          1. Proximity is computed in ZONES (close/medium/far) rather than
             linear — real danger is non-linear with distance.
          2. Velocity-toward is amplified when ALSO close (AND-gate).
          3. Sustained proximity counter is maintained per-track (not per-frame)
             so it accumulates correctly.
          4. Single-person scenes always score 0 — no threat without others.
          5. Speed is only a threat signal when ALSO pointing toward someone.
        """
        others = [s for s in all_states if s.track_id != target.track_id]

        # ── Gate: need at least one other person ──────────────────────────────
        if not others:
            return 0.0

        prox_norm   = feat.get("proximity_norm",         1.0)
        encircle    = feat.get("encirclement_score",      0.0)
        surr_count  = feat.get("surrounding_count",       0.0)
        speed_norm  = feat.get("speed_norm",              0.0)
        vel_toward  = feat.get("velocity_toward_target",  0.5)
        dir_change  = feat.get("direction_change",        0.0)

        # ── 1. Proximity zone score ───────────────────────────────────────────
        # Non-linear: danger increases steeply as distance shrinks
        if prox_norm < _CLOSE_ZONE:
            prox_score = 1.0
        elif prox_norm < _MEDIUM_ZONE:
            # linear interpolation: 0.5 → 1.0 across medium→close zone
            prox_score = 0.5 + 0.5 * (1.0 - (prox_norm - _CLOSE_ZONE) /
                                       (_MEDIUM_ZONE - _CLOSE_ZONE))
        elif prox_norm < _FAR_ZONE:
            prox_score = 0.5 * (1.0 - (prox_norm - _MEDIUM_ZONE) /
                                 (_FAR_ZONE - _MEDIUM_ZONE))
        else:
            prox_score = 0.0

        # ── 2. Directional approach signal ───────────────────────────────────
        # vel_toward ∈ [0,1]: 0.5=neutral, 1.0=directly toward
        # Ramp starts at 0.55 (not 0.4) so the neutral value of 0.5 does NOT
        # contribute — only clear directional approach scores positively.
        approach = max(0.0, (vel_toward - 0.55) / 0.45)  # ramps from 0.55→1.0

        # AND-gate: approach only matters when also close
        approach_score = approach * prox_score  # removed the min-floor of 0.3

        # ── 3. Sustained proximity counter ───────────────────────────────────
        tid = target.track_id
        if prox_norm < _FAR_ZONE:
            self._proximity_counters[tid] = self._proximity_counters.get(tid, 0) + 1
        else:
            self._proximity_counters[tid] = max(
                0, self._proximity_counters.get(tid, 0) - 2
            )

        sustained_frames = self._proximity_counters[tid]
        # Saturates at THREAT_SUSTAINED_FRAMES
        sustained_score = min(
            sustained_frames / max(cfg.THREAT_SUSTAINED_FRAMES, 1), 1.0
        )

        # ── 4. Group encirclement ─────────────────────────────────────────────
        # With only 1 other person, encirclement is meaningless — boost
        # proximity instead. With 2+ others, use true encirclement.
        if int(surr_count) == 1:
            # 1 person close: scale reduced — normal chat distance shouldn't score
            group_score = prox_score * 0.25
        else:
            group_score = encircle * min(surr_count / 3.0, 1.0)

        # ── 5. Speed signal (only meaningful when moving toward someone) ──────
        # Fast movement toward someone is a threat; fast movement away is not
        speed_signal = min(speed_norm * 2.5, 1.0) * approach

        # ── 6. Erratic path (panic / chase) ──────────────────────────────────
        # Only meaningful when also close
        erratic_score = dir_change * prox_score

        # ── Weighted combination ──────────────────────────────────────────────
        # Calibration targets (heuristic only, no XGBoost):
        #   1 person alone                     → 0.00  (NONE, gated out)
        #   2 people at chat distance          → ~0.08 (NONE)
        #   2 people very close, stationary   → ~0.30 (LOW)
        #   2 people very close, sustained 15f → ~0.47 (MEDIUM)
        #   2 people very close + approaching  → ~0.65 (HIGH)
        #   3+ people surrounding             → ~0.70 (HIGH)
        score = (
            0.25 * prox_score        # raw closeness (elevated — distance matters)
            + 0.22 * approach_score  # moving toward + close
            + 0.16 * group_score     # encirclement / 1-on-1
            + 0.22 * sustained_score # sustained close presence (elevated — key signal)
            + 0.09 * speed_signal    # fast + approaching
            + 0.06 * erratic_score   # erratic when close
        )

        return float(np.clip(score, 0.0, 1.0))

    # ── Threshold + gating ────────────────────────────────────────────────────

    def _score_to_level(self, score: float) -> str:
        if score >= cfg.THREAT_HIGH:
            return "HIGH"
        elif score >= cfg.THREAT_MEDIUM:
            return "MEDIUM"
        elif score >= cfg.THREAT_LOW:
            return "LOW"
        return "NONE"

    def _apply_sustained_gating(self, state: TrackState, raw_level: str) -> str:
        """
        Only gate escalation TO HIGH — require sustained_count >= threshold.
        LOW and MEDIUM escalate freely for fast response.
        Demotion (going down) is always immediate — safety first.
        """
        order = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
        raw_rank     = order.get(raw_level, 0)
        current_rank = order.get(state.threat_level, 0)

        if raw_rank < current_rank:
            return raw_level   # immediate demotion

        if raw_rank > current_rank:
            # Only gate the final jump to HIGH
            if raw_level == "HIGH" and state.sustained_count < cfg.THREAT_SUSTAINED_FRAMES:
                return "MEDIUM"   # cap at MEDIUM until sustained
            return raw_level      # LOW and MEDIUM escalate freely

        return raw_level  # same level

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def build_color_map(
        results: Dict[int, ThreatResult],
    ) -> Dict[int, Tuple[int, int, int]]:
        return {tid: r.color_bgr for tid, r in results.items()}

    @staticmethod
    def summarise(results: Dict[int, ThreatResult]) -> Dict[str, int]:
        counts = {"NONE": 0, "LOW": 0, "MEDIUM": 0, "HIGH": 0}
        for r in results.values():
            counts[r.threat_level] = counts.get(r.threat_level, 0) + 1
        return counts

