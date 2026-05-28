# Perception Platform

Market data ingestion, verification, and analysis platform. Modular pipeline architecture — each module is independently specced, built, and verifiable through the UI.

## Current Modules

| Module | Service | Port | Status |
|--------|---------|------|--------|
| 01 — Data Ingestion | `backend` | 8000 (internal) | Built |
| 02 — Gateway + Frontend | `gateway` / `frontend` | 8080 (internal) / 8090 | Built |

---

## Prerequisites

- Docker Desktop (Mac/Windows) or Docker Engine + Docker Compose (Linux)
- Git
- An Alpaca live trading account — required for real-time WebSocket stream data
  - Register at https://alpaca.markets
  - Navigate to API Keys and generate a live account key pair

---

## First-Time Setup

### 1. Clone the repo

```bash
git clone <your-repo-url>
cd perception-platform
```

### 2. Create your environment file

```bash
cp .env.example .env
```

Open `.env` and fill in your Alpaca credentials:

```
ALPACA_API_KEY=your_key_here
ALPACA_SECRET_KEY=your_secret_here
```

Everything else in `.env.example` has working defaults and does not need to change for local development.

### 3. Start the stack

```bash
docker compose up --build
```

First build takes 3–5 minutes (downloading base images, installing dependencies). Subsequent starts are faster.

### 4. Verify it's running

Wait for all four services to be healthy. You'll see output like:

```
backend   | INFO: Application startup complete.
gateway   | INFO: Gateway starting. Launching health poller.
frontend  | ... [nginx starting]
```

Then open: **http://localhost:8090**

The UI should load immediately. The Pipeline Health view (first view, left nav) shows the status of all subsystems. If the Database card is green, everything is wired up correctly.

---

## Stopping the stack

```bash
docker compose down
```

To also delete the database volume (wipes all stored bar data):

```bash
docker compose down -v
```

---

## Local Development (without Docker)

If you want to run services individually for faster iteration:

### Backend (Module 01)

```bash
cd backend
pip install -r requirements.txt
# Requires a running PostgreSQL + TimescaleDB instance
# Set DATABASE_URL in your environment or .env
uvicorn app.main:app --reload --port 8000
```

### Gateway

```bash
cd gateway
pip install -r requirements.txt
INGESTION_API_URL=http://localhost:8000 uvicorn app.main:app --reload --port 8080
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:3000
# Proxies /api/* to http://localhost:8080 automatically via vite.config.ts
```

For local frontend dev you do not need to set `VITE_GATEWAY_URL` — Vite's dev server proxies API calls to the gateway automatically.

---

## Service Map

```
Browser → http://localhost:8090
  └── nginx (frontend container)
        ├── serves React app (static files)
        └── proxies /api/* → gateway:8080
              └── FastAPI gateway
                    └── proxies to backend:8000
                          └── FastAPI + TimescaleDB
```

All inter-service communication happens on Docker's internal network. Only port 8090 is exposed to your machine for normal use. Port 8080 (gateway) and 8000 (backend) are also exposed for direct API access and debugging.

---

## Adding Tickers

1. Open the UI at http://localhost:8090
2. Navigate to **Data Ingestion → Watchlist & Coverage**
3. Click **Add ticker**, enter a symbol (e.g. `AAPL`), press Enter
4. Historical backfill starts automatically in the background (5 years daily, 90 days intraday)
5. Enable **Live Stream** toggle on any ticker to include it in the WebSocket stream during market hours

---

## Ports Reference

| Port | Service | Notes |
|------|---------|-------|
| 8090 | Frontend (nginx) | Main UI — open this in your browser |
| 8080 | Gateway | Direct API access + SSE stream |
| 8000 | Backend | Module 01 internal API |
| 5432 | TimescaleDB | Direct DB access if needed |

---

## Troubleshooting

**UI loads but all health cards are red**
- Backend may still be starting. Wait 30 seconds and refresh.
- Check `docker compose logs backend` for errors.

**"Module 01 (ingestion) is unreachable" in the UI**
- The backend container failed to start. Run `docker compose logs backend`.
- Most common cause: missing or incorrect Alpaca credentials in `.env`.

**Stream shows as disconnected**
- Expected outside US market hours (9:30am–4:00pm ET, weekdays).
- During market hours: check that at least one ticker has **Live Stream** enabled in the Watchlist view.

**Database errors on startup**
- TimescaleDB may not have finished initialising before the backend started.
- Run `docker compose restart backend` to retry after the DB is ready.

**Frontend not updating after code changes**
- The Docker build compiles the frontend at build time. Run `docker compose up --build frontend` to rebuild.
- For live-reload during development, use `npm run dev` locally (see Local Development above).

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ALPACA_API_KEY` | **Yes** | — | Alpaca API key |
| `ALPACA_SECRET_KEY` | **Yes** | — | Alpaca secret key |
| `DATABASE_URL` | Set by Compose | — | PostgreSQL connection string |
| `INGESTION_API_URL` | Set by Compose | `http://backend:8000` | Gateway → backend URL |
| `GATEWAY_PORT` | No | `8080` | Gateway port |
| `SSE_KEEPALIVE_SECONDS` | No | `30` | SSE keepalive ping interval |
| `STREAM_RESOLUTIONS` | No | `1m,5m` | Resolutions for live stream |
| `STREAM_FALLBACK_POLL_SECONDS` | No | `60` | Poll interval on stream drop |
| `MAX_WATCHLIST_SIZE` | No | `50` | Max tickers in watchlist |
| `MAX_STREAM_TICKERS` | No | `25` | Max tickers in live stream |

---

## Running Tests

Unit tests (no running stack required):

```bash
cd backend
pip install -r requirements.txt pytest pytest-asyncio
pytest tests/test_validation.py -v
```

Acceptance tests (requires full stack running):

```bash
cd backend
pytest tests/test_acceptance.py -v
```
