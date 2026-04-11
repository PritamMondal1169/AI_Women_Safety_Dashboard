import math
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from config import cfg
from core.tracker import TrackState
from utils.logger import get_logger

log = get_logger(__name__)

# COCO-17 keypoint indices mapping (same as in features.py)
_KP = {
    "l_shoulder": 5, "r_shoulder": 6,
    "l_elbow": 7,    "r_elbow": 8,
    "l_wrist": 9,    "r_wrist": 10,
    "l_hip": 11,     "r_hip": 12,
}

@dataclass
class InteractionResult:
    """Result of analyzing the interaction between two people."""
    target_id: int
    other_id: int
    interaction_type: str   # "NEUTRAL", "FRIENDLY", "DANGER"
    boost: float            # 0.0 to cfg.INTERACTION_BOOST_MAX
    features: Dict[str, float]


class InteractionAnalyzer:
    """
    Analyzes pairwise physical interactions between TrackStates using pose keypoints.
    Looks for signs of struggle (resistance, arm-locks) vs friendly gestures (hugs).
    """

    def __init__(self, frame_diag: float):
        self._diag = max(frame_diag, 1.0)
        self._max_dist = cfg.INTERACTION_DISTANCE_THRESHOLD * self._diag

    def analyze_scene(self, active_states: List[TrackState]) -> Dict[int, InteractionResult]:
        """
        Analyze all pairs in the scene.
        Returns a dict mapping track_id -> highest InteractionResult for that track.
        """
        if not cfg.ENABLE_INTERACTION_ANALYSIS or len(active_states) < 2:
            return {}

        results: Dict[int, InteractionResult] = {}
        
        # Analyze every unique pair
        for i, s1 in enumerate(active_states):
            for j, s2 in enumerate(active_states[i+1:]):
                if s1.center is None or s2.center is None:
                    continue
                
                # Fast distance check -- only analyze if close enough
                d = math.hypot(s1.center[0] - s2.center[0], s1.center[1] - s2.center[1])
                if d > self._max_dist:
                    continue
                
                res1, res2 = self._analyze_pair(s1, s2, d)
                
                # Keep the highest boost interaction for s1
                if s1.track_id not in results or res1.boost > results[s1.track_id].boost:
                    results[s1.track_id] = res1
                
                # Keep the highest boost interaction for s2
                if s2.track_id not in results or res2.boost > results[s2.track_id].boost:
                    results[s2.track_id] = res2

        return results

    def _analyze_pair(self, s1: TrackState, s2: TrackState, dist: float) -> Tuple[InteractionResult, InteractionResult]:
        """Analyze the specific physical interaction between s1 and s2."""
        kp1 = s1.latest_keypoints
        kp2 = s2.latest_keypoints

        # Default neutral response if pose data missing
        neutral1 = InteractionResult(s1.track_id, s2.track_id, "NEUTRAL", 0.0, {})
        neutral2 = InteractionResult(s2.track_id, s1.track_id, "NEUTRAL", 0.0, {})
        
        if kp1 is None or kp2 is None or len(kp1) < 17 or len(kp2) < 17:
            return neutral1, neutral2

        # 1. Contact Detection (are wrists touching bodies?)
        c1_to_2 = self._check_contact(kp1, kp2)  # s1 touching s2
        c2_to_1 = self._check_contact(kp2, kp1)  # s2 touching s1

        # 2. Resistance Score (is someone pulling away?)
        res1, res2 = self._check_resistance(s1, s2, kp1, kp2)

        # 3. Arm Asymmetry (mutual vs one-sided)
        sym1 = self._arm_symmetry(kp1)
        sym2 = self._arm_symmetry(kp2)
        mutual_extension = (sym1 > 0.6 and sym2 > 0.6)  # Hugs are usually mutual

        # Calculate Danger Boost
        boost_1 = 0.0
        boost_2 = 0.0
        interaction = "NEUTRAL"

        # DANGER Rule 1: One-sided physical contact with resistance
        if (c1_to_2 and res2 > 0.5) or (c2_to_1 and res1 > 0.5):
            interaction = "DANGER"
            boost_1 = cfg.INTERACTION_BOOST_MAX
            boost_2 = cfg.INTERACTION_BOOST_MAX
        
        # DANGER Rule 2: Forceful one-sided grab (asymmetric extension + contact)
        elif (c1_to_2 and sym1 < 0.4 and sym2 > 0.6) or (c2_to_1 and sym2 < 0.4 and sym1 > 0.6):
            interaction = "DANGER"
            boost_1 = cfg.INTERACTION_BOOST_MAX * 0.8
            boost_2 = cfg.INTERACTION_BOOST_MAX * 0.8

        # FRIENDLY Rule 1: Mutual contact with highly symmetric poses (hug)
        elif (c1_to_2 or c2_to_1) and mutual_extension and res1 < 0.2 and res2 < 0.2:
            interaction = "FRIENDLY"
            boost_1 = -0.2  # Negative boost (reduces threat)
            boost_2 = -0.2

        feats = {
            "c1_to_2": float(c1_to_2), "c2_to_1": float(c2_to_1),
            "res1": res1, "res2": res2, "sym1": sym1, "sym2": sym2
        }

        r1 = InteractionResult(s1.track_id, s2.track_id, interaction, boost_1, feats)
        r2 = InteractionResult(s2.track_id, s1.track_id, interaction, boost_2, feats)
        return r1, r2

    def _check_contact(self, kp_grabber: np.ndarray, kp_target: np.ndarray) -> bool:
        """Check if grabber's wrists are very close to target's torso/shoulders."""
        try:
            for w_idx in [_KP["l_wrist"], _KP["r_wrist"]]:
                if kp_grabber[w_idx, 2] < 0.3:
                    continue
                w_pt = kp_grabber[w_idx, :2]

                # Check against target's shoulders and hips
                for t_idx in [_KP["l_shoulder"], _KP["r_shoulder"], _KP["l_hip"], _KP["r_hip"]]:
                    if kp_target[t_idx, 2] < 0.3:
                        continue
                    t_pt = kp_target[t_idx, :2]
                    
                    dist = np.linalg.norm(w_pt - t_pt)
                    # Contact threshold ~5% of frame diagonal
                    if dist < (self._diag * 0.05):
                        return True
            return False
        except Exception:
            return False

    def _check_resistance(self, s1: TrackState, s2: TrackState, kp1: np.ndarray, kp2: np.ndarray) -> Tuple[float, float]:
        """
        Check if one person is moving away while the other holds/pulls.
        Returns (resistance_of_1, resistance_of_2) mostly based on velocity vectors.
        """
        if len(s1.centers_array) < 3 or len(s2.centers_array) < 3:
            return 0.0, 0.0

        # Velocity vectors over last few frames
        v1 = s1.centers_array[-1] - s1.centers_array[-3]
        v2 = s2.centers_array[-1] - s2.centers_array[-3]
        
        n1 = np.linalg.norm(v1)
        n2 = np.linalg.norm(v2)
        
        # If no one is moving much, no resistance
        if n1 < 5.0 and n2 < 5.0:
            return 0.0, 0.0

        # Direction vector between them
        c1 = s1.centers_array[-1]
        c2 = s2.centers_array[-1]
        dir_12 = c2 - c1
        dn = np.linalg.norm(dir_12)
        if dn < 1e-6:
            return 0.0, 0.0
        
        dir_12_unit = dir_12 / dn
        
        # Is s1 trying to move away from s2? (dot product < 0)
        res1 = 0.0
        if n1 > 5.0:
            dot1 = np.dot(v1/n1, dir_12_unit)
            if dot1 < -0.3:  # moving away
                res1 = min((-dot1 - 0.3) / 0.7, 1.0)
                
        # Is s2 trying to move away from s1?
        res2 = 0.0
        if n2 > 5.0:
            dot2 = np.dot(v2/n2, -dir_12_unit)
            if dot2 < -0.3:
                res2 = min((-dot2 - 0.3) / 0.7, 1.0)

        return float(res1), float(res2)

    def _arm_symmetry(self, kp: np.ndarray) -> float:
        """Are both arms doing the same thing? 1.0 = highly symmetric, 0.0 = one-sided grab."""
        try:
            ls, rs = kp[_KP["l_shoulder"]], kp[_KP["r_shoulder"]]
            lw, rw = kp[_KP["l_wrist"]], kp[_KP["r_wrist"]]
            
            if min(ls[2], rs[2], lw[2], rw[2]) < 0.3:
                return 1.0  # assume safe/neutral if can't see arms
                
            mid_x = (ls[0] + rs[0]) / 2.0
            
            l_ext = abs(lw[0] - mid_x)
            r_ext = abs(rw[0] - mid_x)
            max_ext = max(l_ext, r_ext, 1.0)
            
            asym = abs(l_ext - r_ext) / max_ext
            return float(np.clip(1.0 - asym, 0.0, 1.0))
        except Exception:
            return 1.0
