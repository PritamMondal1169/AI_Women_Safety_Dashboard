"""
coordinator/services/notifier.py — Multi-stakeholder notification service.

Dispatches alerts to:
  1. Woman (mobile push via Firebase / mock)
  2. Family members (push + email)
  3. Security dashboard (WebSocket broadcast — handled in routes/alerts.py)

Firebase is optional — if credentials are not configured, notifications are
logged but not sent (mock mode for development/hackathon).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coordinator.models import Alert, FamilyContact, Journey, User

logger = logging.getLogger("safesphere.notifier")

# ── Firebase Cloud Messaging (optional) ──────────────────────────────────────
_firebase_app = None
_FCM_AVAILABLE = False

try:
    import firebase_admin
    from firebase_admin import credentials, messaging

    _cred_path = os.environ.get("FIREBASE_CREDENTIALS", "")
    if _cred_path and os.path.exists(_cred_path):
        cred = credentials.Certificate(_cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        _FCM_AVAILABLE = True
        logger.info("Firebase Cloud Messaging initialised.")
    else:
        logger.warning(
            "Firebase credentials not found at '%s' — FCM disabled (mock mode).",
            _cred_path,
        )
except ImportError:
    logger.warning("firebase-admin not installed — FCM disabled (mock mode).")


async def send_push(
    token: Optional[str],
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None,
) -> bool:
    """
    Send a push notification via Firebase Cloud Messaging.
    Returns True if sent, False if FCM is unavailable or token is missing.
    """
    if not _FCM_AVAILABLE or not token:
        logger.info("[MOCK PUSH] → %s: %s", title, body)
        return False

    try:
        from firebase_admin import messaging

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            token=token,
        )
        messaging.send(message)
        logger.info("[FCM] Push sent: %s", title)
        return True
    except Exception:
        logger.exception("FCM push failed")
        return False


async def send_email_alert(
    to_email: str,
    subject: str,
    body_html: str,
) -> bool:
    """
    Send an email alert. Re-uses the project's existing SMTP logic.
    For MVP, logs the alert if SMTP is not configured.
    """
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        smtp_host = os.environ.get("ALERT_EMAIL_SMTP", "")
        smtp_port = int(os.environ.get("ALERT_EMAIL_PORT", "587"))
        sender = os.environ.get("ALERT_EMAIL_SENDER", "")
        password = os.environ.get("ALERT_EMAIL_PASSWORD", "")

        if not all([smtp_host, sender, password, to_email]):
            logger.info("[MOCK EMAIL] → %s: %s", to_email, subject)
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to_email
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)

        logger.info("[EMAIL] Alert sent to %s", to_email)
        return True
    except Exception:
        logger.exception("Email alert failed to %s", to_email)
        return False


async def notify_all_stakeholders(
    alert: Alert,
    journey: Optional[Journey],
    db: AsyncSession,
) -> Dict[str, bool]:
    """
    Notify all relevant stakeholders about a threat alert.
    
    Returns:
        dict with keys "user", "family", "security" → bool (success).
    """
    result = {"user": False, "family": False, "security": True}  # security always gets it via WS

    # Only MEDIUM and HIGH trigger multi-stakeholder alerts
    if alert.threat_level.value not in ("MEDIUM", "HIGH"):
        return result

    level_emoji = "🔴" if alert.threat_level.value == "HIGH" else "🟠"
    title = f"{level_emoji} SafeSphere Alert: {alert.threat_level.value} Threat"
    body = (
        f"Threat level: {alert.threat_level.value} (score: {alert.threat_score:.2f})\n"
        f"Location: {alert.location_name or 'Unknown'}\n"
        f"Type: {alert.alert_type}"
    )

    # ── 1. Notify the woman (user) ────────────────────────────────────────────
    if journey:
        user_result = await db.execute(
            select(User).where(User.id == journey.user_id)
        )
        user = user_result.scalar_one_or_none()
        if user:
            # In a real app, the user's FCM token would be stored in the DB
            # For MVP, we mock the push
            result["user"] = await send_push(
                token=None,  # Would be user.fcm_token
                title=title,
                body=body,
                data={
                    "alert_id": alert.id,
                    "threat_level": alert.threat_level.value,
                    "journey_id": journey.id,
                },
            )

    # ── 2. Notify family members ──────────────────────────────────────────────
    if journey:
        contacts_result = await db.execute(
            select(FamilyContact).where(
                FamilyContact.user_id == journey.user_id,
                FamilyContact.notify_on_journey == True,
            )
        )
        contacts = contacts_result.scalars().all()

        family_notified = False
        for contact in contacts:
            # Push notification (mock for MVP)
            await send_push(
                token=None,  # Would be contact.fcm_token
                title=f"{level_emoji} Safety Alert for your family member",
                body=body,
            )
            # Email if available
            if contact.email:
                email_body = f"""
                <h2>{level_emoji} SafeSphere Safety Alert</h2>
                <p><strong>Threat Level:</strong> {alert.threat_level.value}</p>
                <p><strong>Score:</strong> {alert.threat_score:.2f}</p>
                <p><strong>Location:</strong> {alert.location_name or 'Unknown'}</p>
                <p><strong>Type:</strong> {alert.alert_type}</p>
                <p>Please check the SafeSphere app for live updates.</p>
                """
                await send_email_alert(contact.email, title, email_body)
            family_notified = True

        result["family"] = family_notified

    logger.info(
        "Alert %s notifications: user=%s family=%s security=%s",
        alert.id, result["user"], result["family"], result["security"],
    )
    return result
