"""FastAPI application: REST snapshot + WebSocket stream.

On startup it launches two background tasks — the OpenSky ingestion loop (writer)
and the WebSocket broadcast loop (reader/pusher) — sharing a single Redis store.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .ingest import run_ingestion
from .redis_store import RedisStore
from .ws import ConnectionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = RedisStore()
    manager = ConnectionManager(store)
    stop = asyncio.Event()

    app.state.store = store
    app.state.manager = manager

    ingest_task = asyncio.create_task(run_ingestion(store, stop))
    broadcast_task = asyncio.create_task(manager.broadcast_loop(settings.push_interval, stop))
    logger.info("background tasks started")

    try:
        yield
    finally:
        stop.set()
        await asyncio.gather(ingest_task, broadcast_task, return_exceptions=True)
        await store.close()
        logger.info("shutdown complete")


app = FastAPI(title="Flight Radar API", lifespan=lifespan)

# Dev CORS: allow the Vite frontend. Tighten allow_origins for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    parts = [float(x) for x in bbox.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be 'south,west,north,east'")
    return (parts[0], parts[1], parts[2], parts[3])


@app.get("/health")
async def health() -> dict[str, object]:
    ok = await app.state.store.ping()
    return {"status": "ok", "redis": ok}


@app.get("/api/flights")
async def flights(
    bbox: str = Query(..., description="south,west,north,east in degrees"),
) -> dict[str, object]:
    """One-shot snapshot of flights in a bounding box (initial paint / debugging)."""
    box = _parse_bbox(bbox)
    states = await app.state.store.query_bbox(box)
    return {"count": len(states), "flights": [s.model_dump() for s in states]}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    manager: ConnectionManager = ws.app.state.manager
    conn = await manager.connect(ws)
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "subscribe":
                box = msg.get("bbox")
                if isinstance(box, list) and len(box) == 4:
                    conn.set_bbox((box[0], box[1], box[2], box[3]))
                    # Push an immediate snapshot so the client paints without
                    # waiting for the next broadcast tick.
                    await manager.push_one(conn)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(conn)
