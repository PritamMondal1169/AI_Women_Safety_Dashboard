"""
coordinator/routes/alerts.py — Threat alert handling.

Edge AI cameras POST alerts here. The coordinator then:
1. Stores the alert in the database
2. Pushes notification to the affected user's phone (FCM)
3. Pushes notification to family members
4. Broadcasts to security dashboard (WebSocket)
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from coordinator.database import get_db
from coordinator.models import (
    Alert, Journey, User, FamilyContact,
    AlertCreate, AlertResponse,
)
from fastapi import BackgroundTasks
import asyncio

logger = logging.getLogger("safesphere.alerts")
router = APIRouter(tags=["alerts"])


# ── Helper: optional current user (must be defined before route that uses it)

async def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Like get_current_user but returns None instead of 401."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    from coordinator.auth import decode_token
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        return None
    return await db.get(User, payload["sub"])


def _alert_to_response(a: Alert) -> AlertResponse:
    return AlertResponse(
        id=a.id, camera_id=a.camera_id, journey_id=a.journey_id,
        track_id=a.track_id, threat_level=a.threat_level,
        threat_score=a.threat_score, alert_type=a.alert_type,
        latitude=a.latitude, longitude=a.longitude,
        location_name=a.location_name, details=a.details,
        notified_user=a.notified_user,
        notified_family=a.notified_family,
        notified_security=a.notified_security,
        created_at=a.created_at,
    )


# ── Post alert (from edge AI camera) ─────────────────────────────────────

@router.post("/alerts", status_code=201, response_model=AlertResponse)
async def create_alert(
    body: AlertCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    # Find affected user if journey_id is given
    user_id = None
    if body.journey_id:
        journey = await db.get(Journey, body.journey_id)
        if journey:
            user_id = journey.user_id

    alert = Alert(
        camera_id=body.camera_id,
        journey_id=body.journey_id,
        user_id=user_id,
        track_id=body.track_id,
        threat_level=body.threat_level,
        threat_score=body.threat_score,
        alert_type=body.alert_type,
        latitude=body.latitude,
        longitude=body.longitude,
        location_name=body.location_name,
        details=body.details,
        snapshot_url=body.snapshot_url,
    )

    # ── Notification logic ────────────────────────────────────────────────
    alert.notified_security = True

    if body.threat_level in ("MEDIUM", "HIGH") and user_id:
        user = await db.get(User, user_id)
        if user and user.fcm_token:
            await _send_fcm(user.fcm_token, alert)
            alert.notified_user = True

        result = await db.execute(
            select(FamilyContact).where(
                FamilyContact.user_id == user_id,
                FamilyContact.notify_on_alert == True,
            )
        )
        family = result.scalars().all()
        if family:
            for member in family:
                if member.fcm_token:
                    await _send_fcm(member.fcm_token, alert, is_family=True)
            alert.notified_family = True

    db.add(alert)
    await db.flush()

    # ── Autonomous Escalation ──────────────────────────────────────────
    if body.threat_level == "HIGH" and user_id:
        background_tasks.add_task(_check_and_escalate, alert.id, user_id)

    logger.info(
        "Alert %s: %s (%.2f) → user=%s family=%s security=%s",
        alert.id[:8] if alert.id else "????", alert.threat_level, alert.threat_score,
        alert.notified_user, alert.notified_family, alert.notified_security,
    )

    # Broadcast to dashboard
    from coordinator.main import broadcast_to_dashboards, broadcast_to_user
    payload = {
        "type": "threat_alert",
        "alert_id": alert.id,
        "threat_level": alert.threat_level,
        "threat_score": alert.threat_score,
        "alert_type": alert.alert_type,
        "location_name": alert.location_name,
        "camera_id": alert.camera_id,
        "journey_id": alert.journey_id,
    }
    await broadcast_to_dashboards(payload)
    if user_id:
        await broadcast_to_user(user_id, payload)

    return _alert_to_response(alert)


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Mark an alert as acknowledged to stop automated escalation."""
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.acknowledged = True
    await db.commit()
    logger.info("Alert %s acknowledged by user", alert_id[:8])
    return {"status": "success"}


async def _check_and_escalate(alert_id: str, user_id: str):
    """Background task to verify user response and fire autonomous call."""
    from coordinator.database import async_session
    from coordinator.state import is_user_connected
    from utils.twilio_alerts import MultiChannelAlerter

    # 1. Check Offline status immediately
    if not is_user_connected(user_id):
        logger.warning("User %s is OFFLINE during HIGH threat. Dispatching autonomous call immediately.", user_id[:8])
        await _dispatch_autonomous_call(alert_id, user_id)
        return

    # 2. If Online, wait for escalation window
    logger.info("User %s is online. Waiting 30s before autonomous escalation...", user_id[:8])
    await asyncio.sleep(30)

    async with async_session() as db:
        alert = await db.get(Alert, alert_id)
        if alert and not alert.acknowledged:
            logger.warning("User %s did not acknowledge HIGH threat alert %s. Escalating...", user_id, alert_id[:8])
            await _dispatch_autonomous_call(alert_id, user_id)
        else:
            logger.info("Escalation cancelled for alert %s (acknowledged or inactive)", alert_id[:8])


async def _dispatch_autonomous_call(alert_id: str, user_id: str):
    """Effectively triggers the Twilio call to all family guardians."""
    from coordinator.database import async_session
    from utils.twilio_alerts import MultiChannelAlerter

    async with async_session() as db:
        # Fetch guardians
        result = await db.execute(
            select(FamilyContact).where(FamilyContact.user_id == user_id)
        )
        guardians = result.scalars().all()
        if not guardians:
            logger.error("No guardians found to call for user %s", user_id)
            return

        alert = await db.get(Alert, alert_id)
        if not alert:
            return

        guardian_phones = [g.phone for g in guardians if g.phone]
        
        alerter = MultiChannelAlerter()
        alerter.dispatch(
            threat_level=alert.threat_level,
            threat_score=alert.threat_score,
            location=alert.location_name or "Unknown Location",
            track_id=alert.track_id or 0,
            override_numbers=guardian_phones
        )
        logger.info("Autonomous emergency call dispatched to %d guardians", len(guardian_phones))


# ── Query alerts ──────────────────────────────────────────────────────────

@router.get("/alerts", response_model=list[AlertResponse])
async def list_alerts(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=500),
    level: Optional[str] = None,
):
    query = select(Alert).order_by(desc(Alert.created_at)).limit(limit)
    if level:
        query = query.where(Alert.threat_level == level.upper())
    result = await db.execute(query)
    return [_alert_to_response(a) for a in result.scalars().all()]


# ── My alerts (for mobile app user) ──────────────────────────────────────

@router.get("/alerts/my", response_model=list[AlertResponse])
async def my_alerts(
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=200),
):
    if not user:
        return []
    result = await db.execute(
        select(Alert)
        .where(Alert.user_id == user.id)
        .order_by(desc(Alert.created_at))
        .limit(limit)
    )
    return [_alert_to_response(a) for a in result.scalars().all()]


# ── FCM push notification ────────────────────────────────────────────────

async def _send_fcm(token: str, alert: Alert, is_family: bool = False):
    """Send push notification via Firebase Cloud Messaging."""
    try:
        import firebase_admin
        from firebase_admin import messaging

        if not firebase_admin._apps:
            firebase_admin.initialize_app()

        title = f"{'🔴' if alert.threat_level == 'HIGH' else '🟠'} SafeSphere Alert"
        if is_family:
            title += " (Family Member)"

        body_text = f"Threat: {alert.threat_level} ({alert.threat_score:.2f})"
        if alert.location_name:
            body_text += f"\nLocation: {alert.location_name}"

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body_text),
            data={
                "alert_id": alert.id,
                "threat_level": alert.threat_level,
                "threat_score": str(alert.threat_score),
                "alert_type": alert.alert_type or "threat",
                "latitude": str(alert.latitude or ""),
                "longitude": str(alert.longitude or ""),
            },
            token=token,
        )
        messaging.send(message)
        logger.info("FCM sent to %s...", token[:20])
    except ImportError:
        logger.debug("firebase-admin not installed — FCM skipped")
    except Exception as e:
        logger.warning("FCM send failed: %s", e)
