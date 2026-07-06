"""WebSocket connection manager.

Each connected client subscribes to a bounding box (its current map view). On a
fixed interval the manager re-queries Redis for each client's box and pushes only
the delta since that client's last update: which flights are new, which moved, and
which left the box. This keeps bandwidth proportional to change, not to fleet size.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

from .models import FlightState
from .redis_store import RedisStore

logger = logging.getLogger(__name__)

# (south, west, north, east)
BBox = tuple[float, float, float, float]


class Connection:
    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.bbox: BBox | None = None
        # icao24 -> last FlightState we sent this client (for delta computation).
        self.sent: dict[str, FlightState] = {}

    def set_bbox(self, bbox: BBox) -> None:
        self.bbox = bbox
        # New region: forget what we sent so the next tick is a fresh "added" set.
        self.sent = {}


def _changed(old: FlightState, new: FlightState) -> bool:
    """Has anything worth re-sending changed? (position/heading/altitude)."""
    return (
        old.latitude != new.latitude
        or old.longitude != new.longitude
        or old.true_track != new.true_track
        or old.geo_altitude != new.geo_altitude
        or old.velocity != new.velocity
    )


class ConnectionManager:
    def __init__(self, store: RedisStore) -> None:
        self.store = store
        self.connections: set[Connection] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> Connection:
        await ws.accept()
        conn = Connection(ws)
        async with self._lock:
            self.connections.add(conn)
        logger.info("client connected (%d total)", len(self.connections))
        return conn

    async def disconnect(self, conn: Connection) -> None:
        async with self._lock:
            self.connections.discard(conn)
        logger.info("client disconnected (%d total)", len(self.connections))

    async def push_one(self, conn: Connection) -> None:
        """Compute and send the delta for a single connection."""
        if conn.bbox is None:
            return

        current = await self.store.query_bbox(conn.bbox)
        current_by_id = {s.icao24: s for s in current}

        added, updated = [], []
        for icao24, state in current_by_id.items():
            prev = conn.sent.get(icao24)
            if prev is None:
                added.append(state)
            elif _changed(prev, state):
                updated.append(state)

        removed = [i for i in conn.sent if i not in current_by_id]

        conn.sent = current_by_id

        if not (added or updated or removed):
            return  # nothing changed; stay quiet

        await conn.ws.send_json(
            {
                "type": "update",
                "added": [s.model_dump() for s in added],
                "updated": [s.model_dump() for s in updated],
                "removed": removed,
            }
        )

    async def broadcast_loop(self, interval: float, stop: asyncio.Event) -> None:
        """Every ``interval`` seconds, push deltas to all connected clients."""
        while not stop.is_set():
            async with self._lock:
                conns = list(self.connections)
            for conn in conns:
                try:
                    await self.push_one(conn)
                except Exception:  # noqa: BLE001 — one bad client shouldn't stop the loop
                    logger.debug("push failed for a client; dropping", exc_info=True)
                    await self.disconnect(conn)
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
