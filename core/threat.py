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
    journey_id:      Optional[str] = None  # linked journey (if any)
    blind_spot_score: float = 0.0          # blind-spot anomaly boost
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
        self,
        active_states: List[TrackState],
        journey_thresholds: Optional[Dict[str, float]] = None,
        journey_id: Optional[str] = None,
    ) -> Dict[int, ThreatResult]:
        """Score every active track. Returns Dict[track_id → ThreatResult].
        
        Args:
            active_states: All active TrackState objects.
            journey_thresholds: If a journey is active, adjusted thresholds
                                {"LOW": x, "MEDIUM": y, "HIGH": z}.
            journey_id: ID of the active journey (for traceability).
        """
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
            result = self._score_one(
                state, active_states, interaction_res,
                journey_thresholds=journey_thresholds,
                journey_id=journey_id,
            )
            
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
        self,
        target: TrackState,
        all_states: List[TrackState],
        interaction=None,
        journey_thresholds: Optional[Dict[str, float]] = None,
        journey_id: Optional[str] = None,
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

        # ── Journey-Aware Boosting (Phase 2) ─────────────────────────────────
        if journey_id:
            # Boost score by 15% of the remaining range to make it more sensitive
            # This helps bring MEDIUM threats to HIGH faster during a journey.
            composite += (1.0 - composite) * 0.15
            log.debug("Journey boost applied to track %d: %.3f", target.track_id, composite)
        
        raw_level  = self._score_to_level(composite, journey_thresholds)
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
            journey_id=journey_id,
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
        Simplified 3-Heuristic Hackathon Model:
        1. Proximity: Inverse normalized distance (max threat when touching).
        2. Closure Velocity: Approach speed toward the target.
        3. Surround Score: Angular distribution of other tracked IDs.
        """
        others = [s for s in all_states if s.track_id != target.track_id]
        if not others:
            return 0.0

        # Features from extractor
        prox_norm   = feat.get("proximity_norm",         1.0)
        vel_toward  = feat.get("velocity_toward_target",  0.5)
        encircle    = feat.get("encirclement_score",      0.0)
        surr_count  = feat.get("surrounding_count",       0.0)

        # 1. Proximity (Inverse Normalized Distance)
        # Danger starts at 0.3 (Far), maxes at 0.05 (Critically Close)
        prox_score = np.clip((0.3 - prox_norm) / 0.25, 0.0, 1.0)

        # 2. Closure Velocity (Are they moving towards the target?)
        # vel_toward is 0.5 (Neutral), 1.0 (Directly Toward). 
        # We only care about positive approach.
        vel_score = max(0.0, (vel_toward - 0.5) * 2.0)
        
        # Velocity only adds threat if they are relatively close
        closure_threat = vel_score * np.clip((0.4 - prox_norm) / 0.3, 0.0, 1.0)

        # 3. Surround Score (Encirclement / Boxed in)
        # Higher count and higher angular coverage = higher threat
        surround_threat = encircle * min(surr_count / 3.0, 1.0)

        # ── Weighted combination for Demo Stability ──────────────────────────
        score = (
            0.40 * prox_score      # 40% Weight: Pure distance
            + 0.30 * closure_threat # 30% Weight: Moving towards user
            + 0.30 * surround_threat # 30% Weight: Multiple IDs surrounding
        )

        return float(np.clip(score, 0.0, 1.0))

    # ── Threshold + gating ────────────────────────────────────────────────────

    def _score_to_level(
        self, score: float, thresholds: Optional[Dict[str, float]] = None
    ) -> str:
        t_high = thresholds["HIGH"] if thresholds else cfg.THREAT_HIGH
        t_med = thresholds["MEDIUM"] if thresholds else cfg.THREAT_MEDIUM
        t_low = thresholds["LOW"] if thresholds else cfg.THREAT_LOW
        if score >= t_high:
            return "HIGH"
        elif score >= t_med:
            return "MEDIUM"
        elif score >= t_low:
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

