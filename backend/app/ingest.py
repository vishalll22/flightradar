"""Ingestion loop: poll OpenSky, normalize, write the snapshot into Redis.

Runs as a single long-lived asyncio task (started from main.py's lifespan). It is
the only writer to Redis, which keeps the store consistent and lets the API layer
scale out as stateless readers.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from .config import settings
from .opensky import OpenSkyClient
from .redis_store import RedisStore

logger = logging.getLogger(__name__)


async def run_ingestion(store: RedisStore, stop: asyncio.Event) -> None:
    client = OpenSkyClient()
    # Backoff grows on repeated failures (rate limits / outages), capped.
    backoff = settings.poll_interval
    try:
        while not stop.is_set():
            try:
                states = await client.get_states()
                count = await store.write_snapshot(states)
                logger.info("ingested %d flights", count)
                backoff = settings.poll_interval  # reset on success
                delay = settings.poll_interval
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 429:
                    backoff = min(backoff * 2, 120)
                    logger.warning("OpenSky rate-limited (429); backing off %.0fs", backoff)
                else:
                    logger.warning("OpenSky HTTP %s; retrying", status)
                delay = backoff
            except Exception:  # noqa: BLE001 — keep the loop alive on any error
                logger.exception("ingestion cycle failed; retrying")
                delay = backoff

            # Sleep, but wake immediately if we're asked to stop.
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
    finally:
        await client.close()
        logger.info("ingestion loop stopped")
