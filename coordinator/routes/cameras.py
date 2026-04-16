"""
coordinator/routes/cameras.py — CCTV camera registration + heartbeat.

Edge AI nodes use these endpoints to register themselves and report status.
This is the SECURITY SIDE — cameras are managed by the security team, not users.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coordinator.database import get_db
from coordinator.models import (
    Camera,
    CameraRegister, CameraResponse, CameraHeartbeat,
    CameraUpdate,
)

logger = logging.getLogger("safesphere.cameras")
router = APIRouter(tags=["cameras"])


def _cam_to_response(c: Camera) -> CameraResponse:
    return CameraResponse(
        id=c.id, name=c.name, status=c.status,
        latitude=c.latitude, longitude=c.longitude,
        coverage_radius_m=c.coverage_radius_m,
        fps=c.fps, person_count=c.person_count,
        last_heartbeat=c.last_heartbeat,
        linked_camera_id=c.linked_camera_id,
        transit_distance_m=c.transit_distance_m,
    )



@router.post("/cameras/register", status_code=201, response_model=CameraResponse)
async def register_camera(
    body: CameraRegister,
    db: AsyncSession = Depends(get_db),
):
    camera = Camera(
        name=body.name,
        latitude=body.latitude,
        longitude=body.longitude,
        coverage_radius_m=body.coverage_radius_m,
        source_url=body.source_url,
        status="online",
        last_heartbeat=datetime.now(timezone.utc),
    )
    db.add(camera)
    await db.flush()
    logger.info("Camera registered: %s (%s)", camera.name, camera.id[:8])
    return _cam_to_response(camera)


@router.get("/cameras", response_model=list[CameraResponse])
async def list_cameras(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Camera).order_by(Camera.name))
    return [_cam_to_response(c) for c in result.scalars().all()]


@router.post("/cameras/{camera_id}/heartbeat")
async def camera_heartbeat(
    camera_id: str,
    body: CameraHeartbeat,
    db: AsyncSession = Depends(get_db),
):
    camera = await db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(404, "Camera not found")

    camera.status = "online"
    camera.fps = body.fps
    camera.person_count = body.person_count
    camera.last_heartbeat = datetime.now(timezone.utc)
    await db.flush()
    return {"status": "ok"}


@router.patch("/cameras/{camera_id}", response_model=CameraResponse)
async def update_camera(
    camera_id: str,
    body: CameraUpdate,
    db: AsyncSession = Depends(get_db),
):
    camera = await db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(404, "Camera not found")

    if body.name is not None: camera.name = body.name
    if body.status is not None: camera.status = body.status
    if body.latitude is not None: camera.latitude = body.latitude
    if body.longitude is not None: camera.longitude = body.longitude
    if body.linked_camera_id is not None: camera.linked_camera_id = body.linked_camera_id
    if body.transit_distance_m is not None: camera.transit_distance_m = body.transit_distance_m

    await db.flush()
    return _cam_to_response(camera)
