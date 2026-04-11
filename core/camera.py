"""
core/camera.py — Thread-safe, auto-reconnecting camera abstraction.

Wraps OpenCV VideoCapture in a background reader thread so the main loop
always gets the *latest* frame (no queue build-up) and never blocks on I/O.

Usage:

    from core.camera import Camera
    cam = Camera()
    cam.start()

    while cam.is_running():
        ok, frame = cam.read()
        if ok:
            cv2.imshow("feed", frame)

    cam.stop()

Key design decisions:
- Daemon thread: dies automatically when the main process exits.
- Lock-free latest-frame slot: thread writes, caller reads — no queue lag.
- Exponential back-off on reconnect up to CAMERA_RECONNECT_DELAY * 4.
- Emits structured loguru events at every state transition.
"""

from __future__ import annotations

import threading
import time
from typing import Optional, Tuple, Union

import cv2
import numpy as np

from config import cfg
from utils.logger import get_logger

log = get_logger(__name__)


class Camera:
    """
    Thread-safe camera wrapper with automatic reconnection.

    Args:
        source:  Camera index (int) or URL / file path (str).
                 Defaults to cfg.CAMERA_SOURCE.
        width:   Capture width.  Defaults to cfg.CAMERA_WIDTH.
        height:  Capture height. Defaults to cfg.CAMERA_HEIGHT.
        fps:     Target capture FPS. Defaults to cfg.CAMERA_FPS.
    """

    def __init__(
        self,
        source: Union[int, str, None] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[int] = None,
    ) -> None:
        self._source: Union[int, str] = source if source is not None else cfg.CAMERA_SOURCE
        self._width: int = width or cfg.CAMERA_WIDTH
        self._height: int = height or cfg.CAMERA_HEIGHT
        self._fps: int = fps or cfg.CAMERA_FPS

        self._cap: Optional[cv2.VideoCapture] = None
        self._frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()

        self._running = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Metrics exposed for the dashboard
        self.frames_captured: int = 0
        self.reconnect_count: int = 0
        self._last_frame_time: float = 0.0

        log.info("Camera created | source={src} | {w}x{h} @ {fps}fps",
                 src=self._source, w=self._width, h=self._height, fps=self._fps)

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> "Camera":
        """Open the camera and launch the background reader thread."""
        if self._running.is_set():
            log.warning("Camera.start() called but camera is already running.")
            return self

        if not self._open():
            raise RuntimeError(
                f"Failed to open camera source '{self._source}' on first attempt."
            )

        self._running.set()
        self._thread = threading.Thread(
            target=self._reader_loop,
            name="CameraReader",
            daemon=True,   # auto-killed when main process exits
        )
        self._thread.start()
        log.info("Camera reader thread started.")
        return self

    def stop(self) -> None:
        """Signal the reader thread to stop and release the capture device."""
        log.info("Camera stopping…")
        self._running.clear()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._release()
        log.info("Camera stopped. Total frames captured: {n}", n=self.frames_captured)

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Return the latest captured frame.

        Returns:
            (True, frame_ndarray)  if a frame is available.
            (False, None)          if no frame has been grabbed yet.
        """
        with self._frame_lock:
            if self._frame is None:
                return False, None
            return True, self._frame.copy()

    def is_running(self) -> bool:
        """True while the background reader is active."""
        return self._running.is_set()

    @property
    def actual_fps(self) -> float:
        """Instantaneous FPS based on time since last frame (rough estimate)."""
        elapsed = time.monotonic() - self._last_frame_time
        if elapsed == 0:
            return 0.0
        return 1.0 / elapsed

    @property
    def resolution(self) -> Tuple[int, int]:
        """Return (width, height) as reported by the capture device."""
        if self._cap and self._cap.isOpened():
            w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            return w, h
        return self._width, self._height

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _open(self) -> bool:
        """
        Attempt to open the capture device.

        Returns True on success, False on failure.
        """
        self._release()
        log.debug("Opening camera source: {src}", src=self._source)
        try:
            self._cap = cv2.VideoCapture(self._source)
            if not self._cap.isOpened():
                log.error("cv2.VideoCapture failed to open source: {src}", src=self._source)
                return False

            # Apply desired settings (best-effort; hardware may ignore some)
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
            self._cap.set(cv2.CAP_PROP_FPS, self._fps)

            # Reduce internal buffer to minimise latency (1 frame)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = self._cap.get(cv2.CAP_PROP_FPS)
            log.info(
                "Camera opened | actual {w}x{h} @ {fps:.1f}fps",
                w=actual_w, h=actual_h, fps=actual_fps,
            )
            return True

        except Exception:
            log.exception("Exception while opening camera source: {src}", src=self._source)
            return False

    def _release(self) -> None:
        """Safely release the OpenCV capture object."""
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _reader_loop(self) -> None:
        """
        Background thread: continuously grab frames and store the latest one.

        Handles connection drops with exponential back-off reconnect.
        """
        consecutive_failures = 0
        reconnect_delay = cfg.CAMERA_RECONNECT_DELAY

        log.debug("Camera reader loop entered.")

        while self._running.is_set():
            if self._cap is None or not self._cap.isOpened():
                # ── Reconnect logic ──────────────────────────────────────────
                if self.reconnect_count >= cfg.CAMERA_MAX_RECONNECT:
                    log.critical(
                        "Max reconnect attempts ({n}) reached. Stopping camera.",
                        n=cfg.CAMERA_MAX_RECONNECT,
                    )
                    self._running.clear()
                    break

                self.reconnect_count += 1
                log.warning(
                    "Camera not available. Reconnect attempt {n}/{max} in {d}s…",
                    n=self.reconnect_count,
                    max=cfg.CAMERA_MAX_RECONNECT,
                    d=reconnect_delay,
                )
                time.sleep(reconnect_delay)
                # Exponential back-off, capped at 4× the base delay
                reconnect_delay = min(
                    reconnect_delay * 2, cfg.CAMERA_RECONNECT_DELAY * 4
                )

                if self._open():
                    log.info("Camera reconnected successfully.")
                    reconnect_delay = cfg.CAMERA_RECONNECT_DELAY  # reset back-off
                    consecutive_failures = 0
                continue

            # ── Normal frame grab ────────────────────────────────────────────
            ret, frame = self._cap.read()

            if not ret or frame is None:
                consecutive_failures += 1
                log.debug(
                    "Frame grab failed (consecutive={n}).", n=consecutive_failures
                )
                if consecutive_failures >= 5:
                    log.warning("5 consecutive frame failures — releasing capture for reconnect.")
                    self._release()
                    consecutive_failures = 0
                continue

            # Reset failure counter on success
            consecutive_failures = 0

            # Atomic slot update — readers always see the latest complete frame
            with self._frame_lock:
                self._frame = frame

            self.frames_captured += 1
            self._last_frame_time = time.monotonic()

        log.debug("Camera reader loop exited.")

    # ── Context manager support ───────────────────────────────────────────────

    def __enter__(self) -> "Camera":
        return self.start()

    def __exit__(self, *_) -> None:
        self.stop()
