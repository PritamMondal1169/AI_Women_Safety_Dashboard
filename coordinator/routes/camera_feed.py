"""
coordinator/routes/camera_feed.py — WebSocket relay for mobile phone camera frames.

Flow:
  1. Phone browser sends JPEG frames via /ws/camera-feed
  2. This module stores the latest frame in a shared buffer
  3. mobile_edge.py reads frames via /ws/edge-feed (or HTTP polling)
  4. Processed/annotated frames are pushed back via /ws/processed-feed
  5. Dashboard reads processed frames for live video display

All frames are binary JPEG blobs — no base64 encoding overhead.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

logger = logging.getLogger("safesphere.camera_feed")

router = APIRouter(tags=["camera-feed"])

# ── Shared frame buffers (in-memory, single-process) ──────────────────────────

class FrameBuffer:
    """Thread-safe single-frame buffer for the latest camera frame."""

    def __init__(self):
        self.raw_frame: Optional[bytes] = None
        self.processed_frame: Optional[bytes] = None
        self.raw_timestamp: float = 0.0
        self.processed_timestamp: float = 0.0
        self.frame_count: int = 0
        self.detection_result: dict = {}
        self._raw_event = asyncio.Event()
        self._processed_event = asyncio.Event()

    def set_raw(self, data: bytes) -> None:
        self.raw_frame = data
        self.raw_timestamp = time.time()
        self.frame_count += 1
        self._raw_event.set()
        self._raw_event = asyncio.Event()  # reset for next waiter

    def set_processed(self, data: bytes, result: dict = None) -> None:
        self.processed_frame = data
        self.processed_timestamp = time.time()
        self.detection_result = result or {}
        self._processed_event.set()
        self._processed_event = asyncio.Event()

    async def wait_raw(self, timeout: float = 2.0) -> Optional[bytes]:
        try:
            await asyncio.wait_for(self._raw_event.wait(), timeout)
        except asyncio.TimeoutError:
            pass
        return self.raw_frame

    async def wait_processed(self, timeout: float = 2.0) -> Optional[bytes]:
        try:
            await asyncio.wait_for(self._processed_event.wait(), timeout)
        except asyncio.TimeoutError:
            pass
        return self.processed_frame


# Global shared buffer
frame_buffer = FrameBuffer()

# Track connected clients
_phone_clients: list[WebSocket] = []
_edge_clients: list[WebSocket] = []
_dashboard_feed_clients: list[WebSocket] = []


# ── Phone → Coordinator: Raw camera frames ───────────────────────────────────

@router.websocket("/ws/camera-feed")
async def camera_feed_ws(websocket: WebSocket):
    """
    Receives raw JPEG frames from the phone's camera.
    The phone sends binary blobs (camera.html captures + sends).
    """
    await websocket.accept()
    _phone_clients.append(websocket)
    logger.info("Phone camera connected. Total phones: %d", len(_phone_clients))

    try:
        while True:
            # Receive binary JPEG frame from phone
            data = await websocket.receive_bytes()
            frame_buffer.set_raw(data)

            # Forward to all edge processors
            dead_edges = []
            for edge_ws in _edge_clients:
                try:
                    await edge_ws.send_bytes(data)
                except Exception:
                    dead_edges.append(edge_ws)
            for ws in dead_edges:
                _edge_clients.remove(ws)

            # Send back detection results to phone (if available)
            if frame_buffer.detection_result:
                try:
                    await websocket.send_json(frame_buffer.detection_result)
                except Exception:
                    pass

    except WebSocketDisconnect:
        _phone_clients.remove(websocket)
        logger.info("Phone camera disconnected. Total phones: %d", len(_phone_clients))
    except Exception:
        if websocket in _phone_clients:
            _phone_clients.remove(websocket)


# ── Edge processor ↔ Coordinator ──────────────────────────────────────────────

@router.websocket("/ws/edge-feed")
async def edge_feed_ws(websocket: WebSocket):
    """
    Edge processor connects here to:
    1. RECEIVE raw frames (forwarded from phone)
    2. SEND processed/annotated frames + detection results back

    Protocol:
    - Binary message FROM server → raw JPEG frame to process
    - Binary message FROM edge → processed/annotated JPEG frame
    - Text/JSON message FROM edge → detection results
    """
    await websocket.accept()
    _edge_clients.append(websocket)
    logger.info("Edge processor connected. Total edges: %d", len(_edge_clients))

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"]:
                # Edge sending processed frame
                frame_buffer.set_processed(message["bytes"], frame_buffer.detection_result)

                # Forward processed frame to dashboard viewers
                dead = []
                for dash_ws in _dashboard_feed_clients:
                    try:
                        await dash_ws.send_bytes(message["bytes"])
                    except Exception:
                        dead.append(dash_ws)
                for ws in dead:
                    _dashboard_feed_clients.remove(ws)

            elif "text" in message and message["text"]:
                # Edge sending detection results (JSON)
                import json
                try:
                    result = json.loads(message["text"])
                    frame_buffer.detection_result = result

                    # Forward results to phone
                    for phone_ws in _phone_clients:
                        try:
                            await phone_ws.send_json(result)
                        except Exception:
                            pass

                    # Forward to dashboard feed clients
                    for dash_ws in _dashboard_feed_clients:
                        try:
                            await dash_ws.send_json(result)
                        except Exception:
                            pass

                except json.JSONDecodeError:
                    pass

    except WebSocketDisconnect:
        _edge_clients.remove(websocket)
        logger.info("Edge processor disconnected. Total edges: %d", len(_edge_clients))
    except Exception:
        if websocket in _edge_clients:
            _edge_clients.remove(websocket)


# ── Dashboard: Processed feed viewer ──────────────────────────────────────────

@router.websocket("/ws/processed-feed")
async def processed_feed_ws(websocket: WebSocket):
    """
    Dashboard connects here to receive processed/annotated frames.
    Sends: binary JPEG (annotated frame) + JSON (detection metadata).
    """
    await websocket.accept()
    _dashboard_feed_clients.append(websocket)
    logger.info("Dashboard feed viewer connected. Total: %d", len(_dashboard_feed_clients))

    try:
        while True:
            # Keep alive — client sends pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        _dashboard_feed_clients.remove(websocket)
        logger.info("Dashboard feed viewer disconnected. Total: %d", len(_dashboard_feed_clients))
    except Exception:
        if websocket in _dashboard_feed_clients:
            _dashboard_feed_clients.remove(websocket)


# ── HTTP endpoints for status + snapshots ─────────────────────────────────────

@router.get("/api/v1/camera-feed/status")
async def feed_status():
    """Check camera feed status."""
    return {
        "phone_connected": len(_phone_clients) > 0,
        "edge_connected": len(_edge_clients) > 0,
        "dashboard_viewers": len(_dashboard_feed_clients),
        "frames_received": frame_buffer.frame_count,
        "last_frame_age_s": round(time.time() - frame_buffer.raw_timestamp, 2) if frame_buffer.raw_timestamp else None,
        "detection_result": frame_buffer.detection_result,
    }


@router.get("/api/v1/camera-feed/latest")
async def latest_raw_frame():
    """Return the latest raw JPEG frame from the phone camera (for debugging)."""
    if not frame_buffer.raw_frame:
        return Response(content=b"", status_code=204)
    return Response(
        content=frame_buffer.raw_frame,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/api/v1/camera-feed/processed")
async def latest_processed_frame():
    """Return the latest processed/annotated JPEG frame."""
    if not frame_buffer.processed_frame:
        return Response(content=b"", status_code=204)
    return Response(
        content=frame_buffer.processed_frame,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache"},
    )
