"""Async OpenSky Network client.

Supports OpenSky's current OAuth2 client-credentials flow, falls back to legacy
HTTP basic auth, and finally to anonymous access (with tighter rate limits).

Only the pieces the app needs are implemented: fetching the global state snapshot
(optionally constrained to a bounding box).
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from .config import settings
from .models import FlightState

logger = logging.getLogger(__name__)


class OpenSkyClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=30.0)
        self._token: str | None = None
        self._token_expiry: float = 0.0

    async def close(self) -> None:
        await self._client.aclose()

    # --- auth -------------------------------------------------------------
    async def _get_token(self) -> str | None:
        """Return a valid OAuth2 access token, refreshing if near expiry."""
        if not settings.has_oauth:
            return None
        # Refresh 30s before actual expiry to avoid edge-of-expiry 401s.
        if self._token and time.monotonic() < self._token_expiry - 30:
            return self._token

        resp = await self._client.post(
            settings.opensky_token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.opensky_client_id,
                "client_secret": settings.opensky_client_secret,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        # expires_in is seconds from now.
        self._token_expiry = time.monotonic() + float(payload.get("expires_in", 300))
        logger.info("Obtained OpenSky OAuth2 token (expires in %ss)", payload.get("expires_in"))
        return self._token

    async def _auth_kwargs(self) -> dict[str, Any]:
        """Build per-request auth (bearer header, basic auth, or nothing)."""
        token = await self._get_token()
        if token:
            return {"headers": {"Authorization": f"Bearer {token}"}}
        if settings.has_basic_auth:
            return {"auth": (settings.opensky_username, settings.opensky_password)}
        return {}

    # --- data -------------------------------------------------------------
    async def get_states(
        self, bbox: tuple[float, float, float, float] | None = None
    ) -> list[FlightState]:
        """Fetch current aircraft states.

        bbox, if given, is (south, west, north, east) in degrees. When omitted,
        the full global snapshot is returned.
        """
        params: dict[str, float] = {}
        if bbox is not None:
            south, west, north, east = bbox
            params = {"lamin": south, "lomin": west, "lamax": north, "lomax": east}

        auth = await self._auth_kwargs()
        resp = await self._client.get(
            f"{settings.opensky_base_url}/states/all", params=params, **auth
        )
        resp.raise_for_status()
        data = resp.json()

        rows = data.get("states") or []
        states: list[FlightState] = []
        for row in rows:
            fs = FlightState.from_state_vector(row)
            if fs is not None:
                states.append(fs)
        return states
