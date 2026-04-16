"""
coordinator/routes/auth.py — User registration, login, family management.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coordinator.database import get_db
from coordinator.auth import hash_password, verify_password, create_access_token, decode_token
from coordinator.models import (
    User, FamilyContact,
    RegisterRequest, LoginRequest, UserResponse, TokenResponse,
    FamilyContactCreate, FamilyContactResponse, UpdateFcmRequest,
)

router = APIRouter(tags=["auth"])


# ── Helper: extract current user from JWT ─────────────────────────────────

async def get_current_user(
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(401, "Invalid or expired token")
    user = await db.get(User, payload["sub"])
    if not user:
        raise HTTPException(401, "User not found")
    return user


# ── Register ──────────────────────────────────────────────────────────────

@router.post("/auth/register", status_code=201, response_model=UserResponse)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Email already registered")

    user = User(
        email=body.email,
        name=body.name,
        phone=body.phone,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.flush()
    return UserResponse(
        id=user.id, email=user.email, name=user.name,
        phone=user.phone or "", created_at=user.created_at,
    )


# ── Login ─────────────────────────────────────────────────────────────────

@router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")

    token = create_access_token({"sub": user.id, "email": user.email})
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user.id, email=user.email, name=user.name,
            phone=user.phone or "", created_at=user.created_at,
        ),
    )


# ── Get current user profile ─────────────────────────────────────────────

@router.get("/auth/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return UserResponse(
        id=user.id, email=user.email, name=user.name,
        phone=user.phone or "", created_at=user.created_at,
    )


# ── Update FCM token (for push notifications) ────────────────────────────

@router.post("/auth/fcm-token")
async def update_fcm_token(
    body: UpdateFcmRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.fcm_token = body.fcm_token
    await db.flush()
    return {"status": "ok"}


# ── Family contacts ──────────────────────────────────────────────────────

@router.post("/auth/family", status_code=201, response_model=FamilyContactResponse)
async def add_family(
    body: FamilyContactCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contact = FamilyContact(
        user_id=user.id,
        name=body.name,
        phone=body.phone,
        email=body.email,
        relationship_label=body.relationship_label,
        notify_on_journey=body.notify_on_journey,
        notify_on_alert=body.notify_on_alert,
    )
    db.add(contact)
    await db.flush()
    return FamilyContactResponse(
        id=contact.id, name=contact.name, phone=contact.phone or "",
        email=contact.email or "", relationship_label=contact.relationship_label,
        notify_on_journey=contact.notify_on_journey,
        notify_on_alert=contact.notify_on_alert,
    )


@router.get("/auth/family", response_model=list[FamilyContactResponse])
async def list_family(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FamilyContact).where(FamilyContact.user_id == user.id)
    )
    contacts = result.scalars().all()
    return [
        FamilyContactResponse(
            id=c.id, name=c.name, phone=c.phone or "", email=c.email or "",
            relationship_label=c.relationship_label,
            notify_on_journey=c.notify_on_journey,
            notify_on_alert=c.notify_on_alert,
        )
        for c in contacts
    ]


@router.delete("/auth/family/{contact_id}")
async def remove_family(
    contact_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FamilyContact).where(
            FamilyContact.id == contact_id,
            FamilyContact.user_id == user.id,
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(404, "Contact not found")
    await db.delete(contact)
    return {"status": "deleted"}
