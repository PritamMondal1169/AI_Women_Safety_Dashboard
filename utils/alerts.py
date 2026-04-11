"""
utils/alerts.py — Multi-channel alert dispatcher for the Women Safety Product.

Channels:
  1. Console / log  — always fires; zero dependencies.
  2. Sound          — cross-platform beep (winsound on Windows, bell on Linux/macOS).
  3. Email          — SMTP/TLS via smtplib; supports Gmail App Passwords.

Design:
  - AlertDispatcher: single instance created in main.py.
  - AlertEvent dataclass carries everything about one incident.
  - Per-track cooldown (cfg.ALERT_COOLDOWN seconds) prevents alert storms.
  - Email I/O runs in a daemon thread — dispatch never blocks the CV loop.
  - Thread-safe in-memory log (deque) consumed by the Streamlit dashboard.

Usage:
    from utils.alerts import AlertDispatcher, AlertEvent

    dispatcher = AlertDispatcher()

    event = AlertEvent(
        track_id=3,
        threat_level="HIGH",
        threat_score=0.87,
        location="Kolkata, WB, India",
        snapshot_path="data/alert_3_1717000000.jpg",
        features={"speed_px_s": 145.0, "encirclement_score": 0.82},
    )
    dispatcher.dispatch(event)

    entries = dispatcher.get_log()   # List[AlertLogEntry] for dashboard
"""

from __future__ import annotations

import smtplib
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Deque, Dict, List, Optional

from config import cfg
from utils.logger import get_logger

log = get_logger(__name__)

# Max entries kept in the in-memory alert log
_LOG_MAXLEN: int = 500


# ---------------------------------------------------------------------------
# AlertEvent — describes one alert dispatch request
# ---------------------------------------------------------------------------
@dataclass
class AlertEvent:
    """All information needed to dispatch one alert."""

    track_id: int
    threat_level: str                    # "LOW" | "MEDIUM" | "HIGH"
    threat_score: float                  # composite score [0, 1]
    location: str = "Unknown"
    snapshot_path: Optional[str] = None  # annotated JPEG path
    timestamp: float = field(default_factory=time.time)
    features: dict = field(default_factory=dict)

    @property
    def timestamp_str(self) -> str:
        import datetime
        return datetime.datetime.fromtimestamp(self.timestamp).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    @property
    def emoji(self) -> str:
        return {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟡"}.get(self.threat_level, "⚪")


# ---------------------------------------------------------------------------
# AlertLogEntry — lightweight record stored in the log deque
# ---------------------------------------------------------------------------
@dataclass
class AlertLogEntry:
    """Slim record stored in the in-memory alert log for the dashboard."""
    timestamp_str: str
    track_id: int
    threat_level: str
    threat_score: float
    location: str
    channels: str   # comma-separated channels that fired


# ---------------------------------------------------------------------------
# AlertDispatcher
# ---------------------------------------------------------------------------
class AlertDispatcher:
    """
    Thread-safe alert dispatcher with per-track cooldown.

    Create once and call dispatch(event) from any thread.
    """

    def __init__(self) -> None:
        self._last_alert: Dict[int, float] = {}
        self._lock = threading.Lock()
        self._log: Deque[AlertLogEntry] = deque(maxlen=_LOG_MAXLEN)
        self._log_lock = threading.Lock()
        self.total_alerts: int = 0

        log.info(
            "AlertDispatcher ready | email={e} | sound={s} | cooldown={c}s",
            e=cfg.ALERT_EMAIL_ENABLED,
            s=cfg.ALERT_SOUND_ENABLED,
            c=cfg.ALERT_COOLDOWN,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def dispatch(self, event: AlertEvent) -> bool:
        """
        Fire all configured alert channels for the given event.

        Respects per-track cooldown: returns False without firing if the
        same track was alerted within cfg.ALERT_COOLDOWN seconds.

        Returns:
            True  — alert fired.
            False — suppressed by cooldown.
        """
        with self._lock:
            last = self._last_alert.get(event.track_id, 0.0)
            if time.time() - last < cfg.ALERT_COOLDOWN:
                log.debug(
                    "Alert suppressed (cooldown) | track={t} level={l}",
                    t=event.track_id, l=event.threat_level,
                )
                return False
            self._last_alert[event.track_id] = time.time()

        self.total_alerts += 1
        fired: List[str] = []

        # ── Console / log ──────────────────────────────────────────────────────
        log.warning(
            "{e} ALERT | Track={t} | Level={l} | Score={s:.3f} | Loc={loc}",
            e=event.emoji,
            t=event.track_id,
            l=event.threat_level,
            s=event.threat_score,
            loc=event.location,
        )
        fired.append("log")

        # ── Sound ──────────────────────────────────────────────────────────────
        if cfg.ALERT_SOUND_ENABLED:
            self._play_sound(event.threat_level)
            fired.append("sound")

        # ── Email (async) ──────────────────────────────────────────────────────
        if cfg.ALERT_EMAIL_ENABLED:
            threading.Thread(
                target=self._send_email,
                args=(event,),
                name=f"AlertEmail-{event.track_id}",
                daemon=True,
            ).start()
            fired.append("email")

        # ── Append to in-memory log ────────────────────────────────────────────
        entry = AlertLogEntry(
            timestamp_str=event.timestamp_str,
            track_id=event.track_id,
            threat_level=event.threat_level,
            threat_score=event.threat_score,
            location=event.location,
            channels=", ".join(fired),
        )
        with self._log_lock:
            self._log.appendleft(entry)

        return True

    def get_log(self) -> List[AlertLogEntry]:
        """Return snapshot of the in-memory log (newest first)."""
        with self._log_lock:
            return list(self._log)

    def clear_log(self) -> None:
        with self._log_lock:
            self._log.clear()

    # ── Sound channel ─────────────────────────────────────────────────────────

    @staticmethod
    def _play_sound(threat_level: str) -> None:
        """Play an alert tone. Windows: winsound. Linux/macOS: ASCII bell."""
        try:
            if sys.platform == "win32":
                import winsound
                patterns = {
                    "HIGH":   [(1200, 300), (1200, 300)],
                    "MEDIUM": [(900,  500)],
                    "LOW":    [(600,  200)],
                }
                for freq, dur in patterns.get(threat_level, [(800, 200)]):
                    winsound.Beep(freq, dur)
            else:
                reps = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(threat_level, 1)
                for _ in range(reps):
                    sys.stdout.write("\a")
                    sys.stdout.flush()
                    time.sleep(0.20)
            log.debug("Sound played | level={l}", l=threat_level)
        except Exception:
            log.exception("Sound alert failed.")

    # ── Email channel ─────────────────────────────────────────────────────────

    def _send_email(self, event: AlertEvent) -> None:
        """Build and send an HTML alert email (runs in its own daemon thread)."""
        if not cfg.ALERT_EMAIL_SENDER or not cfg.ALERT_EMAIL_RECEIVER:
            log.warning("Email skipped: SENDER or RECEIVER not configured.")
            return
        try:
            msg = MIMEMultipart("related")
            msg["Subject"] = (
                f"[Women Safety] {event.emoji} {event.threat_level} ALERT"
                f" — Track {event.track_id}"
            )
            msg["From"] = cfg.ALERT_EMAIL_SENDER
            msg["To"]   = cfg.ALERT_EMAIL_RECEIVER
            msg.attach(MIMEText(self._build_html(event), "html", "utf-8"))

            if event.snapshot_path:
                snap = Path(event.snapshot_path)
                if snap.exists():
                    with open(snap, "rb") as f:
                        img = MIMEImage(f.read(), name=snap.name)
                        img.add_header("Content-ID", "<snapshot>")
                        img.add_header("Content-Disposition", "inline",
                                       filename=snap.name)
                        msg.attach(img)

            with smtplib.SMTP(cfg.ALERT_EMAIL_SMTP, cfg.ALERT_EMAIL_PORT) as s:
                s.ehlo()
                s.starttls()
                s.login(cfg.ALERT_EMAIL_SENDER, cfg.ALERT_EMAIL_PASSWORD)
                s.sendmail(cfg.ALERT_EMAIL_SENDER, cfg.ALERT_EMAIL_RECEIVER,
                           msg.as_string())
            log.success("Email sent to {r}", r=cfg.ALERT_EMAIL_RECEIVER)
        except smtplib.SMTPAuthenticationError:
            log.error("Email auth failed. Check ALERT_EMAIL_PASSWORD.")
        except smtplib.SMTPException as exc:
            log.error("SMTP error: {e}", e=exc)
        except Exception:
            log.exception("Email dispatch failed.")

    @staticmethod
    def _build_html(event: AlertEvent) -> str:
        """Return a complete HTML email body for the given event."""
        color = {"HIGH": "#dc2626", "MEDIUM": "#ea580c", "LOW": "#ca8a04"}.get(
            event.threat_level, "#6b7280"
        )
        feat_rows = "".join(
            f"<tr><td style='padding:4px 8px;color:#374151'>{k}</td>"
            f"<td style='padding:4px 8px;font-weight:bold'>{v:.4f}</td></tr>"
            for k, v in event.features.items()
        )
        feat_table = (
            f"<h3>Feature Values</h3>"
            f"<table style='border-collapse:collapse;font-size:13px'>"
            f"<thead><tr>"
            f"<th style='text-align:left;padding:4px 8px;background:#f3f4f6'>Feature</th>"
            f"<th style='text-align:left;padding:4px 8px;background:#f3f4f6'>Value</th>"
            f"</tr></thead><tbody>{feat_rows}</tbody></table>"
            if feat_rows else ""
        )
        snap_tag = (
            "<h3>Snapshot</h3>"
            "<img src='cid:snapshot' style='max-width:100%;border-radius:8px'>"
            if event.snapshot_path else ""
        )
        return f"""<!DOCTYPE html><html><body style='font-family:Arial,sans-serif;
max-width:600px;margin:0 auto;padding:24px'>
<div style='background:{color};padding:16px 24px;border-radius:8px 8px 0 0'>
  <h1 style='color:#fff;margin:0;font-size:22px'>
    {event.emoji} {event.threat_level} THREAT DETECTED
  </h1>
</div>
<div style='background:#f9fafb;padding:24px;border:1px solid #e5e7eb;
border-top:none;border-radius:0 0 8px 8px'>
  <table style='width:100%;font-size:15px'>
    <tr><td style='color:#6b7280;width:140px'>Time</td>
        <td style='font-weight:bold'>{event.timestamp_str}</td></tr>
    <tr><td style='color:#6b7280'>Track ID</td>
        <td style='font-weight:bold'>{event.track_id}</td></tr>
    <tr><td style='color:#6b7280'>Level</td>
        <td style='font-weight:bold;color:{color}'>{event.threat_level}</td></tr>
    <tr><td style='color:#6b7280'>Score</td>
        <td style='font-weight:bold'>{event.threat_score:.3f} / 1.000</td></tr>
    <tr><td style='color:#6b7280'>Location</td>
        <td>{event.location}</td></tr>
  </table>
  {feat_table}
  {snap_tag}
  <p style='margin-top:32px;font-size:12px;color:#9ca3af'>
    Auto-generated by Women Safety Edge-AI Monitor. Do not reply.
  </p>
</div></body></html>"""
