"""
scripts/train_threat_model.py — XGBoost threat classifier training pipeline.

This script does three things:
  1. Generates a realistic synthetic dataset from first principles.
  2. Trains an XGBoost binary classifier (safe=0 / threat=1).
  3. Saves the booster to models/threat_xgb.json.

Once saved, the ThreatEngine loads it automatically on next startup and
the heuristic-only fallback is replaced by the trained model.

─────────────────────────────────────────────────────────────────────────
SYNTHETIC DATA STRATEGY
─────────────────────────────────────────────────────────────────────────
We simulate two populations across the 20-feature space defined in
core/features.py (12 spatial/temporal + 8 pose/body-language):

  SAFE scenarios (label=0):
    • Normal street walking   — moderate speed, low proximity
    • Standing alone          — zero speed, full isolation
    • Small friendly group    — clustered but no directional convergence
    • Hug                     — very close, arms open/wrapping, symmetric
    • Handshake               — one arm extended sideways, bodies side-by-side

  THREAT scenarios (label=1):
    • Single person followed  — medium speed toward victim, sustained proximity
    • Group encirclement      — high encirclement score, low isolation
    • Rush / grab approach    — high speed, high velocity-toward, close
    • Grab (arm toward)       — wrist very close to other, arm extended toward
    • Strike approach         — fast arm extension toward person, asymmetric
    • Blocking (defensive)    — target arms raised, facing aggressor
    • Mixed high-threat       — random combination of threat signals

Each scenario uses randomised Gaussian noise so the model learns
distributions, not point estimates.

─────────────────────────────────────────────────────────────────────────
REAL DATA INTEGRATION
─────────────────────────────────────────────────────────────────────────
If you have labelled CSV data from real annotations:

    python scripts/train_threat_model.py --data path/to/labels.csv

The CSV must have columns matching FEATURE_KEYS (see core/features.py)
plus a 'label' column (0 = safe, 1 = threat).

─────────────────────────────────────────────────────────────────────────
Run:
    python scripts/train_threat_model.py               # synthetic only
    python scripts/train_threat_model.py --data real.csv
    python scripts/train_threat_model.py --n 20000 --eval
    python scripts/train_threat_model.py --output models/my_model.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from core.features import FEATURE_KEYS, FEATURE_DIM
from utils.logger import setup_logging, get_logger
from config import cfg

setup_logging(cfg.log_abs_dir, cfg.LOG_LEVEL)
log = get_logger(__name__)

# ── Reproducibility ───────────────────────────────────────────────────────────
_RNG_SEED = 42
rng = np.random.default_rng(_RNG_SEED)


# ---------------------------------------------------------------------------
# Feature index helpers
# ---------------------------------------------------------------------------
def _idx(name: str) -> int:
    return FEATURE_KEYS.index(name)

_I = {k: _idx(k) for k in FEATURE_KEYS}   # feature name → column index


# ---------------------------------------------------------------------------
# Scenario generators  (each returns an (N, FEATURE_DIM) float32 array)
# ---------------------------------------------------------------------------

def _gaussian(n: int, means: dict, stds: dict, clip_01: bool = True) -> np.ndarray:
    """
    Generate N samples where each feature is an independent Gaussian.

    Args:
        n:       Number of samples.
        means:   Dict of feature_name → mean value.
        stds:    Dict of feature_name → std dev.
        clip_01: Clip all features to [0,1] after sampling.

    Returns:
        (N, FEATURE_DIM) float32 array.
    """
    X = np.zeros((n, FEATURE_DIM), dtype=np.float32)
    for name, mean in means.items():
        std = stds.get(name, 0.05)
        col = _I[name]
        X[:, col] = rng.normal(mean, std, size=n).astype(np.float32)
    if clip_01:
        X = np.clip(X, 0.0, 1.0)
    return X


def scenario_safe_walking(n: int) -> np.ndarray:
    """Normal pedestrian walking — no threat indicators."""
    return _gaussian(n,
        means={
            "speed_norm":             0.15,
            "speed_px_s":             60.0,
            "acceleration":           0.02,
            "direction_change":       0.10,
            "proximity_min":          0.65,
            "proximity_norm":         0.65,
            "surrounding_count":      0.3,
            "encirclement_score":     0.05,
            "isolation_score":        0.75,
            "sustained_proximity_frames": 0.02,
            "velocity_toward_target": 0.45,
            "track_age_s":            0.35,
        },
        stds={
            "speed_norm": 0.07, "speed_px_s": 30.0, "direction_change": 0.08,
            "proximity_norm": 0.12, "isolation_score": 0.15,
        },
    )


def scenario_standing_alone(n: int) -> np.ndarray:
    """Person standing stationary, no one nearby."""
    return _gaussian(n,
        means={
            "speed_norm":             0.01,
            "speed_px_s":             2.0,
            "acceleration":           0.005,
            "direction_change":       0.02,
            "proximity_min":          0.90,
            "proximity_norm":         0.90,
            "surrounding_count":      0.0,
            "encirclement_score":     0.0,
            "isolation_score":        1.0,
            "sustained_proximity_frames": 0.0,
            "velocity_toward_target": 0.50,
            "track_age_s":            0.25,
        },
        stds={
            "speed_norm": 0.008, "proximity_norm": 0.05,
            "isolation_score": 0.02,
        },
    )


def scenario_friendly_group(n: int) -> np.ndarray:
    """Small group of people clustered together — safe social interaction."""
    return _gaussian(n,
        means={
            "speed_norm":             0.10,
            "speed_px_s":             40.0,
            "acceleration":           0.02,
            "direction_change":       0.12,
            "proximity_min":          0.15,
            "proximity_norm":         0.15,
            "surrounding_count":      2.5,
            "encirclement_score":     0.20,   # low — not surrounding
            "isolation_score":        0.25,
            "sustained_proximity_frames": 0.10,
            "velocity_toward_target": 0.50,
            "track_age_s":            0.40,
        },
        stds={
            "speed_norm": 0.05, "proximity_norm": 0.07,
            "encirclement_score": 0.08, "surrounding_count": 0.8,
        },
    )


def scenario_following(n: int) -> np.ndarray:
    """One person persistently following another — harassment pattern."""
    return _gaussian(n,
        means={
            "speed_norm":             0.20,
            "speed_px_s":             90.0,
            "acceleration":           0.05,
            "direction_change":       0.08,   # smooth tracking movement
            "proximity_min":          0.12,
            "proximity_norm":         0.12,
            "surrounding_count":      1.0,
            "encirclement_score":     0.15,
            "isolation_score":        0.50,
            "sustained_proximity_frames": 0.65,  # key: sustained close approach
            "velocity_toward_target": 0.82,       # moving toward victim
            "track_age_s":            0.55,
        },
        stds={
            "speed_norm": 0.06, "proximity_norm": 0.05,
            "sustained_proximity_frames": 0.12, "velocity_toward_target": 0.08,
        },
    )


def scenario_group_encirclement(n: int) -> np.ndarray:
    """Multiple people surrounding the target — mob/assault pattern."""
    return _gaussian(n,
        means={
            "speed_norm":             0.12,
            "speed_px_s":             50.0,
            "acceleration":           0.04,
            "direction_change":       0.15,
            "proximity_min":          0.08,
            "proximity_norm":         0.08,
            "surrounding_count":      4.5,
            "encirclement_score":     0.82,   # high: surrounded from all sides
            "isolation_score":        0.10,
            "sustained_proximity_frames": 0.55,
            "velocity_toward_target": 0.70,
            "track_age_s":            0.30,
        },
        stds={
            "speed_norm": 0.04, "proximity_norm": 0.03,
            "encirclement_score": 0.08, "surrounding_count": 1.2,
            "velocity_toward_target": 0.10,
        },
    )


def scenario_rush_approach(n: int) -> np.ndarray:
    """Fast aggressive approach — snatching / grab attempt."""
    return _gaussian(n,
        means={
            "speed_norm":             0.70,    # very fast
            "speed_px_s":             280.0,
            "acceleration":           0.55,    # sudden speed-up
            "direction_change":       0.05,    # direct beeline
            "proximity_min":          0.04,
            "proximity_norm":         0.04,
            "surrounding_count":      1.0,
            "encirclement_score":     0.10,
            "isolation_score":        0.55,
            "sustained_proximity_frames": 0.20,
            "velocity_toward_target": 0.95,    # direct toward
            "track_age_s":            0.08,    # short track — new appearance
        },
        stds={
            "speed_norm": 0.12, "acceleration": 0.10,
            "proximity_norm": 0.02, "velocity_toward_target": 0.05,
        },
    )


def scenario_mixed_threat(n: int) -> np.ndarray:
    """Random combination of threat features — broadens the decision boundary."""
    X = np.zeros((n, FEATURE_DIM), dtype=np.float32)
    # Randomly strong on each threat dimension
    for i in range(n):
        threat_type = rng.integers(0, 4)
        if threat_type == 0:       # close + fast
            X[i, _I["proximity_norm"]]         = rng.uniform(0.02, 0.15)
            X[i, _I["speed_norm"]]             = rng.uniform(0.40, 0.90)
            X[i, _I["velocity_toward_target"]] = rng.uniform(0.70, 1.00)
        elif threat_type == 1:     # surrounded + sustained
            X[i, _I["encirclement_score"]]     = rng.uniform(0.60, 0.95)
            X[i, _I["surrounding_count"]]      = rng.uniform(0.50, 1.00)
            X[i, _I["sustained_proximity_frames"]] = rng.uniform(0.50, 0.90)
        elif threat_type == 2:     # erratic pursuit
            X[i, _I["direction_change"]]       = rng.uniform(0.50, 0.90)
            X[i, _I["velocity_toward_target"]] = rng.uniform(0.65, 1.00)
            X[i, _I["proximity_norm"]]         = rng.uniform(0.05, 0.20)
        else:                      # full convergence
            X[i, _I["velocity_toward_target"]] = rng.uniform(0.80, 1.00)
            X[i, _I["encirclement_score"]]     = rng.uniform(0.50, 0.90)
            X[i, _I["speed_norm"]]             = rng.uniform(0.25, 0.70)
        # Fill remaining features with benign noise
        for j in range(FEATURE_DIM):
            if X[i, j] == 0.0:
                X[i, j] = float(rng.uniform(0.0, 0.25))
    return np.clip(X.astype(np.float32), 0.0, 1.0)


# ── NEW: Pose-aware scenarios ─────────────────────────────────────────────────

def scenario_hug(n: int) -> np.ndarray:
    """Two people hugging — very close but arms symmetric/open, NOT a threat."""
    return _gaussian(n,
        means={
            "proximity_norm":          0.05,    # very close
            "speed_norm":              0.02,    # stationary
            "surrounding_count":       0.15,
            "velocity_toward_target":  0.50,    # neutral
            "arm_extension_score":     0.70,    # arms extended (wrapping)
            "arm_toward_target":       0.55,    # toward each other slightly
            "wrist_proximity_norm":    0.04,    # wrists very close to other
            "body_facing_score":       0.85,    # face-to-face
            "shoulder_raise_score":    0.10,    # shoulders relaxed
            "elbow_angle_score":       0.25,    # elbows open/wrapping
            "pose_symmetry_score":     0.90,    # very symmetric (both arms)
            "pose_confidence":         0.80,
        },
        stds={
            "proximity_norm": 0.03, "arm_extension_score": 0.10,
            "pose_symmetry_score": 0.08, "body_facing_score": 0.10,
        },
    )


def scenario_handshake(n: int) -> np.ndarray:
    """Handshake — one arm extended, bodies side-by-side, NOT a threat."""
    return _gaussian(n,
        means={
            "proximity_norm":          0.12,    # close-ish
            "speed_norm":              0.05,
            "velocity_toward_target":  0.48,    # neutral
            "arm_extension_score":     0.75,    # one arm extended
            "arm_toward_target":       0.65,    # arm toward other person
            "wrist_proximity_norm":    0.06,    # wrist near other
            "body_facing_score":       0.40,    # partially turned (side)
            "shoulder_raise_score":    0.10,    # relaxed
            "elbow_angle_score":       0.30,    # moderately open
            "pose_symmetry_score":     0.45,    # asymmetric (one arm out)
            "pose_confidence":         0.80,
        },
        stds={
            "proximity_norm": 0.05, "arm_extension_score": 0.12,
            "pose_symmetry_score": 0.12, "body_facing_score": 0.12,
        },
    )


def scenario_grab(n: int) -> np.ndarray:
    """Grab — wrist very close to other person, arm extended toward them (THREAT)."""
    return _gaussian(n,
        means={
            "proximity_norm":          0.06,
            "speed_norm":              0.20,
            "velocity_toward_target":  0.80,    # moving toward
            "arm_extension_score":     0.85,    # arm fully extended
            "arm_toward_target":       0.90,    # pointing at victim
            "wrist_proximity_norm":    0.02,    # wrist touching victim
            "body_facing_score":       0.90,    # face-to-face confrontation
            "shoulder_raise_score":    0.50,    # tensed
            "elbow_angle_score":       0.45,    # semi-tight
            "pose_symmetry_score":     0.25,    # very asymmetric (one arm out)
            "pose_confidence":         0.75,
            "sustained_proximity_frames": 0.40,
        },
        stds={
            "proximity_norm": 0.03, "arm_toward_target": 0.08,
            "wrist_proximity_norm": 0.02, "pose_symmetry_score": 0.10,
        },
    )


def scenario_strike(n: int) -> np.ndarray:
    """Strike / punch approach — fast arm extension toward person (THREAT)."""
    return _gaussian(n,
        means={
            "proximity_norm":          0.08,
            "speed_norm":              0.55,    # fast approach
            "velocity_toward_target":  0.90,
            "arm_extension_score":     0.90,    # fully extended strike
            "arm_toward_target":       0.95,    # aimed at person
            "wrist_proximity_norm":    0.03,
            "body_facing_score":       0.85,
            "shoulder_raise_score":    0.65,    # raised aggressively
            "elbow_angle_score":       0.55,    # tight fighting stance
            "pose_symmetry_score":     0.20,    # very asymmetric
            "pose_confidence":         0.70,
        },
        stds={
            "speed_norm": 0.15, "arm_extension_score": 0.08,
            "pose_symmetry_score": 0.10,
        },
    )


def scenario_blocking(n: int) -> np.ndarray:
    """Defensive blocking — arms raised to shield, facing aggressor (THREAT context)."""
    return _gaussian(n,
        means={
            "proximity_norm":          0.10,
            "speed_norm":              0.10,
            "velocity_toward_target":  0.40,    # backing away
            "arm_extension_score":     0.60,    # arms up/out
            "arm_toward_target":       0.50,    # arms up, not toward
            "wrist_proximity_norm":    0.12,
            "body_facing_score":       0.80,    # facing aggressor
            "shoulder_raise_score":    0.70,    # shoulders hunched up
            "elbow_angle_score":       0.70,    # elbows tight, guarding
            "pose_symmetry_score":     0.75,    # both arms up symmetrically
            "pose_confidence":         0.70,
            "sustained_proximity_frames": 0.45,
        },
        stds={
            "shoulder_raise_score": 0.12, "elbow_angle_score": 0.12,
        },
    )


# ---------------------------------------------------------------------------
# Dataset builder
# ---------------------------------------------------------------------------

def build_synthetic_dataset(n_per_class: int = 5_000) -> tuple[np.ndarray, np.ndarray]:
    """
    Assemble balanced synthetic training data.

    Returns:
        X: (N, FEATURE_DIM) float32 feature matrix.
        y: (N,) int8 label vector  (0=safe, 1=threat).
    """
    log.info("Generating synthetic dataset ({n} samples/class)…", n=n_per_class)

    # Safe scenarios (label = 0) — 5 types
    safe_per = n_per_class // 5
    safe = np.vstack([
        scenario_safe_walking(safe_per),
        scenario_standing_alone(safe_per),
        scenario_friendly_group(safe_per),
        scenario_hug(safe_per),
        scenario_handshake(n_per_class - 4 * safe_per),
    ])

    # Threat scenarios (label = 1) — 7 types
    thr_per = n_per_class // 7
    threat = np.vstack([
        scenario_following(thr_per),
        scenario_group_encirclement(thr_per),
        scenario_rush_approach(thr_per),
        scenario_grab(thr_per),
        scenario_strike(thr_per),
        scenario_blocking(thr_per),
        scenario_mixed_threat(n_per_class - 6 * thr_per),
    ])

    X = np.vstack([safe, threat]).astype(np.float32)
    y = np.hstack([
        np.zeros(len(safe), dtype=np.int8),
        np.ones(len(threat), dtype=np.int8),
    ])

    # Shuffle
    perm = rng.permutation(len(X))
    X, y = X[perm], y[perm]

    log.info(
        "Dataset ready | total={t} | safe={s} | threat={th} | features={f}",
        t=len(X), s=int((y == 0).sum()), th=int((y == 1).sum()), f=FEATURE_DIM,
    )
    return X, y


def load_csv_dataset(csv_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """
    Load a user-supplied CSV with FEATURE_KEYS columns + 'label' column.

    Missing feature columns are filled with 0.0.
    Extra columns are silently ignored.
    """
    log.info("Loading CSV dataset from {p}…", p=csv_path)
    df = pd.read_csv(csv_path)

    if "label" not in df.columns:
        raise ValueError(f"CSV must contain a 'label' column. Found: {list(df.columns)}")

    y = df["label"].values.astype(np.int8)

    # Build feature matrix in canonical column order
    X = np.zeros((len(df), FEATURE_DIM), dtype=np.float32)
    for i, key in enumerate(FEATURE_KEYS):
        if key in df.columns:
            X[:, i] = df[key].fillna(0.0).values.astype(np.float32)
        else:
            log.warning("Feature '{k}' not in CSV — filled with 0.", k=key)

    X = np.clip(X, 0.0, 1.0)
    log.info(
        "CSV loaded | rows={r} | safe={s} | threat={t}",
        r=len(X), s=int((y == 0).sum()), t=int((y == 1).sum()),
    )
    return X, y


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(
    X: np.ndarray,
    y: np.ndarray,
    eval_split: float = 0.15,
    output_path: Path = None,
) -> None:
    """
    Train an XGBoost binary classifier and save the booster.

    Hyperparameters are tuned for the 12-feature threat detection problem:
    - max_depth=5: enough capacity without overfitting
    - eta=0.05: conservative learning rate; improves generalisation
    - subsample=0.8 + colsample=0.8: reduce variance
    - scale_pos_weight: handles class imbalance if present
    - eval_metric: AUC + logloss together give threshold-independent signal

    Args:
        X:            Feature matrix (N, FEATURE_DIM).
        y:            Labels (N,).
        eval_split:   Fraction held out for evaluation.
        output_path:  Save path. Defaults to cfg.threat_model_abs_path.
    """
    try:
        import xgboost as xgb
    except ImportError:
        log.error("xgboost not installed. Run: pip install xgboost")
        sys.exit(1)

    from sklearn.model_selection import train_test_split
    from sklearn.metrics import (
        roc_auc_score, average_precision_score,
        classification_report, confusion_matrix,
    )

    output_path = output_path or cfg.threat_model_abs_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Train / eval split ────────────────────────────────────────────────────
    X_tr, X_val, y_tr, y_val = train_test_split(
        X, y, test_size=eval_split, random_state=_RNG_SEED, stratify=y
    )
    log.info(
        "Split | train={tr} | val={v}",
        tr=len(X_tr), v=len(X_val),
    )

    d_train = xgb.DMatrix(X_tr, label=y_tr, feature_names=FEATURE_KEYS)
    d_val   = xgb.DMatrix(X_val, label=y_val, feature_names=FEATURE_KEYS)

    # Class imbalance weight
    pos_count = int((y_tr == 1).sum())
    neg_count = int((y_tr == 0).sum())
    spw = neg_count / max(pos_count, 1)

    params = {
        "objective":        "binary:logistic",
        "eval_metric":      ["auc", "logloss"],
        "eta":              0.05,
        "max_depth":        5,
        "min_child_weight": 3,
        "subsample":        0.80,
        "colsample_bytree": 0.80,
        "scale_pos_weight": spw,
        "seed":             _RNG_SEED,
        "nthread":          -1,   # use all CPU cores
        "verbosity":        1,
    }

    log.info("Training XGBoost | params={p}", p={k: v for k, v in params.items()
                                                  if k != "verbosity"})

    evals_result: dict = {}
    booster = xgb.train(
        params,
        d_train,
        num_boost_round=500,
        evals=[(d_train, "train"), (d_val, "val")],
        early_stopping_rounds=30,
        evals_result=evals_result,
        verbose_eval=50,
    )

    # ── Evaluation ────────────────────────────────────────────────────────────
    y_prob = booster.predict(d_val)
    y_pred = (y_prob >= 0.5).astype(int)

    auc  = roc_auc_score(y_val, y_prob)
    ap   = average_precision_score(y_val, y_prob)
    best = booster.best_iteration

    log.success(
        "Training complete | best_round={r} | ROC-AUC={auc:.4f} | AP={ap:.4f}",
        r=best, auc=auc, ap=ap,
    )

    print("\n" + "=" * 60)
    print(f"  XGBoost Threat Model — Evaluation Report")
    print("=" * 60)
    print(f"  Best round:    {best}")
    print(f"  ROC-AUC:       {auc:.4f}  (1.0 = perfect)")
    print(f"  Avg Precision: {ap:.4f}  (1.0 = perfect)")
    print()
    print("Classification Report (threshold=0.50):")
    print(classification_report(y_val, y_pred,
                                 target_names=["Safe", "Threat"], digits=4))
    print("Confusion Matrix:")
    cm = confusion_matrix(y_val, y_pred)
    print(f"  TN={cm[0,0]:5d}  FP={cm[0,1]:5d}")
    print(f"  FN={cm[1,0]:5d}  TP={cm[1,1]:5d}")
    print()

    # ── Feature importance ────────────────────────────────────────────────────
    importance = booster.get_score(importance_type="gain")
    if importance:
        sorted_imp = sorted(importance.items(), key=lambda x: x[1], reverse=True)
        print("Feature Importance (gain):")
        for fname, score in sorted_imp:
            bar = "█" * int(score / sorted_imp[0][1] * 30)
            print(f"  {fname:<38} {score:8.1f}  {bar}")
    print("=" * 60)

    # ── Save ─────────────────────────────────────────────────────────────────
    booster.save_model(str(output_path))
    size_kb = output_path.stat().st_size // 1024
    log.success("Model saved to {p} ({kb} KB)", p=output_path, kb=size_kb)
    print(f"\n✅  Saved: {output_path}  ({size_kb} KB)")
    print("   The ThreatEngine will load this automatically on next startup.\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Train XGBoost threat classifier for the Women Safety Product."
    )
    p.add_argument("--data",   type=Path, default=None,
                   help="Optional CSV file with labelled real data.")
    p.add_argument("--n",      type=int,  default=5_000,
                   help="Synthetic samples per class (default 5000).")
    p.add_argument("--eval",   action="store_true",
                   help="Show detailed evaluation metrics after training.")
    p.add_argument("--output", type=Path, default=None,
                   help="Output .json path (default: models/threat_xgb.json).")
    p.add_argument("--export-csv", type=Path, default=None,
                   help="Save generated synthetic dataset to a CSV file.")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    # ── Build or load dataset ─────────────────────────────────────────────────
    if args.data and args.data.exists():
        X_csv, y_csv = load_csv_dataset(args.data)
        # Merge synthetic + real (real data is undersampled in practice)
        X_syn, y_syn = build_synthetic_dataset(n_per_class=args.n)
        X = np.vstack([X_syn, X_csv])
        y = np.hstack([y_syn, y_csv])
        log.info("Merged synthetic + real data | total={t}", t=len(X))
    else:
        if args.data:
            log.warning("CSV path not found: {p}. Using synthetic only.", p=args.data)
        X, y = build_synthetic_dataset(n_per_class=args.n)

    # ── Optional CSV export ───────────────────────────────────────────────────
    if args.export_csv:
        df_out = pd.DataFrame(X, columns=FEATURE_KEYS)
        df_out["label"] = y
        df_out.to_csv(args.export_csv, index=False)
        log.info("Synthetic dataset saved to {p}", p=args.export_csv)

    # ── Train ─────────────────────────────────────────────────────────────────
    train(X, y, output_path=args.output)
