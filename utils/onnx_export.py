"""
utils/onnx_export.py — ONNX export utility for YOLOv8 and XGBoost models.

Provides:
  export_yolo_onnx()    — Convert yolov8n.pt → yolov8n.onnx via ultralytics.
  export_xgb_onnx()     — Convert threat_xgb.json → threat_xgb.onnx via
                          sklearn-onnx / onnxmltools (optional dep; graceful skip).
  verify_onnx()         — Run a sanity-check inference on the exported ONNX model
                          using onnxruntime (optional dep; graceful skip).

Why ONNX?
  - ONNXRuntime on CPU is typically 1.3–2× faster than PyTorch CPU for YOLOv8n.
  - TensorRT (NVIDIA GPU) can reach 5–10× over CPU once the engine is built.
  - The ONNX file is a portable archive — deploy on Jetson Nano, Raspberry Pi 5,
    or any edge device without Python/PyTorch.

Usage (CLI):
    python utils/onnx_export.py --model models/yolov8n.pt --imgsz 640
    python utils/onnx_export.py --model models/yolov8n.pt --verify

Usage (programmatic):
    from utils.onnx_export import export_yolo_onnx, verify_onnx
    onnx_path = export_yolo_onnx()
    if onnx_path:
        verify_onnx(onnx_path)
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Optional

from config import cfg
from utils.logger import setup_logging, get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# YOLO → ONNX
# ---------------------------------------------------------------------------

def export_yolo_onnx(
    model_path: Optional[Path] = None,
    imgsz: int = 640,
    opset: int = 17,
    simplify: bool = True,
    dynamic: bool = False,
    half: bool = False,
) -> Optional[Path]:
    """
    Export a YOLOv8 .pt model to ONNX format using ultralytics.

    Args:
        model_path: Path to the .pt file. Defaults to cfg.model_abs_path.
        imgsz:      Square input size for the exported model.
        opset:      ONNX opset version (17 is safe for ORT 1.17+).
        simplify:   Run onnx-simplifier to reduce graph complexity.
        dynamic:    Enable dynamic batch axis (useful for server deployment).
        half:       FP16 quantisation (requires CUDA at export time).

    Returns:
        Path to the .onnx file on success, None on failure.
    """
    model_path = model_path or cfg.model_abs_path

    if not model_path.exists():
        log.error("YOLO model not found at {p}. Cannot export.", p=model_path)
        return None

    onnx_path = model_path.with_suffix(".onnx")

    if onnx_path.exists():
        log.info("ONNX already exists at {p}. Delete it to re-export.", p=onnx_path)
        return onnx_path

    log.info(
        "Exporting YOLO ONNX | src={src} imgsz={sz} opset={op} simplify={s}",
        src=model_path, sz=imgsz, op=opset, s=simplify,
    )

    try:
        from ultralytics import YOLO
        model = YOLO(str(model_path))
        t0 = time.monotonic()
        export_result = model.export(
            format="onnx",
            imgsz=imgsz,
            opset=opset,
            simplify=simplify,
            dynamic=dynamic,
            half=half,
        )
        elapsed = time.monotonic() - t0

        # ultralytics returns the export path as a string
        exported = Path(str(export_result)) if export_result else onnx_path
        if exported.exists():
            size_mb = exported.stat().st_size / 1_048_576
            log.success(
                "YOLO ONNX export complete in {t:.1f}s | {p} ({mb:.1f} MB)",
                t=elapsed, p=exported, mb=size_mb,
            )
            return exported
        else:
            log.error("Export finished but ONNX file not found at {p}.", p=onnx_path)
            return None

    except ImportError:
        log.error("ultralytics not installed. Cannot export ONNX.")
        return None
    except Exception:
        log.exception("YOLO ONNX export failed.")
        return None


# ---------------------------------------------------------------------------
# XGBoost → ONNX  (optional — requires onnxmltools + skl2onnx)
# ---------------------------------------------------------------------------

def export_xgb_onnx(
    model_path: Optional[Path] = None,
    n_features: int = 12,
) -> Optional[Path]:
    """
    Convert the XGBoost threat model to ONNX using onnxmltools.

    This is entirely optional — the system runs without it.  Install:
        pip install onnxmltools skl2onnx

    Args:
        model_path: Path to threat_xgb.json. Defaults to cfg.threat_model_abs_path.
        n_features: Number of input features (must match training schema).

    Returns:
        Path to the .onnx file on success, None on failure.
    """
    model_path = model_path or cfg.threat_model_abs_path

    if not model_path.exists():
        log.warning("XGBoost model not found at {p}. Skipping ONNX export.", p=model_path)
        return None

    onnx_path = model_path.with_suffix(".onnx")
    if onnx_path.exists():
        log.info("XGBoost ONNX already exists at {p}.", p=onnx_path)
        return onnx_path

    try:
        import xgboost as xgb
        from onnxmltools.convert import convert_xgboost
        from onnxmltools.convert.common.data_types import FloatTensorType

        booster = xgb.Booster()
        booster.load_model(str(model_path))

        initial_type = [("float_input", FloatTensorType([None, n_features]))]
        onnx_model = convert_xgboost(
            booster, initial_types=initial_type, target_opset=17
        )

        with open(onnx_path, "wb") as f:
            f.write(onnx_model.SerializeToString())

        size_mb = onnx_path.stat().st_size / 1_048_576
        log.success(
            "XGBoost ONNX export complete | {p} ({mb:.2f} MB)",
            p=onnx_path, mb=size_mb,
        )
        return onnx_path

    except ImportError as e:
        log.warning(
            "XGBoost ONNX export skipped (missing: {e}). "
            "Install onnxmltools + skl2onnx to enable.",
            e=e,
        )
        return None
    except Exception:
        log.exception("XGBoost ONNX export failed.")
        return None


# ---------------------------------------------------------------------------
# ONNX model verifier
# ---------------------------------------------------------------------------

def verify_onnx(
    onnx_path: Path,
    input_shape: Optional[tuple] = None,
) -> bool:
    """
    Run a smoke-test inference on an exported ONNX model via onnxruntime.

    For YOLO models the default input shape is (1, 3, 640, 640) NCHW float32.
    For XGBoost threat models the shape is (1, 12) float32.

    Args:
        onnx_path:   Path to the .onnx file.
        input_shape: Override input shape tuple. Auto-detected if None.

    Returns:
        True if inference succeeded without error, False otherwise.
    """
    try:
        import onnxruntime as ort
        import numpy as np

        log.info("Verifying ONNX model: {p}", p=onnx_path)
        t0 = time.monotonic()

        sess_opts = ort.SessionOptions()
        sess_opts.log_severity_level = 3   # suppress verbose ORT logs
        session = ort.InferenceSession(
            str(onnx_path),
            sess_options=sess_opts,
            providers=["CPUExecutionProvider"],
        )

        input_meta = session.get_inputs()[0]
        if input_shape is None:
            # Replace any dynamic (-1 / None) dims with 1
            shape = tuple(d if isinstance(d, int) and d > 0 else 1
                          for d in input_meta.shape)
        else:
            shape = input_shape

        dummy = np.random.rand(*shape).astype(np.float32)
        outputs = session.run(None, {input_meta.name: dummy})

        elapsed_ms = (time.monotonic() - t0) * 1000
        log.success(
            "ONNX verify OK | {p} | input={shape} | "
            "output_shapes={out} | latency={ms:.1f}ms",
            p=onnx_path.name,
            shape=shape,
            out=[list(o.shape) for o in outputs],
            ms=elapsed_ms,
        )
        return True

    except ImportError:
        log.warning("onnxruntime not installed. Skipping ONNX verification.")
        return False
    except Exception:
        log.exception("ONNX verification failed for {p}.", p=onnx_path)
        return False


# ---------------------------------------------------------------------------
# Benchmark helper
# ---------------------------------------------------------------------------

def benchmark_onnx(
    onnx_path: Path,
    n_runs: int = 100,
    input_shape: Optional[tuple] = None,
) -> Optional[dict]:
    """
    Measure average inference latency of an ONNX model over n_runs.

    Returns a dict with mean/min/max/p95 latency in ms, or None on error.
    """
    try:
        import onnxruntime as ort
        import numpy as np

        sess_opts = ort.SessionOptions()
        sess_opts.log_severity_level = 3
        session = ort.InferenceSession(
            str(onnx_path),
            sess_options=sess_opts,
            providers=["CPUExecutionProvider"],
        )
        input_meta = session.get_inputs()[0]
        if input_shape is None:
            shape = tuple(d if isinstance(d, int) and d > 0 else 1
                          for d in input_meta.shape)
        else:
            shape = input_shape

        dummy = np.random.rand(*shape).astype(np.float32)

        # Warm-up
        for _ in range(5):
            session.run(None, {input_meta.name: dummy})

        # Timed runs
        latencies = []
        for _ in range(n_runs):
            t0 = time.monotonic()
            session.run(None, {input_meta.name: dummy})
            latencies.append((time.monotonic() - t0) * 1000)

        latencies.sort()
        result = {
            "n_runs":   n_runs,
            "mean_ms":  round(sum(latencies) / len(latencies), 2),
            "min_ms":   round(latencies[0], 2),
            "max_ms":   round(latencies[-1], 2),
            "p50_ms":   round(latencies[len(latencies) // 2], 2),
            "p95_ms":   round(latencies[int(len(latencies) * 0.95)], 2),
        }

        log.info(
            "ONNX benchmark {n} | mean={m}ms p50={p50}ms p95={p95}ms "
            "min={mn}ms max={mx}ms",
            n=onnx_path.name,
            m=result["mean_ms"], p50=result["p50_ms"], p95=result["p95_ms"],
            mn=result["min_ms"], mx=result["max_ms"],
        )
        return result

    except ImportError:
        log.warning("onnxruntime not installed. Cannot benchmark.")
        return None
    except Exception:
        log.exception("ONNX benchmark failed.")
        return None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    setup_logging(cfg.log_abs_dir, cfg.LOG_LEVEL)

    parser = argparse.ArgumentParser(description="ONNX Export Utility")
    parser.add_argument(
        "--model", type=Path, default=None,
        help="Path to .pt YOLO model (default: cfg.MODEL_PATH)",
    )
    parser.add_argument(
        "--imgsz", type=int, default=640,
        help="Export input size (default 640)",
    )
    parser.add_argument(
        "--opset", type=int, default=17,
        help="ONNX opset version (default 17)",
    )
    parser.add_argument(
        "--no-simplify", action="store_true",
        help="Skip onnx-simplifier pass",
    )
    parser.add_argument(
        "--dynamic", action="store_true",
        help="Enable dynamic batch axis",
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Run smoke-test inference after export",
    )
    parser.add_argument(
        "--benchmark", type=int, default=0, metavar="N",
        help="Run N inference iterations to measure latency",
    )
    parser.add_argument(
        "--xgb", action="store_true",
        help="Also export XGBoost threat model to ONNX",
    )
    args = parser.parse_args()

    # YOLO export
    onnx = export_yolo_onnx(
        model_path=args.model,
        imgsz=args.imgsz,
        opset=args.opset,
        simplify=not args.no_simplify,
        dynamic=args.dynamic,
    )

    if onnx:
        if args.verify:
            verify_onnx(onnx)
        if args.benchmark > 0:
            benchmark_onnx(onnx, n_runs=args.benchmark,
                           input_shape=(1, 3, args.imgsz, args.imgsz))

    # XGBoost export (optional)
    if args.xgb:
        export_xgb_onnx()
