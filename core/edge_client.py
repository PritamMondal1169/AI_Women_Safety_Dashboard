"""
core/edge_client.py — HTTP client for edge node → coordinator communication.

Each edge node uses this client to:
  1. Register itself with the coordinator on startup.
  2. Send periodic heartbeats (FPS, person count, status).
  3. Post threat alerts to the coordinator for multi-stakeholder dispatch.
  4. Fetch active journeys relevant to its camera zone.

All calls are non-blocking with timeouts and retry logic.  If the coordinator
is unreachable, the edge node continues operating in offline mode.
"""

from __future__ import annotations

import json
import logging
import time
import threading
from typing import Any, Dict, List, Optional

import requests
import websocket

logger = logging.getLogger("safesphere.edge_client")


class EdgeClient:
    """
    HTTP client for edge → coordinator API calls.
    
    Args:
        coordinator_url: Base URL of the coordinator (e.g. "http://localhost:8000")
        camera_id: This edge node's camera ID (set after registration)
        timeout_s: HTTP request timeout.
        max_retries: Number of retry attempts on failure.
    """

    def __init__(
        self,
        coordinator_url: Optional[str] = None,
        camera_id: Optional[str] = None,
        timeout_s: float = 3.0,
        max_retries: int = 2,
    ) -> None:
        self._base_url = coordinator_url.rstrip("/") if coordinator_url else None
        self.camera_id = camera_id
        self._timeout = timeout_s
        self._max_retries = max_retries
        self._online = False
        self._last_heartbeat: float = 0.0
        
        self._ws_url = self._base_url.replace("http://", "ws://").replace("https://", "wss://") if self._base_url else None
        self._ws = None
        self._ws_lock = threading.Lock()
        
    def _connect_ws(self):
        if not self._ws_url or not self.camera_id:
            return
        url = f"{self._ws_url}/api/v1/ws/edge-feed/{self.camera_id}"
        try:
            self._ws = websocket.create_connection(url, timeout=2.0)
            logger.debug("Connected to Feed Relay WS: %s", url)
        except Exception as e:
            logger.debug("Failed to connect Feed Relay WS: %s", e)
            self._ws = None

    @property
    def is_configured(self) -> bool:
        return self._base_url is not None

    @property
    def is_online(self) -> bool:
        return self._online

    # ── Internal request helper ────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        json_body: Optional[Dict] = None,
        retries: Optional[int] = None,
    ) -> Optional[Dict]:
        """Send an HTTP request with retry logic."""
        if not self._base_url:
            return None

        url = f"{self._base_url}{path}"
        attempts = retries if retries is not None else self._max_retries

        for attempt in range(1, attempts + 1):
            try:
                resp = requests.request(
                    method,
                    url,
                    json=json_body,
                    timeout=self._timeout,
                )
                self._online = True

                if resp.status_code < 300:
                    return resp.json() if resp.text else {}
                else:
                    logger.warning(
                        "Coordinator %s %s → %d: %s",
                        method, path, resp.status_code, resp.text[:200],
                    )
                    return None

            except requests.exceptions.ConnectionError:
                self._online = False
                if attempt == attempts:
                    logger.debug("Coordinator unreachable at %s (attempt %d/%d)", url, attempt, attempts)
                return None
            except requests.exceptions.Timeout:
                self._online = False
                if attempt == attempts:
                    logger.debug("Coordinator timeout: %s (attempt %d/%d)", url, attempt, attempts)
            except Exception:
                logger.exception("Unexpected error calling coordinator: %s %s", method, path)
                return None

        return None

    # ── Public API ────────────────────────────────────────────────────────────

    def register_camera(
        self,
        name: str,
        latitude: float,
        longitude: float,
        coverage_radius_m: float = 50.0,
        source_url: Optional[str] = None,
        linked_camera_id: Optional[str] = None,
        transit_distance_m: Optional[float] = None,
    ) -> Optional[str]:
        """
        Register this edge node with the coordinator.
        
        Returns:
            Camera ID assigned by the coordinator, or None on failure.
        """
        body = {
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
            "coverage_radius_m": coverage_radius_m,
            "source_url": source_url,
            "linked_camera_id": linked_camera_id,
            "transit_distance_m": transit_distance_m,
        }
        result = self._request("POST", "/api/v1/cameras/register", body)
        if result and "id" in result:
            self.camera_id = result["id"]
            logger.info("Camera registered with coordinator: %s", self.camera_id)
            return self.camera_id
        return None

    def heartbeat(
        self,
        fps: float = 0.0,
        person_count: int = 0,
        status: str = "online",
    ) -> bool:
        """Send a heartbeat to the coordinator. Returns True on success."""
        if not self.camera_id:
            return False

        now = time.monotonic()
        # Don't send heartbeats more often than every 10s
        if now - self._last_heartbeat < 10.0:
            return True

        result = self._request(
            "POST",
            f"/api/v1/cameras/{self.camera_id}/heartbeat",
            {"fps": fps, "person_count": person_count, "status": status},
            retries=1,
        )
        self._last_heartbeat = now
        return result is not None

    def post_alert(
        self,
        threat_level: str,
        threat_score: float,
        track_id: int = -1,
        journey_id: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        location_name: Optional[str] = None,
        snapshot_path: Optional[str] = None,
        alert_type: str = "threat",
        details: Optional[str] = None,
    ) -> Optional[Dict]:
        """Post a threat alert to the coordinator."""
        body = {
            "camera_id": self.camera_id,
            "journey_id": journey_id,
            "track_id": track_id,
            "threat_level": threat_level,
            "threat_score": threat_score,
            "latitude": latitude,
            "longitude": longitude,
            "location_name": location_name,
            "snapshot_path": snapshot_path,
            "alert_type": alert_type,
            "details": details,
        }
        return self._request("POST", "/api/v1/alerts", body)

    def get_active_journeys(self) -> List[Dict]:
        """Fetch active journeys from the coordinator."""
        result = self._request("GET", "/api/v1/journey/active", retries=1)
        return result if isinstance(result, list) else []

    def get_cameras(self) -> List[Dict]:
        """Fetch all registered cameras (for topology discovery)."""
        result = self._request("GET", "/api/v1/cameras", retries=1)
        return result if isinstance(result, list) else []

    def push_frame(self, frame_bytes: bytes) -> bool:
        """Push a JPEG frame to the coordinator's WebSocket relay."""
        if not self._ws_url or not self.camera_id:
            return False
            
        with self._ws_lock:
            if self._ws is None:
                self._connect_ws()
            if self._ws is None:
                return False
                
            try:
                self._ws.send_binary(frame_bytes)
                return True
            except Exception as e:
                logger.debug("WS send error: %s", e)
                try:
                    self._ws.close()
                except:
                    pass
                self._ws = None
                return False

    def report_departure(self, track_id: int, snapshot_url: Optional[str] = None):
        """Report a person departing the camera view toward a blind spot."""
        payload = {"track_id": track_id, "snapshot_url": snapshot_url}
        return self._request("POST", f"/api/v1/cameras/{self.camera_id}/transit-departure", json=payload)

    def report_arrival(self, track_id: int):
        """Report a person arriving from a blind spot."""
        payload = {"track_id": track_id}
        return self._request("POST", f"/api/v1/cameras/{self.camera_id}/transit-arrival", json=payload)
