"""
coordinator/routes/journey.py — Journey CRUD, GPS tracking, route planning.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coordinator.database import get_db
from coordinator.models import (
    User, Journey, GpsPing, FamilyContact, Alert,
    JourneyCreate, JourneyResponse, JourneyUpdate, GpsPingCreate,
)
from coordinator.routes.auth import get_current_user
from fastapi import BackgroundTasks
from sqlalchemy import select, desc

logger = logging.getLogger("safesphere.journey")
router = APIRouter(tags=["journey"])


def _journey_to_response(j: Journey) -> JourneyResponse:
    return JourneyResponse(
        id=j.id, user_id=j.user_id, status=j.status,
        start_lat=j.start_lat, start_lng=j.start_lng,
        start_address=j.start_address,
        end_lat=j.end_lat, end_lng=j.end_lng,
        end_address=j.end_address,
        route_polyline=j.route_polyline,
        route_summary=j.route_summary,
        distance_m=j.distance_m, duration_s=j.duration_s,
        created_at=j.created_at,
        started_at=j.started_at, completed_at=j.completed_at,
    )


# ── Create journey ───────────────────────────────────────────────────────

@router.post("/journey", status_code=201, response_model=JourneyResponse)
async def create_journey(
    body: JourneyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    journey = Journey(
        user_id=user.id,
        start_lat=body.start_lat,
        start_lng=body.start_lng,
        start_address=body.start_address,
        end_lat=body.end_lat,
        end_lng=body.end_lng,
        end_address=body.end_address,
        status="planned",
    )

    # Try to get route from Google Maps
    route_info = await _get_route(
        body.start_lat, body.start_lng,
        body.end_lat, body.end_lng,
    )
    if route_info:
        journey.route_polyline = route_info.get("polyline")
        journey.route_summary = route_info.get("summary")
        journey.distance_m = route_info.get("distance_m")
        journey.duration_s = route_info.get("duration_s")

    db.add(journey)
    await db.flush()
    logger.info("Journey created: %s for user %s", journey.id[:8], user.id[:8])
    return _journey_to_response(journey)


# ── Get journey by ID ────────────────────────────────────────────────────

@router.get("/journey/{journey_id}", response_model=JourneyResponse)
async def get_journey(
    journey_id: str,
    db: AsyncSession = Depends(get_db),
):
    journey = await db.get(Journey, journey_id)
    if not journey:
        raise HTTPException(404, "Journey not found")
    return _journey_to_response(journey)


# ── List active journeys ─────────────────────────────────────────────────

@router.get("/journey/active", response_model=list[JourneyResponse])
async def active_journeys(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Journey).where(Journey.status == "active").order_by(Journey.started_at.desc())
    )
    return [_journey_to_response(j) for j in result.scalars().all()]


# ── My journeys (for the mobile app user) ────────────────────────────────

@router.get("/journey/my", response_model=list[JourneyResponse])
async def my_journeys(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, le=100),
):
    result = await db.execute(
        select(Journey)
        .where(Journey.user_id == user.id)
        .order_by(Journey.created_at.desc())
        .limit(limit)
    )
    return [_journey_to_response(j) for j in result.scalars().all()]


# ── Update journey status ────────────────────────────────────────────────

@router.patch("/journey/{journey_id}", response_model=JourneyResponse)
async def update_journey(
    journey_id: str,
    body: JourneyUpdate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    journey = await db.get(Journey, journey_id)
    if not journey:
        raise HTTPException(404, "Journey not found")
    if journey.user_id != user.id:
        raise HTTPException(403, "Not your journey")

    if body.status:
        journey.status = body.status
        if body.status == "active":
            journey.started_at = datetime.now(timezone.utc)
        elif body.status in ("completed", "cancelled"):
            journey.completed_at = datetime.now(timezone.utc)
        elif body.status == "sos":
            journey.status = "sos"
            # Trigger emergency notifications to family + security
            background_tasks.add_task(_trigger_sos_alerts, journey.id, user.id)
            logger.warning("SOS triggered for journey %s by user %s", journey_id[:8], user.id[:8])

    await db.flush()
    return _journey_to_response(journey)


# ── GPS ping (phone sends location updates) ──────────────────────────────

@router.post("/journey/{journey_id}/gps")
async def post_gps(
    journey_id: str,
    body: GpsPingCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    journey = await db.get(Journey, journey_id)
    if not journey:
        raise HTTPException(404, "Journey not found")
    if journey.user_id != user.id:
        raise HTTPException(403, "Not your journey")

    ping = GpsPing(
        journey_id=journey_id,
        latitude=body.latitude,
        longitude=body.longitude,
        speed_mps=body.speed_mps,
        accuracy_m=body.accuracy_m,
    )
    db.add(ping)
    await db.flush()

    # Broadcast to WebSocket listeners (family tracking)
    from coordinator.main import broadcast_to_dashboards
    await broadcast_to_dashboards({
        "type": "gps_ping",
        "journey_id": journey_id,
        "user_id": user.id,
        "latitude": body.latitude,
        "longitude": body.longitude,
        "speed_mps": body.speed_mps,
    })

    return {"status": "ok", "ping_id": ping.id}


# ── GPS history for a journey ────────────────────────────────────────────

@router.get("/journey/{journey_id}/gps")
async def get_gps_history(
    journey_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GpsPing)
        .where(GpsPing.journey_id == journey_id)
        .order_by(GpsPing.timestamp.asc())
    )
    pings = result.scalars().all()
    return [
        {
            "latitude": p.latitude,
            "longitude": p.longitude,
            "speed_mps": p.speed_mps,
            "timestamp": p.timestamp.isoformat() if p.timestamp else None,
        }
        for p in pings
    ]


# ── Route planning helper (Google Maps) ──────────────────────────────────

async def _get_route(start_lat, start_lng, end_lat, end_lng) -> Optional[dict]:
    """Fetch route from Google Maps Directions API."""
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        logger.debug("No GOOGLE_MAPS_API_KEY set — skipping route lookup")
        return None

    import httpx
    try:
        url = "https://maps.googleapis.com/maps/api/directions/json"
        params = {
            "origin": f"{start_lat},{start_lng}",
            "destination": f"{end_lat},{end_lng}",
            "mode": "walking",
            "alternatives": "true",
            "key": api_key,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=10.0)
            data = resp.json()

        if data.get("status") != "OK" or not data.get("routes"):
            return None

        # Pick the first route (could rank by safety in the future)
        route = data["routes"][0]
        leg = route["legs"][0]

        return {
            "polyline": route["overview_polyline"]["points"],
            "summary": route.get("summary", ""),
            "distance_m": leg["distance"]["value"],
            "duration_s": leg["duration"]["value"],
        }
    except Exception as e:
        logger.debug("Google Maps API error: %s", e)
        return None


async def _trigger_sos_alerts(journey_id: str, user_id: str):
    """Effectively triggers the Twilio call/SMS to all family guardians on manual SOS."""
    from coordinator.database import async_session
    from utils.twilio_alerts import MultiChannelAlerter

    async with async_session() as db:
        # 1. Fetch user and guardians
        user = await db.get(User, user_id)
        result = await db.execute(
            select(FamilyContact).where(FamilyContact.user_id == user_id)
        )
        guardians = result.scalars().all()
        
        # 2. Get latest location
        ping_result = await db.execute(
            select(GpsPing)
            .where(GpsPing.journey_id == journey_id)
            .order_by(desc(GpsPing.timestamp))
            .limit(1)
        )
        last_ping = ping_result.scalar_one_or_none()
        
        location_str = "Unknown Location"
        if last_ping:
            location_str = f"{last_ping.latitude:.5f}, {last_ping.longitude:.5f}"

        # 3. Create Alert record
        alert = Alert(
            journey_id=journey_id,
            user_id=user_id,
            threat_level="HIGH",
            threat_score=1.0,
            alert_type="sos",
            latitude=last_ping.latitude if last_ping else None,
            longitude=last_ping.longitude if last_ping else None,
            location_name=location_str,
            details=f"Manual SOS triggered by {user.name if user else 'User'}",
        )
        db.add(alert)
        await db.commit()

        # 4. Dispatch external alerts
        guardian_phones = [g.phone for g in guardians if g.phone]
        if guardian_phones:
            alerter = MultiChannelAlerter()
            alerter.dispatch(
                threat_level="HIGH",
                threat_score=1.0,
                location=location_str,
                track_id=0,
                override_numbers=guardian_phones
            )
            logger.info("SOS alerts dispatched to %d guardians for user %s", len(guardian_phones), user_id[:8])
        else:
            logger.warning("SOS triggered but no guardian phone numbers found for user %s", user_id[:8])
