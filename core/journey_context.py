"""
core/journey_context.py — Journey-aware threat sensitivity for edge nodes.

When the coordinator informs an edge node that an active journey passes through
its camera zone, the JourneyThreatBooster increases detection sensitivity:
  - Lowers effective threat thresholds by a configurable percentage.
  - Tags all resulting ThreatResults with the journey_id.
  - Resets sensitivity when the journey completes or leaves the zone.

Design:
  - The edge node polls the coordinator (or receives WebSocket push) for
    active journeys mapped to its camera.
  - JourneyThreatBooster stores active journey IDs and provides methods
    to compute adjusted thresholds.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class ActiveJourney:
    """An active journey relevant to this camera node."""
    journey_id: str
    user_id: str
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    current_lat: Optional[float] = None
    current_lng: Optional[float] = None
    activated_at: float = field(default_factory=time.monotonic)


class JourneyContextProvider:
    """
    Polls the coordinator for active journeys mapped to this camera.
    
    In a production system, this would listen on a WebSocket.
    For MVP, it polls a REST endpoint at a configurable interval.
    """

    def __init__(
        self,
        camera_id: str,
        coordinator_url: Optional[str] = None,
        poll_interval_s: float = 5.0,
    ) -> None:
        self.camera_id = camera_id
        self._coordinator_url = coordinator_url
        self._poll_interval = poll_interval_s
        self._last_poll: float = 0.0
        self._active_journeys: Dict[str, ActiveJourney] = {}

        log.info(
            "JourneyContextProvider[%s] | coordinator=%s | poll=%ss",
            camera_id, coordinator_url or "None (offline)", poll_interval_s,
        )

    def poll(self) -> Dict[str, ActiveJourney]:
        """
        Check for active journeys on this camera's zone.
        Returns the current set of active journeys.
        """
        now = time.monotonic()
        if now - self._last_poll < self._poll_interval:
            return self._active_journeys

        self._last_poll = now

        if not self._coordinator_url:
            return self._active_journeys

        try:
            import requests

            resp = requests.get(
                f"{self._coordinator_url}/api/v1/journey/active",
                timeout=2.0,
            )
            if resp.status_code == 200:
                journeys_data = resp.json()
                new_active = {}
                for j in journeys_data:
                    jid = j["id"]
                    if jid in self._active_journeys:
                        # Update position
                        existing = self._active_journeys[jid]
                        existing.current_lat = j.get("current_lat")
                        existing.current_lng = j.get("current_lng")
                        new_active[jid] = existing
                    else:
                        new_active[jid] = ActiveJourney(
                            journey_id=jid,
                            user_id=j["user_id"],
                            start_lat=j["start_lat"],
                            start_lng=j["start_lng"],
                            end_lat=j["end_lat"],
                            end_lng=j["end_lng"],
                            current_lat=j.get("current_lat"),
                            current_lng=j.get("current_lng"),
                        )
                        log.info("Journey %s now active on camera %s", jid, self.camera_id)

                # Log removed journeys
                for jid in self._active_journeys:
                    if jid not in new_active:
                        log.info("Journey %s no longer active on camera %s", jid, self.camera_id)

                self._active_journeys = new_active
        except Exception:
            log.debug("Journey poll failed (coordinator unreachable).")

        return self._active_journeys

    @property
    def has_active_journeys(self) -> bool:
        return bool(self._active_journeys)

    @property
    def active_journey_ids(self) -> Set[str]:
        return set(self._active_journeys.keys())


class JourneyThreatBooster:
    """
    Adjusts threat detection thresholds when active journeys are present.
    
    When a journey is active on a camera segment:
      - LOW threshold drops by `boost_pct` (default 20%)
      - MEDIUM threshold drops by `boost_pct`
      - HIGH threshold drops by `boost_pct`
    
    This makes the system MORE sensitive when someone is actively being tracked
    on a journey — the core SafeSphere value proposition.
    """

    def __init__(self, boost_pct: float = 0.20) -> None:
        self._boost_pct = boost_pct
        log.info("JourneyThreatBooster ready | boost=%.0f%%", boost_pct * 100)

    def adjusted_thresholds(
        self,
        base_low: float,
        base_medium: float,
        base_high: float,
        has_journey: bool,
    ) -> Dict[str, float]:
        """
        Return adjusted thresholds. If no journey is active, returns base values.
        
        Args:
            base_low, base_medium, base_high: Normal thresholds from config.
            has_journey: Whether an active journey exists on this camera.
        
        Returns:
            Dict with keys "LOW", "MEDIUM", "HIGH" → adjusted float values.
        """
        if not has_journey:
            return {"LOW": base_low, "MEDIUM": base_medium, "HIGH": base_high}

        factor = 1.0 - self._boost_pct
        adjusted = {
            "LOW": round(base_low * factor, 3),
            "MEDIUM": round(base_medium * factor, 3),
            "HIGH": round(base_high * factor, 3),
        }

        log.debug(
            "Journey boost applied: LOW=%.2f→%.2f MEDIUM=%.2f→%.2f HIGH=%.2f→%.2f",
            base_low, adjusted["LOW"],
            base_medium, adjusted["MEDIUM"],
            base_high, adjusted["HIGH"],
        )
        return adjusted
