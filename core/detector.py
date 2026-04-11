"""
core/detector.py — YOLOv8 person detector with BoT-SORT tracking.

Responsibilities:
  1. Load / download YOLOv8n (or any configured variant) at startup.
  2. Run inference on every frame, filtering to COCO class 0 (person) only.
  3. Return a clean list of TrackedPerson dataclass instances per frame.
  4. Optionally export an ONNX model for future TensorRT / ORT acceleration.

Design notes:
  - Uses ultralytics' built-in tracker (botsort.yaml / bytetrack.yaml).
  - Frame skipping (SKIP_FRAMES) keeps throughput high on weak hardware.
  - All heavy objects (model, tracker) are created once in __init__.
  - Thread-safe: Detector is intended to run in the main loop thread.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
from ultralytics import YOLO

from config import cfg
from utils.logger import get_logger

log = get_logger(__name__)

# COCO class index for "person"
_PERSON_CLASS_ID = 0

# Minimum bounding box area (px²) to accept a detection — rejects tiny noise
_MIN_PERSON_AREA: int = 500   # ~22×22 px

# Minimum mean keypoint confidence — detections below this are likely background
_MIN_POSE_CONFIDENCE: float = 0.2


# ---------------------------------------------------------------------------
# Public dataclass returned per tracked person
# ---------------------------------------------------------------------------
@dataclass
class TrackedPerson:
    """Snapshot of one tracked person in a single frame."""

    track_id: int               # persistent ID assigned by BoT-SORT
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2) in pixel coords
    confidence: float           # YOLO detection confidence [0, 1]
    frame_idx: int              # absolute frame counter
    timestamp: float            # time.monotonic() at detection
    # Pose keypoints: shape (17, 3) = [x, y, conf] per COCO keypoint.
    # None when the pose model is not loaded or keypoints are unavailable.
    keypoints: Optional[np.ndarray] = None

    # Derived convenience properties
    @property
    def center(self) -> Tuple[float, float]:
        """Bounding-box centre (cx, cy)."""
        x1, y1, x2, y2 = self.bbox
        return (x1 + x2) / 2.0, (y1 + y2) / 2.0

    @property
    def area(self) -> int:
        """Bounding-box area in pixels²."""
        x1, y1, x2, y2 = self.bbox
        return max(0, x2 - x1) * max(0, y2 - y1)

    @property
    def height(self) -> int:
        """Bounding-box height — proxy for depth / scale."""
        return max(0, self.bbox[3] - self.bbox[1])


# ---------------------------------------------------------------------------
# Detector class
# ---------------------------------------------------------------------------
class Detector:
    """
    YOLOv8 + BoT-SORT person detector / tracker.

    Args:
        skip_frames:  Run inference every N frames; intermediate frames
                      return the previous result unchanged. 0 = every frame.
    """

    def __init__(self, skip_frames: int = 0) -> None:
        self._skip_frames = max(0, skip_frames)
        self._frame_count: int = 0
        self._last_results: List[TrackedPerson] = []
        self._inference_times: List[float] = []

        self._model: Optional[YOLO] = None
        self._device = self._resolve_device()
        self._load_model()

        if cfg.EXPORT_ONNX:
            self._export_onnx()

    def _resolve_device(self) -> str:
        """Fallback to CPU if CUDA is requested but PyTorch lacks CUDA support."""
        device = str(cfg.MODEL_DEVICE).lower()
        if device in ("cuda", "0", "cuda:0"):
            import torch
            if not torch.cuda.is_available():
                log.warning("CUDA requested but not available. Falling back to CPU for inference.")
                return "cpu"
        return str(cfg.MODEL_DEVICE)

    # ── Model lifecycle ───────────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Download (if needed) and load the YOLO model."""
        model_path = cfg.model_abs_path
        log.info("Loading YOLO model from: {p}", p=model_path)
        try:
            self._model = YOLO(str(model_path))
            # Warm-up pass: avoids first-frame latency spike
            dummy = np.zeros((cfg.MODEL_IMGSZ, cfg.MODEL_IMGSZ, 3), dtype=np.uint8)
            use_fp16 = str(self._device).lower() in ("cuda", "0", "cuda:0")
            self._model.predict(
                dummy,
                conf=cfg.MODEL_CONFIDENCE,
                iou=cfg.MODEL_IOU,
                device=self._device,
                half=use_fp16,
                verbose=False,
            )
            log.info("YOLO model loaded and warmed up. Device: {d} (FP16: {h})", d=self._device, h=use_fp16)
        except Exception:
            log.exception("Failed to load YOLO model from {p}.", p=model_path)
            raise

    def _export_onnx(self) -> None:
        """Export the loaded model to ONNX format (future TensorRT/ORT path)."""
        if self._model is None:
            log.error("Cannot export ONNX: model not loaded.")
            return
        onnx_path = cfg.model_abs_path.with_suffix(".onnx")
        if onnx_path.exists():
            log.info("ONNX model already exists at {p}. Skipping export.", p=onnx_path)
            return
        log.info("Exporting ONNX model to {p} …", p=onnx_path)
        try:
            self._model.export(format="onnx", imgsz=cfg.MODEL_IMGSZ, simplify=True)
            log.success("ONNX export complete: {p}", p=onnx_path)
        except Exception:
            log.exception("ONNX export failed.")

    # ── Inference ─────────────────────────────────────────────────────────────

    def detect(self, frame: np.ndarray) -> List[TrackedPerson]:
        """
        Run detection + tracking on a single BGR frame.

        Args:
            frame: BGR image from OpenCV.

        Returns:
            List of TrackedPerson instances (may be empty).
            Returns the *previous* list unchanged when a frame is skipped.
        """
        self._frame_count += 1

        # Frame skipping: re-use last result for intermediate frames
        if self._skip_frames > 0 and (self._frame_count % (self._skip_frames + 1)) != 0:
            return self._last_results

        if self._model is None:
            log.error("Detector.detect() called but model is not loaded.")
            return []

        t0 = time.monotonic()

        try:
            use_fp16 = str(self._device).lower() in ("cuda", "0", "cuda:0")
            results = self._model.track(
                frame,
                persist=cfg.TRACKER_PERSIST,
                tracker=cfg.TRACKER_CONFIG,
                conf=cfg.MODEL_CONFIDENCE,
                iou=cfg.MODEL_IOU,
                classes=[_PERSON_CLASS_ID],
                device=self._device,
                half=use_fp16,
                imgsz=cfg.MODEL_IMGSZ,
                verbose=False,
            )
        except Exception:
            log.exception("Error during YOLO inference on frame {n}.", n=self._frame_count)
            return self._last_results  # gracefully return stale data

        elapsed_ms = (time.monotonic() - t0) * 1000
        self._inference_times.append(elapsed_ms)
        if len(self._inference_times) > 100:
            self._inference_times.pop(0)

        tracked_persons = self._parse_results(results)
        self._last_results = tracked_persons

        log.debug(
            "Frame {n} | {k} persons | inference {ms:.1f}ms",
            n=self._frame_count,
            k=len(tracked_persons),
            ms=elapsed_ms,
        )
        return tracked_persons

    def _parse_results(self, results) -> List[TrackedPerson]:
        """
        Convert ultralytics Results object into a list of TrackedPerson.

        For pose models, results[0].keypoints contains (N, 17, 3) tensor
        with [x, y, confidence] per COCO keypoint per person.
        """
        persons: List[TrackedPerson] = []

        if not results or results[0].boxes is None:
            return persons

        boxes = results[0].boxes
        now = time.monotonic()

        ids   = boxes.id
        xyxy  = boxes.xyxy.cpu().numpy()  if boxes.xyxy  is not None else []
        confs = boxes.conf.cpu().numpy()  if boxes.conf  is not None else []

        # Pose keypoints: tensor (N, 17, 3) or None for detection-only models
        kpts_data = results[0].keypoints
        kpts_xy   = (
            kpts_data.data.cpu().numpy()   # (N, 17, 3)
            if kpts_data is not None and kpts_data.data is not None
            else None
        )

        for i, (box, conf) in enumerate(zip(xyxy, confs)):
            track_id = int(ids[i].item()) if ids is not None else -1
            x1, y1, x2, y2 = map(int, box)

            # ── Filter: minimum bbox area (reject noise / partial detections) ──
            area = max(0, x2 - x1) * max(0, y2 - y1)
            if area < _MIN_PERSON_AREA:
                continue

            kp: Optional[np.ndarray] = None
            if kpts_xy is not None and i < len(kpts_xy):
                kp_raw = kpts_xy[i].astype(np.float32)   # (17, 3)
                # ── Filter: reject detections with very low pose confidence ──
                mean_kp_conf = float(kp_raw[:, 2].mean())
                if mean_kp_conf < _MIN_POSE_CONFIDENCE:
                    continue   # likely a background object, not a real person
                kp = kp_raw

            persons.append(
                TrackedPerson(
                    track_id=track_id,
                    bbox=(x1, y1, x2, y2),
                    confidence=float(conf),
                    frame_idx=self._frame_count,
                    timestamp=now,
                    keypoints=kp,
                )
            )

        return persons

    # ── Visualisation helper ──────────────────────────────────────────────────

    @staticmethod
    def draw(
        frame: np.ndarray,
        persons: List[TrackedPerson],
        color: Tuple[int, int, int] = (0, 255, 0),
        threat_colors: Optional[dict] = None,
    ) -> np.ndarray:
        """
        Draw bounding boxes + track IDs on a copy of `frame`.

        Args:
            frame:         BGR input frame.
            persons:       List of TrackedPerson from detect().
            color:         Default box colour (BGR).
            threat_colors: Optional dict {track_id: (B,G,R)} to override colour
                           per track (used by the threat engine).

        Returns:
            Annotated BGR frame (copy).
        """
        out = frame.copy()
        threat_colors = threat_colors or {}

        for p in persons:
            x1, y1, x2, y2 = p.bbox
            c = threat_colors.get(p.track_id, color)

            # Bounding box
            cv2.rectangle(out, (x1, y1), (x2, y2), c, 2)

            # Label: ID + confidence
            label = f"ID:{p.track_id}  {p.confidence:.2f}"
            label_y = max(y1 - 8, 12)
            cv2.putText(
                out, label, (x1, label_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, c, 2, cv2.LINE_AA,
            )

        # Frame info overlay
        cv2.putText(
            out,
            f"Persons: {len(persons)}",
            (10, 24),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA,
        )
        return out

    # ── Statistics ────────────────────────────────────────────────────────────

    @property
    def avg_inference_ms(self) -> float:
        """Rolling average inference latency in milliseconds."""
        if not self._inference_times:
            return 0.0
        return sum(self._inference_times) / len(self._inference_times)

    @property
    def frame_count(self) -> int:
        return self._frame_count
