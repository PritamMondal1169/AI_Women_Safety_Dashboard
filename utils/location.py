"""
utils/location.py — Geolocation provider for the Women Safety Product.

Strategy (waterfall, best-available):
  1. Google Maps Geolocation + Geocoding API  — precise; requires API key.
  2. ip-api.com free endpoint                 — city-level; no key needed.
  3. Stale cache                              — returned on network failure.
  4. Hard fallback                            — "Location unavailable".

Location is resolved once at startup and cached for CACHE_TTL seconds
(default 5 min).  A background daemon thread keeps the cache warm so the
CV loop always gets a non-blocking response from get().

Usage:
    from utils.location import LocationProvider, LocationFix

    loc = LocationProvider()
    loc.start_background_refresh()
    fix = loc.get()                  # LocationFix (never raises)
    print(fix.display)               # "Kolkata, West Bengal, India (22.5726°, 88.3639°)"
    print(fix.maps_url)              # "https://www.google.com/maps?q=22.572600,88.363900"
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

from config import cfg
from utils.logger import get_logger

log = get_logger(__name__)

_CACHE_TTL: int = 300          # seconds before location is considered stale
_HTTP_TIMEOUT: int = 5         # seconds per HTTP request

_IP_API_URL = (
    "http://ip-api.com/json/"
    "?fields=status,city,regionName,country,lat,lon,query"
)
_GMAPS_GEO_URL     = "https://www.googleapis.com/geolocation/v1/geolocate"
_GMAPS_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


# ---------------------------------------------------------------------------
# LocationFix — immutable position snapshot
# ---------------------------------------------------------------------------
@dataclass
class LocationFix:
    """A resolved geographic position."""

    city: str    = "Unknown"
    region: str  = ""
    country: str = "Unknown"
    lat: float   = 0.0
    lon: float   = 0.0
    source: str  = "none"
    timestamp: float = field(default_factory=time.time)

    @property
    def display(self) -> str:
        """Human-readable one-liner: "City, Region, Country (lat°, lon°)"."""
        parts = [p for p in [self.city, self.region, self.country]
                 if p and p != "Unknown"]
        geo = (f" ({self.lat:.4f}°, {self.lon:.4f}°)"
               if (self.lat or self.lon) else "")
        return ", ".join(parts) + geo if parts else "Location unavailable"

    @property
    def maps_url(self) -> str:
        """Google Maps URL for this position (empty string if no coordinates)."""
        if self.lat == 0.0 and self.lon == 0.0:
            return ""
        return f"https://www.google.com/maps?q={self.lat:.6f},{self.lon:.6f}"


# ---------------------------------------------------------------------------
# LocationProvider
# ---------------------------------------------------------------------------
class LocationProvider:
    """
    Thread-safe geolocation provider with background cache refresh.

    Args:
        cache_ttl: Seconds before the cached fix is considered stale.
    """

    def __init__(self, cache_ttl: int = _CACHE_TTL) -> None:
        self._cache_ttl = cache_ttl
        self._cache: Optional[LocationFix] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        log.info(
            "LocationProvider | google={g} | ip_fallback={i} | ttl={t}s",
            g=bool(cfg.LOCATION_GOOGLE_API_KEY),
            i=cfg.LOCATION_IP_FALLBACK,
            t=cache_ttl,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self) -> LocationFix:
        """
        Return the current LocationFix.

        Fetches synchronously on the first call; subsequent calls return
        the cached value (non-blocking).
        """
        with self._lock:
            if self._cache is not None and not self._is_stale():
                return self._cache

        fix = self._fetch()
        with self._lock:
            self._cache = fix
        return fix

    def get_display(self) -> str:
        return self.get().display

    def start_background_refresh(self) -> None:
        """Launch a daemon thread that refreshes the cache every cache_ttl/2 s."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._refresh_loop,
            name="LocationRefresh",
            daemon=True,
        )
        self._thread.start()
        log.info("Location background refresh thread started.")

    def stop(self) -> None:
        """Signal the refresh thread to stop."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        log.info("LocationProvider stopped.")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _is_stale(self) -> bool:
        if self._cache is None:
            return True
        return (time.time() - self._cache.timestamp) > self._cache_ttl

    def _refresh_loop(self) -> None:
        interval = max(self._cache_ttl // 2, 30)
        log.debug("Location refresh loop: interval={i}s", i=interval)
        while not self._stop.wait(timeout=interval):
            fix = self._fetch()
            with self._lock:
                self._cache = fix
            log.debug("Location refreshed: {d}", d=fix.display)

    def _fetch(self) -> LocationFix:
        """Run the provider waterfall."""
        if cfg.LOCATION_GOOGLE_API_KEY:
            fix = self._google()
            if fix:
                return fix

        if cfg.LOCATION_IP_FALLBACK:
            fix = self._ip_api()
            if fix:
                return fix

        with self._lock:
            if self._cache is not None:
                log.warning("All providers failed — using stale cache.")
                return self._cache

        log.error("All location providers failed.")
        return LocationFix(city="Location unavailable", source="fallback")

    def _google(self) -> Optional[LocationFix]:
        try:
            r = requests.post(
                _GMAPS_GEO_URL,
                params={"key": cfg.LOCATION_GOOGLE_API_KEY},
                json={"considerIp": True},
                timeout=_HTTP_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            lat = data["location"]["lat"]
            lon = data["location"]["lng"]

            gc = requests.get(
                _GMAPS_GEOCODE_URL,
                params={
                    "latlng": f"{lat},{lon}",
                    "key": cfg.LOCATION_GOOGLE_API_KEY,
                    "result_type": "locality|administrative_area_level_1|country",
                },
                timeout=_HTTP_TIMEOUT,
            )
            gc.raise_for_status()
            city = region = country = ""
            for comp in gc.json().get("results", [{}])[0].get("address_components", []):
                types = comp.get("types", [])
                if "locality"                    in types: city    = comp["long_name"]
                if "administrative_area_level_1" in types: region  = comp["long_name"]
                if "country"                     in types: country = comp["long_name"]
            return LocationFix(city=city or "Unknown", region=region,
                               country=country or "Unknown",
                               lat=lat, lon=lon, source="google")
        except requests.exceptions.ConnectionError:
            log.warning("Google geolocation: no network.")
        except requests.exceptions.Timeout:
            log.warning("Google geolocation: timeout.")
        except Exception:
            log.exception("Google geolocation error.")
        return None

    def _ip_api(self) -> Optional[LocationFix]:
        try:
            r = requests.get(_IP_API_URL, timeout=_HTTP_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            if data.get("status") != "success":
                log.warning("ip-api: status={s}", s=data.get("status"))
                return None
            return LocationFix(
                city=data.get("city", "Unknown"),
                region=data.get("regionName", ""),
                country=data.get("country", "Unknown"),
                lat=float(data.get("lat", 0.0)),
                lon=float(data.get("lon", 0.0)),
                source="ip-api",
            )
        except requests.exceptions.ConnectionError:
            log.warning("ip-api: no network.")
        except requests.exceptions.Timeout:
            log.warning("ip-api: timeout.")
        except Exception:
            log.exception("ip-api error.")
        return None
