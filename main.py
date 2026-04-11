"""
main.py — Women Safety Product: Production Entry Point (Days 1–5)

Full pipeline per frame:
  Camera (thread-safe, auto-reconnect)
    → Detector (YOLOv8n + BoT-SORT, person-only)
    → TrackManager (per-track state history)
    → ThreatEngine (XGBoost + heuristic, 3 levels)
    → AlertDispatcher (email + sound, per-track cooldown)
    → PerformanceMonitor (rolling FPS, latency, p95)
    → FrameSkipTuner (adaptive skip for target FPS)
    → Dashboard state writer (JSON + JPEG shared with Streamlit)
    → RuntimeConfig hot-reloader (threshold changes from dashboard)

Run:
    python main.py                         # webcam, OpenCV window
    python main.py --source video.mp4
    python main.py --no-display            # headless / SSH
    python main.py --dashboard             # launch Streamlit in subprocess
    python main.py --target-fps 30         # auto-tuner target
    python main.py --skip 1               # force skip (disable auto-tuner)
    python main.py --export-onnx          # export ONNX then run pipeline

Controls (OpenCV window):
    q — quit     s — snapshot     p — pause/resume
    + — increase skip manually    - — decrease skip manually
"""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional

import cv2
import numpy as np

from config import cfg
from utils.logger import setup_logging, get_logger
from utils.alerts import AlertDispatcher, AlertEvent
from utils.twilio_alerts import MultiChannelAlerter
from utils.location import LocationProvider
from utils.performance import PerformanceMonitor, FrameSkipTuner
from core.camera import Camera
from core.detector import Detector, TrackedPerson
from core.tracker import TrackManager
from core.threat import ThreatEngine, ThreatResult, THREAT_COLORS

# ---------------------------------------------------------------------------
# Logging — must be first
# ---------------------------------------------------------------------------
setup_logging(
    log_dir=cfg.log_abs_dir,
    level=cfg.LOG_LEVEL,
    rotation=cfg.LOG_ROTATION,
    retention=cfg.LOG_RETENTION,
)
log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Shared data directory (Streamlit dashboard reads these)
# ---------------------------------------------------------------------------
_DATA_DIR        = Path("data")
_STATE_FILE      = _DATA_DIR / "dashboard_state.json"
_ALERT_LOG_FILE  = _DATA_DIR / "alert_log.json"
_FRAME_FILE      = _DATA_DIR / "latest_frame.jpg"
_HISTORY_FILE    = _DATA_DIR / "dashboard_history.json"
_RT_CONFIG_FILE  = _DATA_DIR / "runtime_config.json"

# Write intervals (frames between disk writes)
_STATE_INTERVAL   = 15
_FRAME_INTERVAL   = 1
_HISTORY_INTERVAL = 30
_PERF_LOG_INTERVAL = 120   # log detailed perf summary every N frames

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
_shutdown_requested = False


def _signal_handler(sig, _frame) -> None:
    global _shutdown_requested
    log.warning("Signal {s} — graceful shutdown requested.", s=sig)
    _shutdown_requested = True


signal.signal(signal.SIGINT,  _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ---------------------------------------------------------------------------
# Runtime config hot-reload
# ---------------------------------------------------------------------------
class RuntimeConfig:
    """
    Polls data/runtime_config.json for live overrides from the dashboard.
    Checked every _STATE_INTERVAL frames; never blocks the main loop.
    """

    def __init__(self) -> None:
        self._last_mtime: float = 0.0
        self._overrides: Dict = {}

    def poll(self) -> bool:
        """Return True if the config file changed since last poll."""
        try:
            if not _RT_CONFIG_FILE.exists():
                return False
            mtime = _RT_CONFIG_FILE.stat().st_mtime
            if mtime == self._last_mtime:
                return False
            raw = _RT_CONFIG_FILE.read_text()
            self._overrides = json.loads(raw)
            self._last_mtime = mtime
            log.info(
                "Runtime config updated: {keys}",
                keys=list(self._overrides.keys()),
            )
            return True
        except Exception:
            return False

    def get(self, key: str, default):
        return self._overrides.get(key, default)


# ---------------------------------------------------------------------------
# Dashboard writers
# ---------------------------------------------------------------------------

def _write_state(
    monitor: PerformanceMonitor,
    tuner: FrameSkipTuner,
    person_count: int,
    active_tracks: int,
    summary: Dict[str, int],
    total_alerts: int,
    location_fix,
    xgb_loaded: bool,
    camera_source,
    resolution: str,
) -> None:
    try:
        perf = monitor.report()
        payload = {
            "running":           True,
            "timestamp":         time.time(),
            "fps":               perf["fps"],
            "avg_inference_ms":  perf["avg_inference_ms"],
            "avg_frame_ms":      perf["avg_frame_ms"],
            "p95_frame_ms":      perf["p95_frame_ms"],
            "total_frames":      perf["total_frames"],
            "uptime_s":          perf["uptime_s"],
            "current_skip":      tuner.skip,
            "person_count":      person_count,
            "active_tracks":     active_tracks,
            "threat_summary":    summary,
            "total_alerts":      total_alerts,
            "location":          location_fix.display,
            "maps_url":          location_fix.maps_url,
            "xgb_loaded":        xgb_loaded,
            "camera_source":     str(camera_source),
            "model_path":        cfg.MODEL_PATH,
            "model_device":      cfg.MODEL_DEVICE,
            "resolution":        resolution,
            **summary,   # spread HIGH/MEDIUM/LOW/NONE as top-level for chart queries
        }
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(payload))
    except Exception:
        log.debug("State write failed (non-critical).")


def _write_frame(frame: np.ndarray) -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = str(_FRAME_FILE) + ".tmp"
        cv2.imwrite(tmp_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        import os
        os.replace(tmp_path, str(_FRAME_FILE))
    except Exception:
        pass


def _append_alert(event: AlertEvent) -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        alerts: list = []
        if _ALERT_LOG_FILE.exists():
            try:
                alerts = json.loads(_ALERT_LOG_FILE.read_text())
            except Exception:
                alerts = []
        alerts.insert(0, {
            "timestamp_str": event.timestamp_str,
            "track_id":      event.track_id,
            "threat_level":  event.threat_level,
            "threat_score":  round(event.threat_score, 4),
            "location":      event.location,
            "channels":      "log,sound,email",
        })
        _ALERT_LOG_FILE.write_text(json.dumps(alerts[:cfg.LOG_MAX_ROWS]))
    except Exception:
        pass


def _update_history(monitor: PerformanceMonitor, summary: Dict) -> None:
    try:
        history: list = []
        if _HISTORY_FILE.exists():
            try:
                history = json.loads(_HISTORY_FILE.read_text())
            except Exception:
                history = []
        r = monitor.report()
        history.append({
            "timestamp":        time.time(),
            "fps":              r["fps"],
            "avg_inference_ms": r["avg_inference_ms"],
            "avg_frame_ms":     r["avg_frame_ms"],
            **summary,
        })
        history = history[-600:]   # keep ~10 min at 1 snap/s
        _HISTORY_FILE.write_text(json.dumps(history))
    except Exception:
        pass


def _mark_stopped() -> None:
    try:
        if _STATE_FILE.exists():
            s = json.loads(_STATE_FILE.read_text())
            s["running"] = False
            _STATE_FILE.write_text(json.dumps(s))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Frame annotation
# ---------------------------------------------------------------------------

def _annotate(
    frame: np.ndarray,
    persons: list,
    threat_results: Dict[int, ThreatResult],
    monitor: PerformanceMonitor,
    tuner: FrameSkipTuner,
    summary: Dict[str, int],
    location_str: str,
) -> np.ndarray:
    out = frame.copy()
    color_map = ThreatEngine.build_color_map(threat_results)

    # Track if we have any active danger interactions
    danger_detected = False

    for p in persons:
        x1, y1, x2, y2 = p.bbox
        color = color_map.get(p.track_id, THREAT_COLORS["NONE"])
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

        r = threat_results.get(p.track_id)
        if r:
            label = f"ID:{p.track_id} {r.threat_level} {r.threat_score:.2f}"
            if hasattr(r, 'interaction_type') and r.interaction_type != "NEUTRAL":
                label += f" [{r.interaction_type}]"
                if r.interaction_type == "DANGER":
                    danger_detected = True
        else:
            label = f"ID:{p.track_id}"
            
        cv2.putText(out, label, (x1, max(y1 - 8, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)

    perf = monitor.report()
    stats = [
        f"FPS:{perf['fps']:.1f}  skip:{tuner.skip}  inf:{perf['avg_inference_ms']:.0f}ms  p95:{perf['p95_frame_ms']:.0f}ms",
        f"P:{len(persons)}  H:{summary.get('HIGH',0)} M:{summary.get('MEDIUM',0)} L:{summary.get('LOW',0)}",
        location_str,
    ]
    for i, txt in enumerate(stats):
        cv2.putText(out, txt, (10, 22 + i * 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 220, 255), 2, cv2.LINE_AA)

    h, w = out.shape[:2]

    # Draw High Threat OR Interaction Danger Banner
    if summary.get("HIGH", 0) > 0 or danger_detected:
        ids_high = [str(t) for t, r in threat_results.items() if r.threat_level == "HIGH"]
        ids_danger = [str(t) for t, r in threat_results.items() if getattr(r, 'interaction_type', '') == "DANGER"]
        
        cv2.rectangle(out, (0, h - 40), (w, h), (0, 0, 180), -1)
        
        banner_text = "!!! "
        if summary.get("HIGH", 0) > 0:
            banner_text += f"HIGH THREAT Tracks: {', '.join(ids_high)}  "
        if danger_detected:
            banner_text += f"DANGER INTERACTION Tracks: {', '.join(set(ids_danger))} "
        banner_text += " !!!"
        
        cv2.putText(out, banner_text, (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                    (255, 255, 255), 2, cv2.LINE_AA)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Women Safety Product — Production Pipeline")
    p.add_argument("--source",      default=None,         help="Camera / file / RTSP URL")
    p.add_argument("--skip",        type=int, default=-1,  help="Force frame skip (disables auto-tuner)")
    p.add_argument("--target-fps",  type=float, default=25.0, help="Auto-tuner target FPS")
    p.add_argument("--no-display",  action="store_true",   help="Headless mode")
    p.add_argument("--dashboard",   action="store_true",   help="Launch Streamlit subprocess")
    p.add_argument("--export-onnx", action="store_true",   help="Export ONNX on startup then run")
    p.add_argument("--save-dir",    default="data",        help="Snapshot save directory")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    log.info("=" * 64)
    log.info("  Women Safety Product — Production Pipeline (Days 1–5)")
    log.info("=" * 64)
    log.info(cfg.display())

    # Resolve source
    source = args.source if args.source is not None else cfg.CAMERA_SOURCE
    if isinstance(source, str) and source.lstrip("-").isdigit():
        source = int(source)

    save_dir = Path(args.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ── Optional ONNX export before pipeline start ────────────────────────────
    if args.export_onnx or cfg.EXPORT_ONNX:
        log.info("ONNX export requested…")
        from utils.onnx_export import export_yolo_onnx, verify_onnx
        onnx_path = export_yolo_onnx()
        if onnx_path:
            verify_onnx(onnx_path)

    # ── Optional Streamlit dashboard subprocess ───────────────────────────────
    dashboard_proc: Optional[subprocess.Popen] = None
    if args.dashboard:
        try:
            dashboard_proc = subprocess.Popen(
                [sys.executable, "-m", "streamlit", "run",
                 "frontend/dashboard.py",
                 "--server.port", str(cfg.DASHBOARD_PORT)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log.info("Streamlit launched on port {p}.", p=cfg.DASHBOARD_PORT)
        except Exception:
            log.exception("Could not launch Streamlit.")

    # ── Component init ────────────────────────────────────────────────────────
    camera: Optional[Camera] = None
    try:
        log.info("Initialising camera (source={s})…", s=source)
        camera = Camera(source=source)
        camera.start()
        time.sleep(0.35)   # let the reader thread grab the first frame

        _, probe = camera.read()
        fh, fw = (probe.shape[:2] if probe is not None
                  else (cfg.CAMERA_HEIGHT, cfg.CAMERA_WIDTH))
        resolution_str = f"{fw}×{fh}"
        log.info("Frame resolution: {r}", r=resolution_str)

        # Determine initial skip
        init_skip = args.skip if args.skip >= 0 else 0
        use_auto_tuner = args.skip < 0   # auto-tuner ON when --skip not specified

        log.info("Initialising Detector (skip={s})…", s=init_skip)
        detector = Detector(skip_frames=init_skip)

        log.info("Initialising TrackManager…")
        track_manager = TrackManager()

        log.info("Initialising ThreatEngine ({w}×{h})…", w=fw, h=fh)
        threat_engine = ThreatEngine(frame_width=fw, frame_height=fh)

        log.info("Initialising AlertDispatcher…")
        dispatcher = AlertDispatcher()

        log.info("Initialising MultiChannelAlerter (Twilio/AT)…")
        multi_alerter = MultiChannelAlerter()

        log.info("Initialising LocationProvider…")
        location_svc = LocationProvider()
        location_svc.start_background_refresh()
        location_fix = location_svc.get()
        log.info("Location: {l}", l=location_fix.display)

        monitor   = PerformanceMonitor(fps_window=60)
        tuner     = FrameSkipTuner(
            target_fps=args.target_fps,
            tolerance=2.0,
            window=30,
            initial_skip=init_skip,
            verbose=True,
        )
        rt_cfg    = RuntimeConfig()

    except Exception:
        log.exception("Pipeline init failed. Aborting.")
        if camera:
            camera.stop()
        if dashboard_proc:
            dashboard_proc.terminate()
        return 1

    paused         = False
    snap_idx       = 0
    threat_results: Dict[int, ThreatResult] = {}
    summary: Dict[str, int] = {"NONE":0, "LOW":0, "MEDIUM":0, "HIGH":0}

    log.info(
        "Pipeline ready | auto_tuner={at} | target_fps={t} | device={d}",
        at=use_auto_tuner, t=args.target_fps, d=cfg.MODEL_DEVICE,
    )
    log.info("Controls: q=quit  s=snapshot  p=pause  +=skip+  -=skip-")

    # ── Frame loop ────────────────────────────────────────────────────────────
    while not _shutdown_requested:
        if not camera.is_running():
            log.error("Camera stopped unexpectedly.")
            break

        ok, frame = camera.read()
        if not ok:
            time.sleep(0.005)
            continue

        if paused:
            if not args.no_display:
                cv2.imshow("Women Safety", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("p"):
                paused = False
            continue

        # ── Hot-reload runtime config ─────────────────────────────────────────
        fc = monitor.total_frames
        if fc % _STATE_INTERVAL == 0:
            rt_cfg.poll()

        # ── Full frame pipeline (timed) ───────────────────────────────────────
        with monitor.frame_timer():

            # Detection
            persons = detector.detect(frame)
            monitor.record_inference(detector.avg_inference_ms)

            # Tracking
            active_tracks = track_manager.update(persons)

            # Threat scoring
            threat_results = threat_engine.score_all(list(active_tracks.values()))
            summary = ThreatEngine.summarise(threat_results)

        # ── Auto-tuner ────────────────────────────────────────────────────────
        if use_auto_tuner:
            new_skip = tuner.tick(monitor.fps)
            if new_skip != detector._skip_frames:
                detector._skip_frames = new_skip
        else:
            tuner._skip = detector._skip_frames   # keep tuner in sync for display

        # ── Alerts ────────────────────────────────────────────────────────────
        for tid, result in threat_results.items():
            if not result.is_actionable:
                continue
            track_state = active_tracks.get(tid)
            if track_state and not track_state.alert_sent:
                snap_path = save_dir / f"alert_{tid}_{int(time.time())}.jpg"
                try:
                    cv2.imwrite(str(snap_path), frame)
                except Exception:
                    snap_path = None

                event = AlertEvent(
                    track_id=tid,
                    threat_level=result.threat_level,
                    threat_score=result.threat_score,
                    location=location_fix.display,
                    snapshot_path=str(snap_path) if snap_path else None,
                    features=result.features,
                )
                fired = dispatcher.dispatch(event)
                if fired:
                    track_state.alert_sent    = True
                    track_state.alert_sent_at = time.time()
                    _append_alert(event)
                    # ── Twilio / Africa's Talking ──────────────────────────
                    multi_alerter.dispatch(
                        threat_level  = result.threat_level,
                        threat_score  = result.threat_score,
                        location      = location_fix.display,
                        track_id      = tid,
                        snapshot_path = str(snap_path) if snap_path else None,
                    )

        # ── Dashboard state writes ─────────────────────────────────────────────
        if fc % _STATE_INTERVAL == 0:
            _write_state(
                monitor, tuner, len(persons), track_manager.active_count,
                summary, dispatcher.total_alerts, location_fix,
                threat_engine._xgb_available, source, resolution_str,
            )
        if fc % _FRAME_INTERVAL == 0:
            annotated_for_dash = _annotate(
                frame, persons, threat_results,
                monitor, tuner, summary, location_fix.display,
            )
            _write_frame(annotated_for_dash)
        if fc % _HISTORY_INTERVAL == 0:
            _update_history(monitor, summary)

        # ── Periodic location refresh (every ~5 min) ──────────────────────────
        if fc > 0 and fc % 9000 == 0:
            location_fix = location_svc.get()

        # ── Annotate + display ────────────────────────────────────────────────
        if not args.no_display or fc % _FRAME_INTERVAL == 0:
            annotated = _annotate(
                frame, persons, threat_results,
                monitor, tuner, summary, location_fix.display,
            )
            if not args.no_display:
                cv2.imshow("Women Safety — Live Feed", annotated)

        # ── Detailed perf log ─────────────────────────────────────────────────
        if fc % _PERF_LOG_INTERVAL == 0 and fc > 0:
            monitor.log_summary()
            log.info(
                "Tuner | skip={sk} adjustments={adj} | "
                "Tracks={t} total_seen={ts} | Alerts={a}",
                sk=tuner.skip,
                adj=tuner.adjustments,
                t=track_manager.active_count,
                ts=track_manager.total_tracks_seen,
                a=dispatcher.total_alerts,
            )

        # ── Key handling ──────────────────────────────────────────────────────
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            log.info("Quit key pressed.")
            break
        elif key == ord("s"):
            sp = save_dir / f"snap_{snap_idx:05d}.jpg"
            try:
                cv2.imwrite(str(sp), annotated)
                log.info("Snapshot: {p}", p=sp)
            except Exception:
                pass
            snap_idx += 1
        elif key == ord("p"):
            paused = not paused
            log.info("Paused={v}", v=paused)
        elif key == ord("+") or key == ord("="):
            detector._skip_frames = min(detector._skip_frames + 1, 5)
            tuner._skip = detector._skip_frames
            log.info("Manual skip → {s}", s=detector._skip_frames)
        elif key == ord("-"):
            detector._skip_frames = max(detector._skip_frames - 1, 0)
            tuner._skip = detector._skip_frames
            log.info("Manual skip → {s}", s=detector._skip_frames)

    # ── Shutdown ──────────────────────────────────────────────────────────────
    log.info("Pipeline shutting down…")
    camera.stop()
    location_svc.stop()
    cv2.destroyAllWindows()
    _mark_stopped()

    if dashboard_proc:
        log.info("Terminating Streamlit…")
        dashboard_proc.terminate()

    # Final summary
    perf = monitor.report()
    log.info(
        "Session complete | frames={f} | avg_fps={fps} | avg_inf={ms}ms | "
        "p95={p95}ms | tracks_total={t} | reconnects={r} | alerts={a}",
        f=perf["total_frames"],
        fps=perf["fps"],
        ms=perf["avg_inference_ms"],
        p95=perf["p95_frame_ms"],
        t=track_manager.total_tracks_seen,
        r=camera.reconnect_count,
        a=dispatcher.total_alerts,
    )
    log.info(
        "FrameSkipTuner | final_skip={sk} | adjustments={adj}",
        sk=tuner.skip, adj=tuner.adjustments,
    )
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    args = _parse_args()
    try:
        code = run(args)
    except KeyboardInterrupt:
        log.warning("KeyboardInterrupt.")
        code = 0
    except Exception:
        log.exception("Unhandled top-level exception.")
        code = 1
    finally:
        cv2.destroyAllWindows()
    sys.exit(code)
