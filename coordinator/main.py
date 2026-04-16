"""
coordinator/main.py — SafeSphere Cloud API.

Central backend connecting:
  - 📱 Mobile App (user journeys, GPS tracking, alerts)
  - 🖥️ Security Dashboard (camera monitoring, threat analytics)
  - 📹 Edge AI Nodes (threat alerts, camera registration)

Run locally:
    uvicorn coordinator.main:app --host 0.0.0.0 --port 8000

Deploy to Railway/Render:
    Set DATABASE_URL, JWT_SECRET env vars.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from coordinator.database import create_tables
from coordinator.routes import (
    auth, journey, alerts, cameras, feed, transit, family
)

import json

# Configure structured JSON logging for Cloud Logging (Stackdriver/Loki)
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())

logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger("safesphere.coordinator")

# ── Connected WebSocket clients ──────────────────────────────────────────
from coordinator.state import _dashboard_ws, _user_ws


# ── Blind Spot Monitor Task ──────────────────────────────────────────────

async def blind_spot_monitor():
    """Periodically check for overdue transits and raise alerts."""
    from coordinator.database import async_session
    from coordinator.models import TransitLog, Alert
    from sqlalchemy import select, update, and_
    from datetime import datetime, timezone

    logger.info("Blind Spot Monitor Task started")
    while True:
        try:
            async with async_session() as db:
                now = datetime.now(timezone.utc)
                # Find overdue transits
                # Filter for in_transit and now > expected_arrival_time
                result = await db.execute(
                    select(TransitLog)
                    .where(and_(
                        TransitLog.status == "in_transit",
                        TransitLog.expected_arrival_time < now
                    ))
                )
                overdue = result.scalars().all()
                
                for transit in overdue:
                    transit.status = "delayed"
                    
                    # Create Alert
                    alert = Alert(
                        camera_id=transit.from_camera_id,
                        threat_level="MEDIUM",
                        threat_score=0.5,
                        alert_type="blind_spot",
                        location_name="Blind Spot",
                        details=f"Person from Camera {transit.from_camera_id[:8]} did not emerge at Camera {transit.to_camera_id[:8] if transit.to_camera_id else '???'}"
                    )
                    db.add(alert)
                    
                    logger.warning("BLIND SPOT ALERT: Overdue transit for track %d from %s", 
                                   transit.track_id, transit.from_camera_id[:8])
                    
                    # Broadcast alert
                    # (Note: In a modular app, we'd use an event bus, but we'll call broadcast directly here)
                    await broadcast_to_dashboards({
                        "type": "threat_alert",
                        "alert_id": alert.id,
                        "threat_level": alert.threat_level,
                        "alert_type": "blind_spot",
                        "location_name": "Blind Spot Delay",
                    })

                await db.commit()
        except Exception as e:
            logger.error("Error in blind_spot_monitor: %s", e)
            
        await asyncio.sleep(30) # Check every 30s


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SafeSphere Coordinator starting…")
    await create_tables()
    # Launch background task
    asyncio.create_task(blind_spot_monitor())
    logger.info("Database tables created.")
    yield
    logger.info("SafeSphere Coordinator shutting down.")


# ── App ──────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SafeSphere API",
    description="Cloud backend for the SafeSphere safety ecosystem.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Returns 200 if the service is alive and the DB is reachable."""
    from coordinator.database import engine
    from sqlalchemy import select
    from datetime import datetime, timezone
    try:
        # Quick check if DB is alive
        async with engine.connect() as conn:
            await conn.execute(select(1))
        return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}, 503


# ── Routes ───────────────────────────────────────────────────────────────

app.include_router(auth.router, prefix="/api/v1")
app.include_router(journey.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(cameras.router, prefix="/api/v1")
app.include_router(feed.router)
app.include_router(transit.router, prefix="/api/v1")
app.include_router(family.router, prefix="/api/v1")


# ── Dashboard WebSocket (security team) ──────────────────────────────────

@app.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    await websocket.accept()
    _dashboard_ws.append(websocket)
    logger.info("Dashboard connected. Total: %d", len(_dashboard_ws))
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        _dashboard_ws.remove(websocket)
        logger.info("Dashboard disconnected. Total: %d", len(_dashboard_ws))


# ── User WebSocket (mobile app — receives alerts + family tracking) ──────

@app.websocket("/ws/user/{user_id}")
async def user_websocket(websocket: WebSocket, user_id: str):
    await websocket.accept()
    if user_id not in _user_ws:
        _user_ws[user_id] = []
    _user_ws[user_id].append(websocket)
    logger.info("User %s connected via WebSocket", user_id[:8])
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        _user_ws[user_id].remove(websocket)
        if not _user_ws[user_id]:
            del _user_ws[user_id]
        logger.info("User %s disconnected", user_id[:8])


# ── Broadcast helpers ────────────────────────────────────────────────────

async def broadcast_to_dashboards(data: dict) -> None:
    dead = []
    for ws in _dashboard_ws:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _dashboard_ws.remove(ws)


async def broadcast_to_user(user_id: str, data: dict) -> None:
    connections = _user_ws.get(user_id, [])
    dead = []
    for ws in connections:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connections.remove(ws)


# ── Health check ─────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "SafeSphere API",
        "version": "1.0.0",
        "dashboards_connected": len(_dashboard_ws),
        "users_connected": len(_user_ws),
    }


# ── Direct run ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("coordinator.main:app", host="0.0.0.0", port=8000, reload=True)
