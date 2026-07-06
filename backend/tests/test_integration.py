"""End-to-end smoke test of the running ASGI app.

Runs the real FastAPI app (lifespan starts the ingestion + broadcast tasks) but
swaps Redis for an in-memory fakeredis so no external services are needed. The
ingestion loop still hits the live OpenSky API, so this doubles as a real data
check.

Run:  .venv/Scripts/python.exe -m pytest tests/test_integration.py -s
or:   .venv/Scripts/python.exe tests/test_integration.py
"""
from __future__ import annotations

import time

import fakeredis.aioredis
from starlette.testclient import TestClient

import app.redis_store as redis_store
from app.main import app

# Route every RedisStore at one shared in-memory fake.
_shared = fakeredis.aioredis.FakeRedis(decode_responses=True)
redis_store.redis.from_url = lambda *a, **k: _shared  # type: ignore[assignment]

LONDON = "51.0,-1.0,52.0,1.0"


def test_end_to_end() -> None:
    with TestClient(app) as client:
        # health
        assert client.get("/health").json()["status"] == "ok"

        # Wait for the first live ingestion cycle to populate Redis.
        deadline = time.time() + 25
        count = 0
        while time.time() < deadline:
            count = client.get(f"/api/flights?bbox={LONDON}").json()["count"]
            if count > 0:
                break
            time.sleep(1)
        print(f"REST /api/flights over London -> {count} flights")
        assert count > 0, "no flights ingested (network/rate-limit?)"

        # WebSocket: subscribe and receive an initial update frame.
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "bbox": [51.0, -1.0, 52.0, 1.0]})
            msg = ws.receive_json()
            assert msg["type"] == "update"
            print(
                "WS update -> added=%d updated=%d removed=%d"
                % (len(msg["added"]), len(msg["updated"]), len(msg["removed"]))
            )
            assert len(msg["added"]) > 0


if __name__ == "__main__":
    test_end_to_end()
    print("OK")
