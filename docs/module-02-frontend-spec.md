# Module 02 — Frontend & Gateway
**Perception Platform · Module Spec Series**

| Field | Value |
|---|---|
| Version | 0.1.0 |
| Status | Draft |
| Module | Frontend & Gateway |
| Depends On | Module 01 — Data Ingestion |
| Next Module | Transform Layer |

---

## Changelog

| Version | Notes |
|---|---|
| 0.1.0 | Initial draft. Stack selected, gateway pattern established, real-time architecture defined, Module 01 verification views specified, extension contract defined for future modules. |

---

## Overview

This document specifies the **Frontend and Gateway Module** — the visual layer of the Perception Platform and the single point of communication between the UI and all backend pipeline modules.

The frontend serves two purposes simultaneously and permanently:

1. **Pipeline verification.** Every module in the system must be visually verifiable — health, data flow, live output. You should never need to read raw database rows or API responses to confirm a module is working correctly. The UI makes that obvious at a glance.

2. **The operator's working environment.** This is not a dev tool that gets replaced later. It is the interface the operator uses. Verification views evolve into working views as each module matures. The foundation must support both from day one.

This spec covers the full frontend architecture and the Gateway service. It specifies the Module 01 verification views in detail. Future modules extend this foundation through a defined extension contract — they do not require architectural changes to the frontend or gateway.

> **Design Principle:** The frontend never talks directly to a pipeline module API. All communication flows through the Gateway. The frontend does not know how many modules exist, what APIs they expose, or how they are structured internally.

---

## Scope

### In Scope
- React frontend application
- API Gateway service (Backend for Frontend)
- Server-Sent Events (SSE) real-time connection from gateway to frontend
- Module registry — the mechanism by which new modules appear in the UI
- Pipeline status bar — persistent health view across all registered modules
- Module 01 verification views in full detail
- Extension contract for future module views
- Docker Compose integration with Module 01

### Not In Scope
- Trading execution controls (future module)
- Perception tuning workbench (future module)
- Strategy / algorithm builder (future module)
- Authentication or user accounts
- Mobile layout (desktop-first in Phase 1)
- Dark/light theme switching (dark only in Phase 1)

---

## Context

The system is built and operated by a small team. The frontend must be intuitive enough that the operator — whose expertise is trading, not software — can read and trust what it shows without explanation. Verification views must communicate pass/fail states visually, not through log output or raw data.

Modules will be added incrementally. The frontend must absorb new modules without structural rework. The extension contract defined in this spec is the mechanism for that.

Real-time data is a hard requirement. The operator watches live intraday bars. The UI must reflect arriving data within seconds of a bar closing.

---

## Architecture Decision Records

### ADR-006 · Frontend Framework and Build Tool

| Field | Detail |
|---|---|
| Status | Accepted |
| Decision | React 18 with Vite |

**Context:** React is already established in ADR-001. The build tool choice affects developer experience significantly.

**Rationale:** Vite provides near-instant hot module replacement and cold start times orders of magnitude faster than Create React App. For a UI that will be iterated frequently, fast feedback loops matter. React 18 concurrent features (Suspense, transitions) are useful for a data-heavy UI that receives frequent live updates.

**Rejected alternatives:** Create React App (slow, effectively unmaintained), Next.js (SSR adds complexity with no benefit for a local-first tool with a separate API layer).

**Consequences:** Node 18+ required. Build output is static files served by a simple static file server in the Docker Compose setup.

---

### ADR-007 · Component Library

| Field | Detail |
|---|---|
| Status | Accepted |
| Decision | shadcn/ui with Tailwind CSS |

**Context:** The UI requires highly customized components — financial charts, pipeline flow diagrams, real-time data feeds. A rigid component library would fight these requirements. The team has no pre-existing preference.

**Rationale:** shadcn/ui is not a dependency — components are copied into the codebase and owned outright. This means complete freedom to modify any component without fighting library internals. Tailwind CSS provides the styling foundation. Together they allow rapid composition of standard UI elements while remaining fully malleable for the custom interfaces this platform requires. No version lock-in, no upstream breaking changes.

**Rejected alternatives:** Ant Design (opinionated styling, hard to override), Material UI (heavy, Google aesthetic inappropriate for a trading tool), Chakra UI (runtime CSS-in-JS performance concerns for a real-time data UI).

**Consequences:** Components must be added to the codebase individually as needed rather than importing from a package. Tailwind must be configured in the project. Initial setup takes slightly longer but the long-term flexibility is worth it.

---

### ADR-008 · Financial Charts

| Field | Detail |
|---|---|
| Status | Accepted |
| Decision | TradingView Lightweight Charts for OHLCV and time-series visualization |

**Context:** The operator needs to visually verify that ingested bar data looks correct. Standard charting libraries are not optimised for financial data — they struggle with large bar series, OHLCV candlestick rendering, and real-time bar appending.

**Rationale:** TradingView Lightweight Charts is purpose-built for financial time-series. It handles hundreds of thousands of bars without performance degradation, supports candlestick and line series natively, and has a clean API for real-time bar updates. It is free and open source. For all non-financial charts (health metrics, coverage heatmaps, log visualizations) Recharts is used — it integrates naturally with React and handles the use cases well.

**Rejected alternatives:** Recharts for financial data (not optimised for OHLCV, performance degrades with large series), D3 directly (too low-level, significant build time for this use case), ApexCharts (heavier, less performant for real-time updates).

**Consequences:** Two charting libraries in the project. This is intentional and clearly scoped — TradingView Lightweight Charts for financial data only, Recharts for everything else.

---

### ADR-009 · State Management

| Field | Detail |
|---|---|
| Status | Accepted |
| Decision | Zustand for global state, React Query for server state |

**Context:** The UI needs to manage two distinct kinds of state: application state (which module is selected, what ticker is being viewed, UI preferences) and server state (data fetched from the gateway, real-time updates arriving via SSE).

**Rationale:** Zustand handles application state with minimal boilerplate — a plain store with no provider wrapping. React Query handles server state with built-in caching, background refresh, and loading/error states. The two libraries have complementary responsibilities and do not overlap. Together they cover the full state surface area cleanly.

**Rejected alternatives:** Redux (excessive boilerplate for this scale), Context API alone (performance issues with frequent real-time updates), SWR instead of React Query (React Query has better mutation handling and more complete feature set).

**Consequences:** React Query's cache must be invalidated appropriately when SSE events signal new data. The SSE event handler updates Zustand and triggers React Query invalidations as needed.

---

### ADR-010 · Real-Time Transport

| Field | Detail |
|---|---|
| Status | Accepted |
| Decision | Server-Sent Events (SSE) from Gateway to Frontend |

**Context:** The frontend needs to receive live bar updates, health state changes, and ingestion log entries as they happen. A real-time transport from gateway to frontend is required.

**Rationale:** SSE is unidirectional server-to-client push over standard HTTP. It reconnects automatically on connection drop. It requires no special protocol handling and works through standard proxies and load balancers. For this use case — the server pushing updates to the client — SSE is simpler and more appropriate than WebSocket. The frontend has nothing to push to the server in real time; all user actions are standard REST calls. WebSocket's bidirectional capability is unnecessary overhead here.

**Rejected alternatives:** WebSocket (bidirectional — unnecessary complexity for a one-way push use case), long polling (wasteful, higher latency), client-side polling (misses the immediacy requirement for live bar updates).

**Consequences:** The gateway maintains an SSE connection per connected client. Events are typed and versioned so the frontend can handle unknown event types gracefully — important as new modules add new event types.

---

### ADR-011 · API Gateway Pattern

| Field | Detail |
|---|---|
| Status | Accepted |
| Decision | Dedicated FastAPI gateway service as the sole frontend-facing API |

**Context:** The system will grow to multiple pipeline modules each exposing their own internal API. The frontend needs a stable, consistent interface that does not change shape as modules are added or restructured.

**Rationale:** The gateway is a Backend for Frontend (BFF) — a dedicated service that translates internal module APIs into frontend-friendly contracts. It aggregates data from multiple modules, normalises response shapes, hosts the SSE connection, and will be the single location for authentication when that is needed. The frontend is fully decoupled from module topology. Adding Module 03 means adding routes to the gateway — the frontend's API surface does not change.

**Rejected alternatives:** Frontend calling module APIs directly (tight coupling, frontend breaks when module APIs change, multiplying API surfaces to manage), GraphQL gateway (significant complexity overhead for this scale, no meaningful benefit over REST at this team size).

**Consequences:** The gateway is a thin translation and aggregation layer — it must not contain business logic. Business logic lives in the modules. The gateway shapes data for the frontend and nothing else. This boundary must be enforced.

---

## Service Architecture

```
Browser (React + Vite)
        |
        | REST + SSE
        v
    Gateway Service (FastAPI)
        |           |           |
        v           v           v
  Module 01     Module 02    Module N
  Internal      Internal     Internal
    API           API          API
```

All services run in Docker Compose on a shared internal network. The gateway is the only service with a port exposed to the host. Module internal APIs are not reachable from outside the Docker network.

---

## Module Registry

The module registry is the mechanism that makes the frontend extensible. It is a configuration object — not a database — that lists every module the frontend knows about and what views it exposes.

### Registry Entry Contract

Each module registers itself with the following shape:

```typescript
interface ModuleRegistration {
  id: string                    // e.g. "ingestion"
  label: string                 // e.g. "Data Ingestion"
  version: string               // e.g. "0.1.0"
  healthEndpoint: string        // gateway route for health status
  views: ModuleView[]           // ordered list of views this module provides
}

interface ModuleView {
  id: string                    // e.g. "watchlist"
  label: string                 // e.g. "Watchlist"
  icon: string                  // lucide icon name
  component: React.ComponentType // the view component
  verificationView: boolean     // true = this view proves the module works
}
```

Registering a new module is a single file change. The pipeline status bar, navigation, and layout automatically reflect the new module. No other frontend code changes.

---

## Layout

### Persistent Shell

The shell is always present regardless of which view is active. It contains:

**Pipeline Status Bar — top of screen.** One node per registered module. Each node shows the module name and a health indicator: green (healthy), amber (degraded), red (failed), grey (not yet built). Nodes are connected by a line with a subtle animation when data is actively flowing between them. Clicking a node navigates to that module's primary verification view.

**Left Navigation.** Module sections listed vertically. Each section expands to show that module's views. Active view is highlighted. Module health indicator repeated here for visibility when the status bar is scrolled past.

**Main Content Area.** The active view renders here. Full width and height of remaining space.

**Live Event Ticker — bottom of screen.** A scrolling single-line feed of the most recent SSE events across all modules. Timestamp, module source, event type, and a one-line summary. Gives immediate confirmation that the pipeline is alive and producing data without requiring the operator to navigate to a specific view. Can be paused or dismissed.

---

## Module 01 Verification Views

Four views cover the full surface area of Module 01. Together they answer: is ingestion working, is the data correct, and is the stream live?

---

### View 1 — Pipeline Health

**Purpose:** One-glance confirmation that all Module 01 subsystems are operational.

**What it shows:**

A grid of status cards, one per subsystem:

| Card | What it shows |
|---|---|
| Database | Connected / unreachable. Row counts for `bars` and `ingestion_log`. |
| Alpaca Connection | Authenticated / unauthenticated. Last successful API call timestamp. |
| WebSocket Stream | Live / degraded / offline. Active ticker subscriptions count. Connected since timestamp. |
| Scheduler | Running / stopped. Each scheduled job with last run time, next run time, and last run status. |
| Retention Policy | Last cleanup run. Rows dropped per resolution. |

**What makes it a verification view:** If all cards are green, Module 01 is healthy. No log reading required. Failures are specific — the card that is red tells you exactly which subsystem failed.

---

### View 2 — Watchlist & Coverage

**Purpose:** Verify the right tickers are being tracked and that historical data is present and complete.

**What it shows:**

**Top half — Watchlist table.** One row per ticker. Columns: symbol, name, active toggle, stream_live toggle, date added, last bar received, coverage percentage. Inline controls to add or remove tickers.

**Bottom half — Coverage heatmap.** Tickers on the Y axis, dates on the X axis, coloured cells showing data presence by resolution. Green = full coverage. Amber = partial (some resolutions missing). Red = no data. Grey = market holiday or weekend. Hovering a cell shows exact row counts per resolution for that ticker and date.

**What makes it a verification view:** The coverage heatmap makes data gaps immediately visible as red or amber cells in an otherwise green grid. You can see at a glance if a backfill worked, if a weekend gap was captured, or if a ticker has missing history.

---

### View 3 — Bar Viewer

**Purpose:** Visually verify that ingested bar data looks correct for a given ticker and resolution.

**What it shows:**

**Controls row:** Ticker selector, resolution selector (1m / 5m / 15m / 1h / 1d), date range picker.

**Main chart:** TradingView Lightweight Charts candlestick chart rendering the selected bars. Volume bars below. No indicators — raw OHLCV only. This is a data verification view, not an analysis view.

**Data table below chart:** The raw bars underlying the current chart view. Columns: timestamp, open, high, low, close, volume, source, flagged. Flagged bars are highlighted amber. Allows spot-checking that the chart is rendering correctly against the underlying data.

**What makes it a verification view:** If the chart looks like a real price chart — sensible candles, no wild spikes, continuous bars with no unexpected gaps — the data is good. Flagged bars appear amber in both the chart and the table simultaneously. The operator can visually confirm in seconds that a ticker's data is usable.

---

### View 4 — Live Feed

**Purpose:** Verify that the WebSocket stream is delivering live bars in real time during market hours.

**What it shows:**

**Stream status header:** Connection state (live / degraded / offline), active ticker count, bars received this session, last bar received timestamp. A pulsing indicator when actively receiving.

**Live bar log:** A scrolling feed of bars as they arrive via SSE. Each row: timestamp, symbol, resolution, open, high, low, close, volume, source. New rows animate in from the top. Feed can be filtered by symbol or resolution. Can be paused without disconnecting.

**Mini sparklines:** For each ticker currently in the stream, a small real-time line chart of the last 20 closes at the selected resolution. Updates as each new bar arrives. Gives immediate visual confirmation that different tickers are streaming independently and correctly.

**What makes it a verification view:** If bars are arriving, the sparklines are moving, and the timestamp on the last bar is recent — the stream is working. You do not need to query the database or inspect API responses. The absence of new bars for a live ticker during market hours is immediately obvious.

---

## Gateway API Contract

The gateway exposes the following to the frontend. Internal module APIs are not exposed. All responses are JSON. All timestamps are ISO 8601.

### System

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Aggregated health across all registered modules |
| `GET` | `/api/modules` | List of registered modules with versions and health |
| `GET` | `/api/events` | SSE stream. All real-time events from all modules. |

### Module 01 — Ingestion

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/ingestion/health` | Subsystem health cards for View 1 |
| `GET` | `/api/ingestion/tickers` | Watchlist with coverage summary |
| `POST` | `/api/ingestion/tickers` | Add ticker to watchlist |
| `PATCH` | `/api/ingestion/tickers/{symbol}` | Update active / stream_live flags |
| `DELETE` | `/api/ingestion/tickers/{symbol}` | Remove ticker |
| `GET` | `/api/ingestion/coverage` | Coverage heatmap data. Params: `start`, `end` |
| `GET` | `/api/ingestion/bars/{symbol}` | Bars for chart view. Params: `resolution`, `start`, `end` |
| `POST` | `/api/ingestion/backfill` | Trigger manual backfill |
| `GET` | `/api/ingestion/stream/status` | Stream connection state and active subscriptions |

### SSE Event Types

All events have a consistent envelope:

```typescript
interface SSEEvent {
  type: string        // event type identifier
  module: string      // which module emitted it
  ts: string          // ISO 8601 timestamp
  payload: object     // event-specific data
}
```

Module 01 emits the following event types:

| Event Type | Payload | Triggers |
|---|---|---|
| `bar.live` | symbol, resolution, ohlcv, source | New bar arrives via stream |
| `ingestion.health_change` | subsystem, previous_state, new_state | Any subsystem health state changes |
| `stream.connected` | ticker_count | WebSocket stream connects |
| `stream.disconnected` | reason | WebSocket stream drops |
| `stream.reconnected` | downtime_seconds | WebSocket stream recovers |
| `backfill.complete` | symbol, resolution, rows_written | Backfill job completes |
| `gap.detected` | symbol, resolution, gap_start, gap_end | Gap audit finds missing bars |

> **Extensibility rule:** The frontend must handle unknown event types gracefully — log them to the event ticker and ignore them. This means future modules can emit new event types without requiring a frontend update to avoid errors.

---

## Real-Time Update Behaviour

**Bar arrival (`bar.live`):**
- Live feed view appends the bar to the top of the feed
- Relevant sparkline updates immediately
- React Query cache for the bar viewer is invalidated if the arriving bar matches the currently viewed ticker and resolution

**Health change (`ingestion.health_change`):**
- Pipeline status bar node updates immediately
- Health view card updates immediately
- If state is red, the event ticker highlights the entry in red

**Stream events:**
- Stream status header in View 4 updates immediately
- Pipeline status bar stream node reflects new state

**All events:**
- Appended to the live event ticker at the bottom of the screen

---

## Extension Contract for Future Modules

When a new pipeline module is built, adding it to the frontend requires:

1. **Gateway routes** — new routes under `/api/{module_name}/` following the shape conventions above
2. **SSE event types** — new event types documented and emitted following the SSE envelope contract
3. **Module registration** — one entry added to the module registry file
4. **View components** — React components for each view, placed in `/src/modules/{module_name}/`
5. **Health endpoint** — the gateway route that returns subsystem health cards for this module

Nothing outside these five files changes. The pipeline status bar, navigation, layout, event ticker, and SSE handling all work automatically.

> **Contract invariant:** Every module must provide at least one view with `verificationView: true`. A module with no verification view is considered incomplete regardless of backend functionality.

---

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `GATEWAY_PORT` | No | `8080` | Port exposed to host |
| `INGESTION_API_URL` | Yes | — | Internal URL of Module 01 API |
| `VITE_GATEWAY_URL` | Yes | — | Gateway URL for frontend at build time |
| `SSE_KEEPALIVE_SECONDS` | No | `30` | SSE keepalive ping interval |

---

## Acceptance Criteria

### Gateway
- [ ] All documented gateway endpoints return correct HTTP status codes
- [ ] `/api/health` returns aggregated status across all registered modules
- [ ] Gateway returns 503 with degraded status when a module API is unreachable, not an unhandled error
- [ ] SSE connection established from frontend within 2 seconds of page load
- [ ] SSE reconnects automatically within 5 seconds of connection drop
- [ ] Unknown SSE event types do not cause frontend errors

### Pipeline Status Bar
- [ ] Each registered module appears as a node with correct health state
- [ ] Health state updates within 3 seconds of a subsystem state change
- [ ] Clicking a module node navigates to its primary verification view

### Module 01 — View 1 (Health)
- [ ] All subsystem cards reflect current state without page refresh
- [ ] Red state on any card indicates the specific failing subsystem
- [ ] Scheduler jobs show correct last run and next run times

### Module 01 — View 2 (Coverage)
- [ ] Coverage heatmap renders for all watchlist tickers and the last 30 days
- [ ] A manually introduced gap appears as a red cell within 60 seconds
- [ ] Adding a ticker via the watchlist table triggers backfill and coverage updates

### Module 01 — View 3 (Bar Viewer)
- [ ] Candlestick chart renders correctly for any active ticker and resolution
- [ ] Flagged bars appear amber in both chart and data table
- [ ] Resolution and date range selectors update chart without page reload

### Module 01 — View 4 (Live Feed)
- [ ] Live bars appear in the feed within 3 seconds of bar close during market hours
- [ ] Sparklines update in real time as bars arrive
- [ ] Feed can be paused and resumed without losing the SSE connection
- [ ] Stream disconnection is immediately visible in the status header

### Extensibility
- [ ] Adding a new module registration entry causes it to appear in the status bar and navigation with no other code changes
- [ ] A new SSE event type from a new module appears in the event ticker without frontend errors

### Deployment
- [ ] `docker compose up` starts frontend, gateway, and all module services together
- [ ] Frontend is accessible at `http://localhost:8080` with no additional steps

---

## Explicit Exclusions

> **For the agent:** The following must not be implemented in this module.

- Trading controls, order placement, or any execution interface
- Chart indicators, overlays, or derived series — the bar viewer shows raw OHLCV only
- Authentication or login flow
- Any business logic in the gateway — it translates and aggregates, nothing more
- Direct calls from the frontend to module APIs, bypassing the gateway
- Mobile or responsive layout optimisation

---

## Living Document Policy

This document is the source of truth for the frontend and gateway. It will be updated as new modules are specced and their views defined. Each new module adds a section to the Gateway API Contract and a verification view description. The extension contract and shell layout do not change — only new module-specific sections are added.

When implementation decisions deviate from this spec, this document is updated first — not after.
