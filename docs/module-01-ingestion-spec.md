# Module 01 — Data Ingestion
**Perception Platform · Module Spec Series**

| Field | Value |
|---|---|
| Version | 0.3.0 |
| Status | Draft |
| Module | Foundation |
| Next Module | Transform Layer |

---

## Changelog

| Version | Notes |
|---|---|
| 0.3.0 | ADR-002 revised: Alpaca replaced with Finnhub (free tier, Canada-accessible). ADR-005 updated: Finnhub WebSocket delivers trades/quotes not pre-built bars — bar assembly added to stream mode responsibility. Configuration updated. |
| 0.2.0 | Revised: timeframe-agnostic design. Intraday promoted to first-class. Dual-mode ingestion (stream + fetch). ADR-005 added. Scheduler, storage, and retention policy updated. |
| 0.1.0 | Initial draft. Stack selected, data model defined, API contracted, acceptance criteria written. |

---

## Overview

This document specifies the **Data Ingestion Module** — the first and foundational layer of the Perception Platform. It is responsible for acquiring, validating, storing, and serving raw market data to all downstream modules. No other module touches external data sources. All market data in the system flows through this module.

> **Design Principle:** This module is intentionally dumb. It does not interpret, transform, or derive anything from market data. It collects, validates, stores, and exposes. Transformation is the responsibility of the next module. This boundary must not be crossed.

The module operates in two modes that serve different needs:

- **Stream mode** — a persistent WebSocket connection during market hours delivering live bars as they close. This is the path for intraday pattern detection. Data arrives fast enough to act on.
- **Fetch mode** — REST API calls for historical data, backfill, and end-of-day pulls. This is the path for daily and multi-day cycle analysis.

Both modes are first-class. The system has no preferred timeframe. He picks the lens. The architecture has no opinion about whether a 1-minute bar or a daily bar is more important.

---

## Scope

### In Scope
- OHLCV bar ingestion at all resolutions (1m, 5m, 15m, 1h, daily)
- Ticker watchlist management
- WebSocket stream ingestion during market hours (stream mode)
- REST-based historical and backfill ingestion (fetch mode)
- Automatic fallback from stream to fetch on connection loss
- Data quality validation
- Gap detection and flagging
- Resolution-aware retention policy
- Internal REST API for downstream modules

### Not In Scope
- Any derived or transformed data
- Signal generation of any kind
- User-facing UI
- Order execution or broker connectivity
- Options or futures data
- Fundamental or news data
- Authentication or multi-user
- Tick-level data (sub-bar resolution)

---

## Context

This module is being built for a proprietary trading platform whose downstream modules will perform custom normalized derivative computations and user-defined perception tuning. The operator actively trades intraday cycles as well as multi-day cycles up to approximately 5 trading days. The system must serve both without architectural preference for either.

Intraday pattern detection requires data to arrive fast enough to act on — polled REST data with a 15-minute delay is not sufficient. Live bar streaming is a hard requirement for the intraday use case.

The platform is intended to run locally during development and be deployable to a cloud host without architectural change. No OS-native application layer is required — the system is browser-accessible throughout.

---

## Architecture Decision Records

### ADR-001 · Application Stack

| Field | Detail |
|---|---|
| Status | Accepted |
| Decision | Python + FastAPI backend, React frontend, Docker Compose |

**Context:** The platform needs to handle time-series data processing, market data libraries, and expose a clean API to a browser-based frontend. It must run locally and be deployable without architectural changes.

**Rationale:** Python owns the market data ecosystem — pandas, numpy, every brokerage SDK, and every financial data library targets Python first. FastAPI gives async performance with automatic OpenAPI docs, keeping the spec and the implementation in sync. React gives full flexibility for the custom interfaces this platform will require. Docker Compose means the agent writes one compose file and the operator runs one command in any environment.

**Rejected alternatives:** Node.js backend (weaker data science ecosystem), Django (heavier than required for an API layer), Flask (lacks async and automatic API documentation).

**Consequences:** Docker must be installed on the host. Python version pinned to 3.11+. Frontend and backend run as separate services behind a shared Compose network.

---

### ADR-002 · Data Sources

| Field | Detail |
|---|---|
| Status | Accepted |
| Decision | Finnhub as primary source, yfinance as historical fallback, behind an abstracted connector interface |
| Supersedes | Previous decision used Alpaca Markets — not accessible from Canada |

**Context:** The system needs reliable OHLCV data at all resolutions including real-time intraday. Phase 1 cost must be zero. The operator is based in Canada — Alpaca Markets is not available in Canada. The source layer must be swappable without touching downstream modules.

**Rationale:** Finnhub's free tier provides real-time WebSocket streaming for US equities with no geographic restriction, no account approval wait, and no cost. A single API key is issued immediately on registration. yfinance covers historical REST backfill where Finnhub's free REST tier rate limits apply. The abstracted connector interface means Polygon.io (paid, ~$29/month) can be added as an upgrade path by dropping in a new connector class with no other changes.

**Important architectural difference from Alpaca:** Finnhub's WebSocket stream delivers individual trades and quotes, not pre-assembled OHLCV bars. The stream mode in this module is responsible for assembling trades into bars at the requested resolution before writing to the database. This bar assembly step lives in the ingestion module — it is not a transform and does not belong in the transform layer. See ADR-005 for stream mode details.

**Finnhub free tier limits:**
- REST: 60 API calls/minute
- WebSocket: real-time trades for US equities, no documented connection limit
- Historical: 1 year of daily bars, 1 month of intraday bars via REST

**Rejected alternatives:** Alpaca (not available in Canada), Polygon.io free tier (15-minute delay, not actionable for intraday), yfinance only (no WebSocket support, cannot assemble real-time bars), Alpha Vantage (severe rate limits on free tier, no WebSocket).

**Upgrade path:** Polygon.io Starter (~$29/month) delivers pre-built OHLCV bars via WebSocket, eliminating the bar assembly step and increasing REST rate limits significantly. Switching requires only a new connector class — no other module changes.

**Consequences:** Finnhub API key required (free, instant registration at finnhub.io). US equities only in Phase 1. Bar assembly from raw trades adds a processing step in stream mode. REST rate limit of 60 calls/minute requires careful batching for watchlists larger than ~10 tickers at intraday resolution.

---

### ADR-003 · Storage

| Field | Detail |
|---|---|
| Status | Accepted |
| Decision | PostgreSQL 15 with TimescaleDB extension |

**Context:** The system handles time-series data across multiple resolutions with different retention windows. It needs fast range queries, efficient appends during live streaming, and a storage layer that runs identically locally and in the cloud.

**Rationale:** TimescaleDB handles time-series workloads at scale while remaining standard SQL — no new query language and full compatibility with every Python ORM and analytics library. Automatic time-based partitioning makes resolution-aware retention policies straightforward to implement. The same Docker image runs locally and deploys to any cloud provider that runs containers.

**Rejected alternatives:** SQLite (no concurrent access, poor performance under streaming writes), InfluxDB (query language lock-in, weaker ecosystem), pure file storage (no queryable API, cannot serve downstream modules efficiently).

**Consequences:** TimescaleDB Docker image adds ~300MB to the stack. Schema migrations must be managed explicitly. Backup is standard PostgreSQL tooling.

---

### ADR-004 · Scheduling

| Field | Detail |
|---|---|
| Status | Accepted |
| Decision | APScheduler embedded in the FastAPI process for fetch-mode jobs only |

**Context:** Fetch-mode jobs — EOD pulls, gap audits, backfill — need scheduling. Stream-mode ingestion is event-driven, not scheduled, and is managed by the WebSocket connection lifecycle.

**Rationale:** APScheduler is lightweight, pure Python, and requires no additional service. It is appropriate for the low-frequency fetch-mode job set. Stream mode has no use for a scheduler — it connects at market open and disconnects at close, driven by the market calendar, not a cron pattern.

**Rejected alternatives:** Celery + Redis (significant overhead for this job volume), cron jobs (brittle across environments), external scheduler services (unnecessary cloud dependency).

**Consequences:** Scheduler manages fetch jobs only. Stream lifecycle is managed separately by the WebSocket manager. Missed fetch jobs during downtime are recovered by the gap audit and backfill endpoint.

---

### ADR-005 · Dual-Mode Ingestion

| Field | Detail |
|---|---|
| Status | Accepted |
| Decision | WebSocket streaming for live intraday bars during market hours; REST polling for all historical and daily data |

**Context:** A polled REST architecture introduces up to 15 minutes of latency on intraday data even before free-tier delays are added. Intraday pattern detection requires data to arrive as bars close — not minutes later. However, streaming is unnecessary and wasteful for historical data pulls and daily bar ingestion.

**Rationale:** The two modes serve fundamentally different needs. Stream mode delivers live bars as they close — latency from market event to system is under one second on a normal connection. Fetch mode is simpler, more reliable for historical depth, and appropriate for data that doesn't require real-time delivery. Combining them in one module with a clean handoff gives the system the full capability of both without the complexity of trying to use a WebSocket for historical pulls or REST polling for live data.

**Bar assembly responsibility:** Finnhub's WebSocket delivers individual trades, not pre-built bars. The WebSocket manager in this module accumulates incoming trades into OHLCV bars at the configured resolutions. For each resolution, a bar is considered closed when the bar's time window elapses. Assembly logic: open = first trade price in window, high = max trade price, low = min trade price, close = last trade price, volume = sum of trade sizes. Assembled bars then pass through the standard validation path before being written. This assembly is not a transform — it is raw data normalisation required to produce a consistent storage format.

**Rejected alternatives:** REST polling only (15-minute+ latency, not actionable intraday), WebSocket only (WebSocket APIs do not serve arbitrary historical ranges), third-party event bus (unnecessary complexity for Phase 1), delegating bar assembly to the transform layer (the transform layer must receive clean OHLCV — it must not be responsible for raw data assembly).

**Consequences:** The module must manage WebSocket connection lifecycle — connect at market open, disconnect at close, handle drops and reconnects gracefully. The stream and fetch paths write to the same database tables using the same schema. Downstream modules do not need to know which path delivered a given bar.

> **Fallback rule:** If the WebSocket connection drops during market hours, the module immediately falls back to fetch mode at the highest available poll frequency until the stream reconnects. The gap is logged and backfilled on reconnect. Downstream modules are not notified — the gap appears as normal latency, not an error state.

---

## Data Model

### tickers

The operator's watchlist. Every ticker the system tracks must exist here before data is pulled or streamed for it.

| Column | Type | Notes |
|---|---|---|
| `symbol` | VARCHAR(10) PK | Ticker symbol e.g. `AAPL` |
| `name` | VARCHAR | Human-readable company name |
| `active` | BOOLEAN | Whether to include in stream and scheduled pulls |
| `stream_live` | BOOLEAN | Whether to include in WebSocket stream during market hours |
| `added_at` | TIMESTAMPTZ | When added to watchlist |
| `notes` | TEXT | Optional operator annotation |

> `active` and `stream_live` are independent flags. A ticker can be active for historical fetch without being in the live stream, and vice versa. This lets him monitor a large watchlist historically while streaming only the tickers he is actively watching today.

---

### bars

A single table for all OHLCV bars regardless of resolution. Resolution is a column, not a table-per-resolution. TimescaleDB partitions by `ts` automatically.

| Column | Type | Notes |
|---|---|---|
| `symbol` | VARCHAR(10) FK | References `tickers` |
| `ts` | TIMESTAMPTZ | TimescaleDB partition key. Bar open time. Always timezone-aware. |
| `resolution` | VARCHAR(5) | `1m`, `5m`, `15m`, `1h`, `1d` |
| `open` | NUMERIC(12,4) | |
| `high` | NUMERIC(12,4) | |
| `low` | NUMERIC(12,4) | |
| `close` | NUMERIC(12,4) | |
| `volume` | BIGINT | |
| `flagged` | BOOLEAN | True if bar passed validation but triggered a spike warning |
| `source` | VARCHAR(20) | `alpaca_stream`, `alpaca_fetch`, `yfinance` |
| `ingested_at` | TIMESTAMPTZ | When row was written |

**Unique constraint:** `(symbol, ts, resolution)` — no duplicates, upsert on conflict.

---

### ingestion_log

Audit trail of every fetch job and every stream session. Used to detect gaps, diagnose failures, and drive backfill logic.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `symbol` | VARCHAR(10) | Null for stream sessions covering multiple tickers |
| `mode` | VARCHAR(10) | `stream` or `fetch` |
| `job_type` | VARCHAR(20) | `eod`, `intraday_poll`, `backfill`, `stream_session` |
| `source` | VARCHAR(20) | |
| `status` | VARCHAR(10) | `ok`, `partial`, `failed`, `reconnecting` |
| `rows_written` | INT | |
| `error_msg` | TEXT | Null on success |
| `started_at` | TIMESTAMPTZ | |
| `ended_at` | TIMESTAMPTZ | Null if session still active |

---

## Retention Policy

Raw bars are not kept indefinitely. The value of historical intraday data decays quickly for a system operating on cycles of up to 5 days. Storage is sized to what is actually useful, not to what is available.

| Resolution | Retention | Rationale |
|---|---|---|
| `1m` | 60 days | Enough for intraday pattern calibration and recent backtesting |
| `5m` | 90 days | Slightly longer — used for cycle shape analysis |
| `15m` | 180 days | Broader context, slower decay |
| `1h` | 2 years | Useful for regime detection and multi-day cycle framing |
| `1d` | 5 years | Primary cycle detection resolution, long history needed |

TimescaleDB retention policies enforce these windows automatically. Expired bars are dropped on a nightly job. Downstream modules must not assume bars older than the retention window exist — they should trigger a fetch if historical depth beyond the window is needed for a specific operation such as a backtest.

---

## Source Connectors

Each connector implements a common interface. The ingestion service never calls Alpaca or yfinance directly — it calls the interface. This is the abstraction that makes sources swappable.

### Connector Interface Contract

```python
# Every connector must implement all five methods.
# Return types are pandas DataFrames with standardised column names.

def get_daily_bars(symbol: str, start: date, end: date) -> DataFrame
def get_intraday_bars(symbol: str, resolution: str, start: datetime, end: datetime) -> DataFrame
def stream_bars(symbols: list[str], resolutions: list[str], callback: Callable) -> None
def stop_stream() -> None
def health_check() -> bool

# DataFrame columns returned by fetch methods:
# ts, open, high, low, close, volume
# All numeric columns are float64. ts is timezone-aware.

# callback signature for stream_bars:
# callback(symbol: str, resolution: str, bar: dict) -> None
# bar dict keys: ts, open, high, low, close, volume
```

### Connector: Finnhub (Primary)

Uses the `finnhub-python` SDK for REST calls and the Finnhub WebSocket (`wss://ws.finnhub.io`) for live trade streaming. Requires `FINNHUB_API_KEY` in environment. Free tier, instant registration at finnhub.io, accessible from Canada and internationally.

Implements all five interface methods. `stream_bars` opens the Finnhub WebSocket, subscribes to the requested symbols, and passes incoming trades to the bar assembly logic in the WebSocket manager. The connector itself delivers raw trades to the callback — bar assembly is the WebSocket manager's responsibility, not the connector's.

**REST rate limit:** 60 calls/minute on the free tier. The connector must enforce this limit internally and raise a rate limit error rather than silently queuing, so the caller can decide whether to wait or fall back to yfinance.

### Connector: yfinance (Fallback)

Used for historical backfill only. No API key required. Does not implement `stream_bars` — calling `stream_bars` on this connector raises `NotImplementedError`. If Finnhub stream is unavailable and yfinance is the active connector, the module operates in fetch-only mode and logs a warning.

**Historical depth on free tier:** yfinance provides up to 10 years of daily bars and up to 60 days of 1-minute bars for US equities. Use yfinance for initial historical backfill where Finnhub's 1-year daily / 1-month intraday free tier limits are insufficient.

---

## Validation

Every bar — whether arriving via stream or fetch — passes through the same validation step before being written. The validation path is shared. Source mode does not affect validation rules.

| Check | Rule | On Failure |
|---|---|---|
| OHLC integrity | `high >= low`, `high >= open`, `high >= close` | Reject bar, log warning |
| Zero volume | `volume > 0` | Reject bar, log warning |
| Timestamp order (fetch) | Bars in batch are ascending by `ts` | Reject batch, log error |
| Duplicate detection | No existing row for `(symbol, ts, resolution)` | Skip on upsert, no error |
| Price spike | Close not more than 50% from previous close | Write bar with `flagged=true`, log warning |
| Missing trading days (fetch) | No gaps in expected NYSE calendar | Log gap, queue backfill job |

> **Invariant:** The database contains only validated data. A row in the database passed validation at ingestion time. Downstream modules do not re-validate.

---

## Stream Mode — WebSocket Lifecycle

The WebSocket manager runs as a background task inside the FastAPI process. It is responsible for the full lifecycle of the live data stream.

**Market open (09:30 ET):** Connect to Finnhub WebSocket stream. Subscribe to all tickers where `stream_live = true`. Begin accumulating incoming trades into bars at the resolutions configured in `STREAM_RESOLUTIONS`. Write completed bars to the database via the standard validation path.

**During market hours:** Maintain the connection. On bar receipt, validate and write immediately. Log the stream session as active in `ingestion_log`.

**On connection drop:** Log the drop. Immediately begin fetch-mode polling at `STREAM_FALLBACK_POLL_SECONDS` interval. Attempt WebSocket reconnect every 30 seconds with exponential backoff up to 5 minutes. On successful reconnect, backfill the gap from the fetch data already collected and resume streaming.

**Market close (16:00 ET):** Flush any in-progress bar assembly windows and write final partial bars with a `partial=true` flag. Gracefully disconnect from Finnhub WebSocket. Mark the stream session as ended in `ingestion_log`. Trigger the EOD fetch job to pull official daily closing bars from the REST API, which are used as the authoritative daily close regardless of what the stream produced.

**Pre-market and after-hours:** Stream is not active by default in Phase 1. Can be enabled per-ticker via configuration flag. Monday pre-market is handled by a dedicated fetch job, not the stream.

---

## Fetch Mode — Scheduler

All times are US Eastern. The scheduler respects the NYSE trading calendar — no jobs run on market holidays.

| Job | Schedule | Action |
|---|---|---|
| EOD Daily Bar Pull | Weekdays 16:30 ET | Pull today's official daily bars for all active tickers |
| Stream Fallback Poll | Continuous during market hours if stream is down | Poll at `STREAM_FALLBACK_POLL_SECONDS` interval for `stream_live` tickers |
| Monday Gap Pull | Mondays 08:00 ET | Pull Friday close for weekend gap context before stream opens |
| Gap Audit | Daily 17:00 ET | Compare stored bars against NYSE calendar. Log gaps. Queue backfill. |
| Retention Cleanup | Daily 02:00 ET | Drop bars older than retention window per resolution |

---

## Internal API

The module exposes a REST API consumed by downstream modules only. Not user-facing. All endpoints return JSON. All timestamps are ISO 8601 with timezone.

### Watchlist

| Method | Path | Description |
|---|---|---|
| `GET` | `/tickers` | Return all tickers in watchlist |
| `POST` | `/tickers` | Add a ticker. Triggers automatic historical backfill. |
| `PATCH` | `/tickers/{symbol}` | Update `active`, `stream_live`, or `notes` |
| `DELETE` | `/tickers/{symbol}` | Remove from watchlist. Does not delete historical bars. |

### Data Access

| Method | Path | Description |
|---|---|---|
| `GET` | `/bars/{symbol}` | Bars for a symbol. Params: `resolution`, `start`, `end` |
| `GET` | `/bars/{symbol}/latest` | Most recent bar at a given resolution |
| `GET` | `/bars/{symbol}/resolutions` | List of resolutions available for a symbol within retention window |

### Operations

| Method | Path | Description |
|---|---|---|
| `POST` | `/ingest/backfill` | Manual backfill. Body: `symbol`, `resolution`, `start`, `end` |
| `GET` | `/ingest/status` | Last fetch job result per ticker |
| `GET` | `/ingest/log` | Paginated ingestion audit log |
| `GET` | `/stream/status` | Current WebSocket connection state and active subscriptions |
| `POST` | `/stream/subscribe` | Add tickers to live stream without restarting connection |
| `POST` | `/stream/unsubscribe` | Remove tickers from live stream |
| `GET` | `/health` | Service health. Checks DB, stream connection, and source connector. |
| `GET` | `/scheduler/jobs` | List scheduled fetch jobs and next run times |

---

## Configuration

All configuration via environment variables. No secrets in code. `.env.example` provided in repository.

| Variable | Required | Default | Description |
|---|---|---|---|
| `FINNHUB_API_KEY` | Yes | — | Finnhub API key (free at finnhub.io) |
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `STREAM_RESOLUTIONS` | No | `1m,5m` | Resolutions to assemble from live trades |
| `STREAM_FALLBACK_POLL_SECONDS` | No | `60` | Poll interval when stream is down |
| `MAX_WATCHLIST_SIZE` | No | `50` | Guard against accidental over-provisioning |
| `MAX_STREAM_TICKERS` | No | `25` | Max tickers in live stream |
| `TIMEZONE` | No | `US/Eastern` | Scheduler and market calendar timezone |

---

## Acceptance Criteria

The module is considered complete when all of the following pass.

### Stream Mode
- [ ] WebSocket connection opens automatically at market open for all `stream_live` tickers
- [ ] Incoming bars are validated and written within 2 seconds of bar close
- [ ] On simulated connection drop, module falls back to fetch polling within 10 seconds
- [ ] On stream reconnect, gap between drop and reconnect is backfilled automatically
- [ ] Stream session is logged with start time, end time, and rows written

### Fetch Mode
- [ ] Adding a ticker triggers automatic backfill of 5 years of daily bars and 90 days of intraday bars
- [ ] EOD pull runs within 5 minutes of 16:30 ET on trading days
- [ ] No fetch job runs on NYSE holidays
- [ ] Monday gap pull executes and logs correctly
- [ ] Gap audit detects and logs a manually introduced gap within 24 hours

### Data Integrity
- [ ] No row in the database fails OHLC integrity validation
- [ ] No duplicate rows exist for any `(symbol, ts, resolution)` combination
- [ ] Bars arriving via stream and bars arriving via fetch are indistinguishable to downstream modules except via the `source` column
- [ ] Retention cleanup removes bars older than the policy window without touching bars within it

### API
- [ ] All documented endpoints return correct HTTP status codes
- [ ] `/health` returns unhealthy when database is unreachable
- [ ] `/health` returns degraded (not unhealthy) when stream is down but fetch is operational
- [ ] `/bars/{symbol}` returns correct data filtered by resolution, start, and end
- [ ] `/stream/status` correctly reflects current connection state
- [ ] Backfill endpoint fills a known gap when triggered manually

### Deployment
- [ ] `docker compose up` starts all services with no manual steps beyond providing a `.env` file
- [ ] Stack starts cleanly on a machine with no prior state
- [ ] All services pass health checks within 60 seconds of compose up

---

## Explicit Exclusions

> **For the agent:** The following must not be implemented in this module even if they seem like natural extensions. They belong to later modules and implementing them here creates coupling that will be expensive to undo.

- Any computed column derived from raw OHLCV — no moving averages, returns, normalizations, or derivatives of any kind
- Any signal, indicator, or pattern detection logic
- A user-facing frontend — this module is API only
- Authentication, API keys, or rate limiting on the internal API
- Multi-user or multi-portfolio support
- Tick-level or quote-level data — bars only

---

## Living Document Policy

This document is the source of truth for this module. When implementation decisions deviate from this spec, this document is updated first — not after. The agent should flag any ambiguity or conflict before building, not after.