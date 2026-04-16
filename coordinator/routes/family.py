from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coordinator.database import get_db
from coordinator.models import FamilyContact, FamilyContactCreate, FamilyContactResponse, User
from coordinator.routes.auth import get_current_user

logger = logging.getLogger("safesphere.family")
router = APIRouter(tags=["family"])

@router.post("/family", status_code=201, response_model=FamilyContactResponse)
async def add_family_contact(
    body: FamilyContactCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a new trusted guardian/family contact."""
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
    await db.commit()
    await db.refresh(contact)
    logger.info("User %s added family contact: %s", user.id[:8], contact.name)
    return contact

@router.get("/family", response_model=List[FamilyContactResponse])
async def list_family_contacts(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all trusted guardians for the current user."""
    result = await db.execute(
        select(FamilyContact).where(FamilyContact.user_id == user.id)
    )
    return result.scalars().all()

@router.delete("/family/{contact_id}", status_code=204)
async def delete_family_contact(
    contact_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a family contact."""
    contact = await db.get(FamilyContact, contact_id)
    if not contact or contact.user_id != user.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    await db.delete(contact)
    await db.commit()
    logger.info("User %s removed contact %s", user.id[:8], contact_id)
    return None
