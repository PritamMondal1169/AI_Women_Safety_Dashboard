"""
coordinator/routes/transit.py — Blind spot transit tracking.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from coordinator.database import get_db
from coordinator.models import (
    Camera, TransitLog,
    TransitDeparture, TransitArrival, TransitResponse,
)

logger = logging.getLogger("safesphere.transit")
router = APIRouter(tags=["transit"])


def _log_to_response(log: TransitLog) -> TransitResponse:
    return TransitResponse(
        id=log.id,
        from_camera_id=log.from_camera_id,
        to_camera_id=log.to_camera_id,
        track_id=log.track_id,
        status=log.status,
        departure_time=log.departure_time,
        expected_arrival_time=log.expected_arrival_time,
        actual_arrival_time=log.actual_arrival_time,
        created_at=log.created_at,
    )


@router.post("/cameras/{camera_id}/transit-departure", status_code=201, response_model=TransitResponse)
async def report_departure(
    camera_id: str,
    body: TransitDeparture,
    db: AsyncSession = Depends(get_db),
):
    camera = await db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(404, "Camera not found")

    # Determine linked camera and transit time
    to_camera_id = camera.linked_camera_id
    # Use provided duration or calculate from distance (avg walking speed 1.35 m/s)
    duration_s = body.estimated_duration_s
    if camera.transit_distance_m and camera.transit_distance_m > 0:
        duration_s = camera.transit_distance_m / 1.35

    now = datetime.now(timezone.utc)
    expected_arrival = now + timedelta(seconds=duration_s)

    log_entry = TransitLog(
        from_camera_id=camera_id,
        to_camera_id=to_camera_id,
        track_id=body.track_id,
        snapshot_url=body.snapshot_url,
        departure_time=now,
        expected_arrival_time=expected_arrival,
        status="in_transit",
    )
    db.add(log_entry)
    await db.flush()
    
    logger.info("Transit START: Camera %s -> %s (track=%d, exp=%ds)", 
                camera_id[:8], to_camera_id[:8] if to_camera_id else "NONE", 
                 body.track_id, int(duration_s))
    
    return _log_to_response(log_entry)


@router.post("/cameras/{camera_id}/transit-arrival", response_model=List[TransitResponse])
async def report_arrival(
    camera_id: str,
    body: TransitArrival,
    db: AsyncSession = Depends(get_db),
):
    """
    Called when a person enters a camera's view.
    We try to match them with a pending transit coming TO this camera.
    """
    # Find the most recent unresolved transit coming to this camera
    # MVP matching: First-In-First-Out (FIFO) for transits to this camera
    result = await db.execute(
        select(TransitLog)
        .where(and_(
            TransitLog.to_camera_id == camera_id,
            TransitLog.status == "in_transit"
        ))
        .order_by(TransitLog.departure_time.asc())
        .limit(1)
    )
    log_entry = result.scalar_one_or_none()
    
    if not log_entry:
        logger.debug("Arrival at %s: No matching pending transits found.", camera_id[:8])
        return []

    log_entry.status = "arrived"
    log_entry.actual_arrival_time = datetime.now(timezone.utc)
    await db.flush()
    
    logger.info("Transit COMPLETE: Track arrived at %s (originated from %s)", 
                camera_id[:8], log_entry.from_camera_id[:8])
    
    return [_log_to_response(log_entry)]


@router.get("/transit/active", response_model=List[TransitResponse])
async def list_active_transits(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TransitLog).where(TransitLog.status == "in_transit")
    )
    return [_log_to_response(l) for l in result.scalars().all()]
