"""
mobile_edge.py — Real-time edge AI processor for mobile phone camera feed.

Connects to the SafeSphere coordinator via WebSocket, receives live JPEG frames
from a mobile phone camera, and runs the FULL AI pipeline:

    JPEG frame (from phone)
      → OpenCV decode
      → YOLOv8n person detection + BoT-SORT tracking
      → TrackManager (per-track state history)
      → ThreatEngine (XGBoost + heuristic scoring)
      → AlertDispatcher (local email + sound alerts)
      → Coordinator API (multi-stakeholder push notifications)
      → Annotated frame → back to coordinator → dashboard

This is the REAL detection pipeline — same AI models as main.py, just reading
frames from WebSocket instead of a local camera/RTSP feed.

Run:
    1. Start coordinator:  uvicorn coordinator.main:app --host 0.0.0.0 --port 8000
    2. Start this:         python mobile_edge.py
    3. Open phone:         http://<your-pc-ip>:8000/camera
    4. Start dashboard:    cd dashboard && npm run dev

Options:
    python mobile_edge.py --coordinator http://192.168.1.100:8000
    python mobile_edge.py --no-display          # headless mode
    python mobile_edge.py --target-fps 15       # auto-tuner target
"""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
import time
import threading
from pathlib import Path
from typing import Dict, Optional

import cv2
import numpy as np

# SafeSphere imports
from config import cfg
from utils.logger import setup_logging, get_logger
from utils.alerts import AlertDispatcher, AlertEvent
from utils.performance import PerformanceMonitor, FrameSkipTuner
from core.detector import Detector
from core.tracker import TrackManager
from core.threat import ThreatEngine, ThreatResult, THREAT_COLORS

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
setup_logging(
    log_dir=cfg.log_abs_dir,
    level=cfg.LOG_LEVEL,
    rotation=cfg.LOG_ROTATION,
    retention=cfg.LOG_RETENTION,
)
log = get_logger("mobile_edge")

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
_shutdown = False


def _signal_handler(sig, _frame):
    global _shutdown
    log.warning("Signal {s} — shutting down.", s=sig)
    _shutdown = True


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

# ---------------------------------------------------------------------------
# Data directory (same as main.py — Streamlit dashboard reads these too)
# ---------------------------------------------------------------------------
_DATA_DIR = Path("data")
_STATE_FILE = _DATA_DIR / "dashboard_state.json"
_FRAME_FILE = _DATA_DIR / "latest_frame.jpg"


def _write_frame(frame: np.ndarray) -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = str(_FRAME_FILE) + ".tmp"
        cv2.imwrite(tmp, frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        import os
        os.replace(tmp, str(_FRAME_FILE))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Frame annotation (same as main.py)
# ---------------------------------------------------------------------------

def annotate(
    frame: np.ndarray,
    persons: list,
    threat_results: Dict[int, ThreatResult],
    monitor: PerformanceMonitor,
    summary: Dict[str, int],
) -> np.ndarray:
    out = frame.copy()
    color_map = ThreatEngine.build_color_map(threat_results)

    for p in persons:
        x1, y1, x2, y2 = p.bbox
        color = color_map.get(p.track_id, THREAT_COLORS["NONE"])
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

        r = threat_results.get(p.track_id)
        if r:
            label = f"ID:{p.track_id} {r.threat_level} {r.threat_score:.2f}"
            if hasattr(r, "interaction_type") and r.interaction_type != "NEUTRAL":
                label += f" [{r.interaction_type}]"
        else:
            label = f"ID:{p.track_id}"

        cv2.putText(out, label, (x1, max(y1 - 8, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)

    perf = monitor.report()
    h, w = out.shape[:2]

    # Stats overlay
    stats = [
        f"FPS:{perf['fps']:.1f}  inf:{perf['avg_inference_ms']:.0f}ms",
        f"Persons:{len(persons)}  H:{summary.get('HIGH',0)} M:{summary.get('MEDIUM',0)} L:{summary.get('LOW',0)}",
        "Mobile Camera Feed",
    ]
    for i, txt in enumerate(stats):
        cv2.putText(out, txt, (10, 22 + i * 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 220, 255), 2, cv2.LINE_AA)

    # Danger banner
    if summary.get("HIGH", 0) > 0:
        ids_high = [str(t) for t, r in threat_results.items() if r.threat_level == "HIGH"]
        cv2.rectangle(out, (0, h - 40), (w, h), (0, 0, 180), -1)
        banner = f"!!! HIGH THREAT Tracks: {', '.join(ids_high)} !!!"
        cv2.putText(out, banner, (10, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)

    return out


# ---------------------------------------------------------------------------
# WebSocket frame receiver thread
# ---------------------------------------------------------------------------

class FrameReceiver:
    """Receives JPEG frames from coordinator WebSocket in a background thread."""

    def __init__(self, ws_url: str):
        self._url = ws_url
        self._latest_frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self.frames_received = 0

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        log.info("Frame receiver started | url={u}", u=self._url)

    def stop(self):
        self._running = False

    @property
    def connected(self) -> bool:
        return self._connected

    def read(self):
        with self._lock:
            if self._latest_frame is not None:
                frame = self._latest_frame.copy()
                return True, frame
            return False, None

    def _run_loop(self):
        """Run async WebSocket receiver in its own event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._ws_loop())

    async def _ws_loop(self):
        """Connect to coordinator and receive frames."""
        import websockets

        while self._running:
            try:
                log.info("Connecting to {u}...", u=self._url)
                async with websockets.connect(self._url, max_size=10_000_000) as ws:
                    self._connected = True
                    log.info("Connected to coordinator WebSocket.")

                    while self._running:
                        try:
                            data = await asyncio.wait_for(ws.recv(), timeout=5.0)

                            if isinstance(data, bytes):
                                # Decode JPEG → numpy array
                                arr = np.frombuffer(data, dtype=np.uint8)
                                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

                                if frame is not None:
                                    with self._lock:
                                        self._latest_frame = frame
                                    self.frames_received += 1

                        except asyncio.TimeoutError:
                            # No frame in 5s — phone might be paused
                            continue

            except Exception as e:
                self._connected = False
                log.debug("WebSocket connection failed: {e} — retrying in 2s", e=str(e))
                await asyncio.sleep(2.0)


# ---------------------------------------------------------------------------
# WebSocket result sender
# ---------------------------------------------------------------------------

class ResultSender:
    """Sends processed frames + results back to coordinator."""

    def __init__(self, ws_url: str):
        self._url = ws_url
        self._queue: list = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def send_frame(self, frame: np.ndarray):
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        with self._lock:
            self._queue = [buf.tobytes()]  # only keep latest

    def send_result(self, result: dict):
        with self._lock:
            self._queue.append(json.dumps(result))

    def _run_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._ws_loop())

    async def _ws_loop(self):
        import websockets

        while self._running:
            try:
                async with websockets.connect(self._url, max_size=10_000_000) as ws:
                    log.info("Result sender connected.")

                    while self._running:
                        items = []
                        with self._lock:
                            items = self._queue.copy()
                            self._queue.clear()

                        for item in items:
                            try:
                                if isinstance(item, bytes):
                                    await ws.send(item)
                                else:
                                    await ws.send(item)
                            except Exception:
                                break

                        await asyncio.sleep(0.05)

            except Exception:
                await asyncio.sleep(2.0)


# ---------------------------------------------------------------------------
# Coordinator alert poster
# ---------------------------------------------------------------------------

def post_alert_to_coordinator(
    coordinator_url: str,
    result: ThreatResult,
    camera_id: Optional[str] = None,
):
    """Post a threat alert to the coordinator API."""
    import requests

    try:
        body = {
            "camera_id": camera_id,
            "track_id": result.track_id,
            "threat_level": result.threat_level,
            "threat_score": result.threat_score,
            "alert_type": "threat",
            "location_name": "Mobile Camera Feed",
            "details": json.dumps({
                "source": "mobile_edge",
                "interaction_type": getattr(result, "interaction_type", "NEUTRAL"),
            }),
        }
        requests.post(
            f"{coordinator_url}/api/v1/alerts",
            json=body,
            timeout=2.0,
        )
    except Exception:
        log.debug("Alert post to coordinator failed (non-critical).")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="SafeSphere Mobile Edge Processor")
    p.add_argument("--coordinator", default="http://localhost:8000",
                   help="Coordinator base URL")
    p.add_argument("--no-display", action="store_true",
                   help="Headless mode — no OpenCV window")
    p.add_argument("--target-fps", type=float, default=25.0,
                   help="Target FPS for auto-tuner")
    p.add_argument("--skip", type=int, default=-1,
                   help="Force frame skip (-1 = auto)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    coordinator = args.coordinator.rstrip("/")
    ws_base = coordinator.replace("http://", "ws://").replace("https://", "wss://")

    log.info("=" * 64)
    log.info("  SafeSphere Mobile Edge Processor")
    log.info("=" * 64)
    log.info("Coordinator: {u}", u=coordinator)
    log.info("Camera page: {u}/camera", u=coordinator)
    log.info("")
    log.info("Open the camera page on your phone to start streaming!")
    log.info("")

    # ── Init AI pipeline ────────────────────────────────────────────────────
    init_skip = args.skip if args.skip >= 0 else 0
    use_auto_tuner = args.skip < 0

    log.info("Initialising Detector (skip={s})...", s=init_skip)
    detector = Detector(skip_frames=init_skip)

    log.info("Initialising TrackManager...")
    track_manager = TrackManager()

    # We'll set frame dimensions after first frame
    threat_engine = None
    fw, fh = 640, 480

    log.info("Initialising AlertDispatcher...")
    dispatcher = AlertDispatcher()

    monitor = PerformanceMonitor(fps_window=60)
    tuner = FrameSkipTuner(
        target_fps=args.target_fps,
        tolerance=2.0,
        window=30,
        initial_skip=init_skip,
        verbose=True,
    )

    # ── Start frame receiver ────────────────────────────────────────────────
    receiver = FrameReceiver(f"{ws_base}/ws/edge-feed")
    receiver.start()

    # ── Start result sender ─────────────────────────────────────────────────
    sender = ResultSender(f"{ws_base}/ws/edge-feed")
    sender.start()

    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    threat_results: Dict[int, ThreatResult] = {}
    summary: Dict[str, int] = {"NONE": 0, "LOW": 0, "MEDIUM": 0, "HIGH": 0}
    last_status_time = time.time()

    log.info("Pipeline ready. Waiting for frames from phone camera...")

    # ── Frame loop ──────────────────────────────────────────────────────────
    while not _shutdown:
        ok, frame = receiver.read()
        if not ok:
            # No frame yet — wait a bit
            time.sleep(0.01)

            # Show waiting screen
            if not args.no_display:
                waiting = np.zeros((480, 640, 3), dtype=np.uint8)
                status = "Connected" if receiver.connected else "Waiting for connection..."
                cv2.putText(waiting, "SafeSphere Mobile Edge", (120, 200),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 220, 255), 2)
                cv2.putText(waiting, status, (200, 260),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 100, 100), 1)
                cv2.putText(waiting, f"Frames received: {receiver.frames_received}", (200, 300),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
                cv2.imshow("SafeSphere — Mobile Edge", waiting)
                key = cv2.waitKey(100) & 0xFF
                if key == ord("q"):
                    break
            continue

        # ── First frame: init threat engine with correct dimensions ─────
        if threat_engine is None:
            fh, fw = frame.shape[:2]
            log.info("First frame received: {w}x{h}", w=fw, h=fh)
            threat_engine = ThreatEngine(frame_width=fw, frame_height=fh)
            log.info("ThreatEngine initialised for {w}x{h}", w=fw, h=fh)

        # ── Full AI pipeline ────────────────────────────────────────────
        with monitor.frame_timer():
            persons = detector.detect(frame)
            monitor.record_inference(detector.avg_inference_ms)

            active_tracks = track_manager.update(persons)
            threat_results = threat_engine.score_all(list(active_tracks.values()))
            summary = ThreatEngine.summarise(threat_results)

        # ── Auto-tuner ──────────────────────────────────────────────────
        if use_auto_tuner:
            new_skip = tuner.tick(monitor.fps)
            if new_skip != detector._skip_frames:
                detector._skip_frames = new_skip

        # ── Alerts ──────────────────────────────────────────────────────
        for tid, result in threat_results.items():
            if not result.is_actionable:
                continue
            track_state = active_tracks.get(tid)
            if track_state and not track_state.alert_sent:
                event = AlertEvent(
                    track_id=tid,
                    threat_level=result.threat_level,
                    threat_score=result.threat_score,
                    location="Mobile Camera Feed",
                    features=result.features,
                )
                fired = dispatcher.dispatch(event)
                if fired:
                    track_state.alert_sent = True
                    track_state.alert_sent_at = time.time()
                    # Post to coordinator for multi-stakeholder alerts
                    post_alert_to_coordinator(coordinator, result)

        # ── Annotate ────────────────────────────────────────────────────
        annotated = annotate(frame, persons, threat_results, monitor, summary)

        # ── Send processed frame + results back to coordinator ──────────
        sender.send_frame(annotated)
        sender.send_result({
            "persons": len(persons),
            "max_threat": max(
                (r.threat_level for r in threat_results.values()),
                key=lambda x: {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}.get(x, 0),
                default="NONE",
            ),
            "summary": summary,
            "fps": round(monitor.fps, 1),
            "tracks": len(active_tracks),
        })

        # ── Write to shared data (Streamlit dashboard compat) ──────────
        _write_frame(annotated)

        # ── Display ─────────────────────────────────────────────────────
        if not args.no_display:
            cv2.imshow("SafeSphere — Mobile Edge", annotated)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

        # ── Periodic status ─────────────────────────────────────────────
        now = time.time()
        if now - last_status_time > 10.0:
            perf = monitor.report()
            log.info(
                "Status | fps={fps:.1f} | persons={p} | tracks={t} | "
                "H={h} M={m} L={l} | alerts={a} | frames_rx={rx}",
                fps=perf["fps"],
                p=len(persons),
                t=track_manager.active_count,
                h=summary.get("HIGH", 0),
                m=summary.get("MEDIUM", 0),
                l=summary.get("LOW", 0),
                a=dispatcher.total_alerts,
                rx=receiver.frames_received,
            )
            last_status_time = now

    # ── Shutdown ────────────────────────────────────────────────────────────
    log.info("Shutting down...")
    receiver.stop()
    sender.stop()
    cv2.destroyAllWindows()

    perf = monitor.report()
    log.info(
        "Session | frames={f} | fps={fps:.1f} | tracks={t} | alerts={a}",
        f=perf["total_frames"],
        fps=perf["fps"],
        t=track_manager.total_tracks_seen,
        a=dispatcher.total_alerts,
    )


if __name__ == "__main__":
    main()
