# Flight Radar

A live flight-tracking web app (Flightradar24-style). A Python backend ingests
global ADS-B data from the **OpenSky Network**, caches current positions in
**Redis** with a geospatial index, and pushes only each client's visible region
over a **WebSocket**. The **React + Leaflet** frontend renders planes on a dark
map, rotates them by heading, and smoothly interpolates their motion between
updates.

```
OpenSky /states/all ──poll──▶ ingestion ──▶ Redis (geo index) ──bbox query──▶ FastAPI WS ──deltas──▶ React/Leaflet
```

## Architecture

| Piece | Where | Responsibility |
|-------|-------|----------------|
| Ingestion loop | `backend/app/ingest.py` | Poll OpenSky, normalize, write a full snapshot to Redis each cycle. The only writer. |
| Redis store | `backend/app/redis_store.py` | `GEOADD` index + per-flight JSON (short TTL). `query_bbox` = BYRADIUS candidates + exact rectangle filter. |
| API / WS | `backend/app/main.py`, `ws.py` | REST snapshot (`/api/flights`) and a `/ws` stream that sends per-client `added/updated/removed` deltas. |
| Frontend | `frontend/src/` | Leaflet dark map, one marker per `icao24`, heading rotation, dead-reckoning interpolation. |

## Prerequisites

- An **OpenSky Network account** (free) for a usable rate limit. Create an API
  client and note the **client id / secret** (OAuth2). Anonymous access works for
  a quick try but is heavily rate-limited.
- Either **Docker Desktop** (recommended) or local **Python 3.13** + **Node 20+**
  + a **Redis** server.

## Configure

```bash
cp backend/.env.example backend/.env
# edit backend/.env and set OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET
```

## Run with Docker (recommended)

```bash
docker compose up --build
```

- Frontend: <http://localhost:8080>
- Backend API: <http://localhost:8000> (e.g. `/health`, `/api/flights?bbox=51,-1,52,1`)

The frontend container (nginx) proxies `/api` and `/ws` to the backend, so the
browser only talks to one origin.

## Run locally without Docker

```bash
# 1. Redis (any instance) — e.g. via Docker just for Redis:
docker run -p 6379:6379 redis:7-alpine

# 2. Backend
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # (Windows)
# source .venv/bin/activate && pip install -r requirements.txt          # (macOS/Linux)
uvicorn app.main:app --reload

# 3. Frontend
cd frontend
npm install
npm run dev   # http://localhost:5173, proxies /api and /ws to :8000
```

## Deploy to Render (from GitHub)

This repo ships a `render.yaml` Blueprint that provisions all three pieces — Redis
(Render "Key Value"), the Docker backend, and the static frontend — in one go.

1. Push this repo to GitHub (already done).
2. On <https://dashboard.render.com> → **New → Blueprint**, connect the repo and
   select `render.yaml`. Render creates `flightradar-redis`, `flightradar-backend`,
   and `flightradar-frontend`.
3. Set the secrets Render leaves blank (they're kept out of git on purpose):
   - **flightradar-backend** → `OPENSKY_CLIENT_ID`, `OPENSKY_CLIENT_SECRET`.
   - Deploy the backend, then copy its public URL (e.g.
     `https://flightradar-backend.onrender.com`).
   - **flightradar-frontend** → `VITE_WS_URL` = that URL with `wss://` and `/ws`,
     e.g. `wss://flightradar-backend.onrender.com/ws`. Then trigger a frontend
     redeploy so the value is baked into the build.
4. Open the frontend URL — planes should stream in.

Notes:
- The browser talks to the backend **cross-origin** (separate URLs); the backend
  already sends permissive CORS and accepts cross-origin WebSockets.
- On Render's **free** tier the backend sleeps after ~15 min idle (first request
  cold-starts in ~30 s, and ingestion pauses while asleep). Move the backend to a
  paid instance for always-on tracking. The static frontend does not sleep.

## How it works (details)

- **Bounding-box querying** — the frontend never asks for "all planes". On every
  `moveend` it sends its current map bounds; the server streams only that box.
- **Deltas, not snapshots** — the server tracks what each client last held and
  sends just what changed, so bandwidth scales with motion, not fleet size.
- **Interpolation** — OpenSky updates every ~5–15 s, so a `requestAnimationFrame`
  loop dead-reckons each plane forward from its last fix using `velocity` +
  `true_track` (`frontend/src/lib/interpolate.js`). Planes glide; they don't jump.
- **TTL expiry** — each `flight:{icao24}` key has a short TTL, so aircraft that
  stop transmitting (landed / out of range) disappear on their own.

## Configuration reference (`backend/.env`)

| Key | Default | Meaning |
|-----|---------|---------|
| `OPENSKY_CLIENT_ID` / `OPENSKY_CLIENT_SECRET` | — | OAuth2 credentials (preferred). |
| `OPENSKY_USERNAME` / `OPENSKY_PASSWORD` | — | Legacy basic auth fallback. |
| `POLL_INTERVAL` | `8` | Seconds between OpenSky polls. |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection. |
| `FLIGHT_TTL` | `60` | Seconds before an unseen plane expires. |
| `PUSH_INTERVAL` | `2` | Seconds between delta pushes to clients. |

## Tests

```bash
cd backend
PYTHONPATH=. .venv/Scripts/python tests/test_integration.py   # end-to-end (uses live OpenSky + in-memory fakeredis)
```

## Scaling notes

- Per-connection region queries are fine for moderate load. The next step is to
  bucket clients into fixed map tiles and compute each tile's delta **once** per
  tick, then fan out — so N viewers of one area cost one query, not N.
- Ingestion is a single writer and can run as its own process, leaving the API
  servers stateless behind a load balancer (Redis is the shared state).
