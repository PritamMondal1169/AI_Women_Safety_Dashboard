"""
coordinator/database.py — Database engine for SafeSphere.

Supports:
  - PostgreSQL via DATABASE_URL env var (for Supabase/Railway cloud deployment)
  - SQLite fallback for local development

Usage:
    from coordinator.database import get_db, create_tables
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# ── Resolve database URL ────────────────────────────────────────────────────

_raw_url = os.environ.get("DATABASE_URL", "")

if _raw_url:
    # Supabase / Railway give postgresql:// — sqlalchemy async needs postgresql+asyncpg://
    if _raw_url.startswith("postgres://"):
        _raw_url = _raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif _raw_url.startswith("postgresql://"):
        _raw_url = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    DATABASE_URL = _raw_url
else:
    DATABASE_URL = "sqlite+aiosqlite:///./safesphere.db"

_is_sqlite = DATABASE_URL.startswith("sqlite")

# ── Engine ──────────────────────────────────────────────────────────────────

# Production tuning for PostgreSQL (ignored for SQLite)
engine_kwargs = {}
if not _is_sqlite:
    engine_kwargs = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 300,
        "pool_pre_ping": True,
        "connect_args": {
            "command_timeout": 30, # seconds
            "prepared_statement_cache_size": 0, # Required for Supabase Transaction Pooler
        }
    }
else:
    engine_kwargs = {
        "connect_args": {"check_same_thread": False}
    }

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    **engine_kwargs,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── Base ────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Dependency ──────────────────────────────────────────────────────────────

async def get_db():
    """FastAPI dependency — yields an async DB session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables():
    """Create all ORM tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
