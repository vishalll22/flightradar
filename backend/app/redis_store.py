"""Redis-backed store of current flight positions.

Two structures, rebuilt on every ingestion cycle:

  * ``flights:geo``      — a geo set (GEOADD) mapping icao24 -> lon/lat, used for
                           "which planes are in this bounding box" queries.
  * ``flight:{icao24}``  — a JSON string with the full normalized FlightState,
                           given a short TTL so vanished aircraft expire on their own.

OpenSky hands us a complete world snapshot each poll, so we rebuild the geo set
atomically (write to a temp key, then RENAME over the live one) rather than doing
per-plane diffing on the write side.
"""
from __future__ import annotations

import math

import redis.asyncio as redis

from .config import settings
from .models import FlightState

GEO_KEY = "flights:geo"
GEO_TMP_KEY = "flights:geo:tmp"


def _flight_key(icao24: str) -> str:
    return f"flight:{icao24}"


class RedisStore:
    def __init__(self, url: str | None = None) -> None:
        self._redis = redis.from_url(url or settings.redis_url, decode_responses=True)

    async def close(self) -> None:
        await self._redis.aclose()

    async def ping(self) -> bool:
        return await self._redis.ping()

    async def write_snapshot(self, states: list[FlightState]) -> int:
        """Replace the current world state with ``states``.

        Returns the number of flights written. The geo set is swapped in
        atomically via RENAME so readers never see a half-built index.
        """
        pipe = self._redis.pipeline(transaction=False)
        pipe.delete(GEO_TMP_KEY)

        written = 0
        for s in states:
            # GEOADD into the temp set (member = icao24).
            pipe.geoadd(GEO_TMP_KEY, (s.longitude, s.latitude, s.icao24))
            # Full state as JSON with TTL.
            pipe.set(_flight_key(s.icao24), s.model_dump_json(), ex=settings.flight_ttl)
            written += 1

        if written:
            # Atomically replace the live geo set.
            pipe.rename(GEO_TMP_KEY, GEO_KEY)
        else:
            # Empty snapshot: clear the live set so stale planes don't linger.
            pipe.delete(GEO_KEY)

        await pipe.execute()
        return written

    async def query_bbox(
        self, bbox: tuple[float, float, float, float]
    ) -> list[FlightState]:
        """Return the flights whose position falls inside ``bbox``.

        bbox is (south, west, north, east) in degrees.

        Strategy: use GEOSEARCH BYRADIUS to cheaply narrow to candidates within a
        circle that circumscribes the rectangle, then filter to the exact
        rectangle in Python. This gives precise rectangular results (including
        non-square viewports) and avoids relying on GEOSEARCH BYBOX.
        """
        south, west, north, east = bbox
        center_lon = (west + east) / 2
        center_lat = (south + north) / 2

        # Radius (km) that circumscribes the rectangle: half its diagonal.
        # ~111 km per degree latitude; longitude degrees shrink by cos(lat).
        half_h_km = (north - south) / 2 * 111.0
        half_w_km = (east - west) / 2 * 111.0 * max(math.cos(math.radians(center_lat)), 0.01)
        radius_km = math.hypot(half_h_km, half_w_km)

        ids = await self._redis.geosearch(
            GEO_KEY,
            longitude=center_lon,
            latitude=center_lat,
            radius=max(radius_km, 0.1),
            unit="km",
        )
        if not ids:
            return []

        keys = [_flight_key(i) for i in ids]
        raw = await self._redis.mget(keys)
        out: list[FlightState] = []
        for item in raw:
            if not item:
                continue
            fs = FlightState.model_validate_json(item)
            # Exact rectangle filter — the circle over-selects at the corners.
            if south <= fs.latitude <= north and west <= fs.longitude <= east:
                out.append(fs)
        return out
