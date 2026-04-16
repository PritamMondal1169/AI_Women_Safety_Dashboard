"""
coordinator/models.py — ORM models + Pydantic schemas for SafeSphere.

Tables:
  - users           — App users (women)
  - family_contacts — Trusted contacts per user
  - journeys        — Trip sessions (origin → destination with route)
  - gps_pings       — Real-time GPS locations during journey
  - alerts          — Threat alerts from edge AI cameras
  - cameras         — Registered CCTV camera nodes
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import (
    Column, String, Float, Boolean, Integer, DateTime, Text, ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from pydantic import BaseModel, EmailStr, Field

from coordinator.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# ORM Models
# ═══════════════════════════════════════════════════════════════════════════

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    fcm_token = Column(String, nullable=True)  # Firebase push token from phone
    created_at = Column(DateTime, default=_now)

    family_contacts = relationship("FamilyContact", back_populates="user", cascade="all, delete-orphan")
    journeys = relationship("Journey", back_populates="user", cascade="all, delete-orphan")


class FamilyContact(Base):
    __tablename__ = "family_contacts"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    relationship_label = Column(String, default="Family")
    notify_on_journey = Column(Boolean, default=True)
    notify_on_alert = Column(Boolean, default=True)
    fcm_token = Column(String, nullable=True)  # If family member also has the app
    created_at = Column(DateTime, default=_now)

    user = relationship("User", back_populates="family_contacts")


class Journey(Base):
    __tablename__ = "journeys"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String, default="planned")  # planned → active → completed / sos / cancelled

    # Origin
    start_lat = Column(Float, nullable=False)
    start_lng = Column(Float, nullable=False)
    start_address = Column(String, nullable=True)

    # Destination
    end_lat = Column(Float, nullable=False)
    end_lng = Column(Float, nullable=False)
    end_address = Column(String, nullable=True)

    # Route (JSON string — polyline from Google Maps)
    route_polyline = Column(Text, nullable=True)
    route_summary = Column(String, nullable=True)
    distance_m = Column(Float, nullable=True)
    duration_s = Column(Float, nullable=True)

    created_at = Column(DateTime, default=_now)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="journeys")
    gps_pings = relationship("GpsPing", back_populates="journey", cascade="all, delete-orphan")


class GpsPing(Base):
    __tablename__ = "gps_pings"

    id = Column(String, primary_key=True, default=_uuid)
    journey_id = Column(String, ForeignKey("journeys.id"), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    speed_mps = Column(Float, nullable=True)
    accuracy_m = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=_now)

    journey = relationship("Journey", back_populates="gps_pings")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String, primary_key=True, default=_uuid)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=True, index=True)
    journey_id = Column(String, nullable=True, index=True)
    user_id = Column(String, nullable=True, index=True)

    track_id = Column(Integer, nullable=True)
    threat_level = Column(String, nullable=False)  # NONE, LOW, MEDIUM, HIGH
    threat_score = Column(Float, nullable=False)
    alert_type = Column(String, default="threat")  # threat, blind_spot, sos

    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_name = Column(String, nullable=True)

    details = Column(Text, nullable=True)  # JSON blob with extra info
    snapshot_url = Column(String, nullable=True)  # URL to evidence snapshot

    notified_user = Column(Boolean, default=False)
    notified_family = Column(Boolean, default=False)
    notified_security = Column(Boolean, default=False)
    acknowledged = Column(Boolean, default=False)

    created_at = Column(DateTime, default=_now)

    camera = relationship("Camera", back_populates="alerts")


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    status = Column(String, default="online")  # online, offline
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    coverage_radius_m = Column(Float, default=40.0)

    fps = Column(Float, nullable=True)
    person_count = Column(Integer, default=0)
    last_heartbeat = Column(DateTime, nullable=True)

    source_url = Column(String, nullable=True)
    linked_camera_id = Column(String, nullable=True)
    transit_distance_m = Column(Float, nullable=True)

    created_at = Column(DateTime, default=_now)

    alerts = relationship("Alert", back_populates="camera")


class TransitLog(Base):
    __tablename__ = "transit_logs"

    id = Column(String, primary_key=True, default=_uuid)
    from_camera_id = Column(String, ForeignKey("cameras.id"), nullable=False, index=True)
    to_camera_id = Column(String, ForeignKey("cameras.id"), nullable=True, index=True)
    
    # Metadata for matching (MVP: track_id and timestamp)
    track_id = Column(Integer, nullable=False)
    snapshot_url = Column(String, nullable=True)
    
    departure_time = Column(DateTime, default=_now)
    expected_arrival_time = Column(DateTime, nullable=False)
    actual_arrival_time = Column(DateTime, nullable=True)
    
    status = Column(String, default="in_transit")  # in_transit, arrived, delayed, missed
    
    created_at = Column(DateTime, default=_now)

    from_camera = relationship("Camera", foreign_keys=[from_camera_id])
    to_camera = relationship("Camera", foreign_keys=[to_camera_id])


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic Schemas (API request/response)
# ═══════════════════════════════════════════════════════════════════════════

# ── Auth ──────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    name: str
    phone: str = ""
    password: str = Field(min_length=6)

class LoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    phone: str = ""
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class UpdateFcmRequest(BaseModel):
    fcm_token: str

# ── Family ────────────────────────────────────────────────────────────────

class FamilyContactCreate(BaseModel):
    name: str
    phone: str = ""
    email: str = ""
    relationship_label: str = "Family"
    notify_on_journey: bool = True
    notify_on_alert: bool = True

class FamilyContactResponse(BaseModel):
    id: str
    name: str
    phone: str
    email: str
    relationship_label: str
    notify_on_journey: bool
    notify_on_alert: bool

# ── Journey ───────────────────────────────────────────────────────────────

class JourneyCreate(BaseModel):
    start_lat: float
    start_lng: float
    start_address: str = ""
    end_lat: float
    end_lng: float
    end_address: str = ""

class JourneyResponse(BaseModel):
    id: str
    user_id: str
    status: str
    start_lat: float
    start_lng: float
    start_address: Optional[str] = None
    end_lat: float
    end_lng: float
    end_address: Optional[str] = None
    route_polyline: Optional[str] = None
    route_summary: Optional[str] = None
    distance_m: Optional[float] = None
    duration_s: Optional[float] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class JourneyUpdate(BaseModel):
    status: Optional[str] = None

class GpsPingCreate(BaseModel):
    latitude: float
    longitude: float
    speed_mps: float = 0.0
    accuracy_m: float = 0.0

# ── Alert ─────────────────────────────────────────────────────────────────

class AlertCreate(BaseModel):
    camera_id: Optional[str] = None
    journey_id: Optional[str] = None
    track_id: Optional[int] = None
    threat_level: str
    threat_score: float
    alert_type: str = "threat"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    details: Optional[str] = None
    snapshot_url: Optional[str] = None

class AlertResponse(BaseModel):
    id: str
    camera_id: Optional[str] = None
    journey_id: Optional[str] = None
    track_id: Optional[int] = None
    threat_level: str
    threat_score: float
    alert_type: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    details: Optional[str] = None
    notified_user: bool
    notified_family: bool
    notified_security: bool
    created_at: datetime

# ── Camera ────────────────────────────────────────────────────────────────

class CameraRegister(BaseModel):
    name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    coverage_radius_m: float = 40.0
    source_url: Optional[str] = None

class CameraUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    linked_camera_id: Optional[str] = None
    transit_distance_m: Optional[float] = None

class CameraResponse(BaseModel):
    id: str
    name: str
    status: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    coverage_radius_m: float
    fps: Optional[float] = None
    person_count: int
    last_heartbeat: Optional[datetime] = None
    linked_camera_id: Optional[str] = None
    transit_distance_m: Optional[float] = None

class CameraHeartbeat(BaseModel):
    fps: Optional[float] = None
    person_count: int = 0


# ── Transit ───────────────────────────────────────────────────────────────

class TransitDeparture(BaseModel):
    track_id: int
    snapshot_url: Optional[str] = None
    estimated_duration_s: float = 60.0

class TransitArrival(BaseModel):
    track_id: Optional[int] = None
    # In the future: appearance_features: List[float]

class TransitResponse(BaseModel):
    id: str
    from_camera_id: str
    to_camera_id: Optional[str]
    track_id: int
    status: str
    departure_time: datetime
    expected_arrival_time: datetime
    actual_arrival_time: Optional[datetime]
    created_at: datetime
