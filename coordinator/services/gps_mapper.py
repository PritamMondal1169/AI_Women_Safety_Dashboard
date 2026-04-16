"""
coordinator/services/gps_mapper.py — Maps GPS coordinates to camera coverage zones.

Given a (lat, lng) position, determines which camera nodes are relevant
(i.e. the position falls within the camera's coverage radius).

Uses Haversine formula for accurate distance on Earth's surface.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coordinator.models import CameraNode


def haversine_m(
    lat1: float, lng1: float,
    lat2: float, lng2: float,
) -> float:
    """
    Haversine distance between two (lat, lng) points in metres.
    """
    R = 6_371_000  # Earth radius in metres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def cameras_near_point(
    lat: float,
    lng: float,
    db: AsyncSession,
    max_distance_m: float = 200.0,
) -> List[CameraNode]:
    """
    Return all cameras whose coverage zone includes the given GPS point,
    or that are within max_distance_m.
    """
    result = await db.execute(select(CameraNode))
    all_cameras = result.scalars().all()

    nearby = []
    for cam in all_cameras:
        dist = haversine_m(lat, lng, cam.latitude, cam.longitude)
        effective_radius = max(cam.coverage_radius_m, max_distance_m)
        if dist <= effective_radius:
            nearby.append(cam)
    return nearby


async def cameras_on_route(
    waypoints: List[Tuple[float, float]],
    db: AsyncSession,
    buffer_m: float = 100.0,
) -> List[CameraNode]:
    """
    Return all cameras within buffer_m of any waypoint along a route.
    Useful for determining which cameras should be alerted for a journey.
    """
    result = await db.execute(select(CameraNode))
    all_cameras = result.scalars().all()

    relevant = set()
    for cam in all_cameras:
        for lat, lng in waypoints:
            dist = haversine_m(lat, lng, cam.latitude, cam.longitude)
            if dist <= cam.coverage_radius_m + buffer_m:
                relevant.add(cam.id)
                break

    # Return full objects for matched IDs
    return [c for c in all_cameras if c.id in relevant]


def estimate_transit_time_s(
    distance_m: float,
    walking_speed_mps: float = 1.35,
    buffer_factor: float = 1.4,
) -> float:
    """
    Estimate expected transit time between two cameras.
    
    Args:
        distance_m: Distance between cameras in metres.
        walking_speed_mps: Average walking speed (1.2–1.5 m/s typical).
        buffer_factor: Safety margin (1.4 = 40% buffer as per PRD).
    
    Returns:
        Expected transit time in seconds (with buffer).
    """
    if distance_m <= 0:
        return 0.0
    base_time = distance_m / walking_speed_mps
    return base_time * buffer_factor
