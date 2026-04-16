"""
coordinator/routes/feed.py — WebSocket relay for live camera frames (Multi-Node Support).

Edge AI nodes push processed frames here.
Security Dashboards subscribe here with camera-specific routing.
"""

from __future__ import annotations
import base64
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("safesphere.feed")
router = APIRouter(tags=["feed"])

# Dashboard viewers (Security team)
_feed_viewers: list[WebSocket] = []


@router.websocket("/ws/processed-feed")
async def dashboard_feed_ws(websocket: WebSocket):
    """Dashboards connect here to view all live streams."""
    await websocket.accept()
    _feed_viewers.append(websocket)
    logger.info("Dashboard feed viewer connected. Total: %d", len(_feed_viewers))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _feed_viewers.remove(websocket)


@router.websocket("/ws/edge-feed/{camera_id}")
async def edge_feed_ws(websocket: WebSocket, camera_id: str):
    """Edge AI node connects here to push frames (binary JPEG)."""
    await websocket.accept()
    logger.info("Edge %s connected to feed relay", camera_id)
    try:
        while True:
            # Receive JPEG frame from edge
            frame_bytes = await websocket.receive_bytes()
            
            # Encode to base64 for multiplexed delivery
            b64_frame = base64.b64encode(frame_bytes).decode('utf-8')
            payload = {
                "type": "frame_update",
                "camera_id": camera_id,
                "frame": f"data:image/jpeg;base64,{b64_frame}",
                "timestamp": base64.time.time() if hasattr(base64, 'time') else __import__('time').time()
            }
            
            # Broadcast to all connected dashboards
            dead = []
            for viewer in _feed_viewers:
                try:
                    await viewer.send_json(payload)
                except Exception:
                    dead.append(viewer)
            for viewer in dead:
                _feed_viewers.remove(viewer)

    except WebSocketDisconnect:
        logger.info("Edge %s disconnected from feed relay", camera_id)
