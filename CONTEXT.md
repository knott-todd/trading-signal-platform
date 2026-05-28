# Perception Platform — Agent Context Briefing

> Read this before reading any module spec. It explains why decisions were made the way they were. Do not deviate from decisions recorded here without flagging the conflict explicitly.

---

## What This System Is

A proprietary trading platform built for a single operator. The operator is an experienced day trader with a bespoke mental model of how markets move. He reads momentum, velocity, and cyclic patterns — primarily on intraday timeframes but also on multi-day cycles up to approximately 5 trading days.

The system is not a generic trading platform. It is a tool that externalises his specific mental model, makes it measurable, and executes it consistently. Every architectural decision should be evaluated against that goal.

---

## The Three Layers and What They Do

The platform is built in three distinct layers with hard boundaries between them. Business logic does not cross layer boundaries.

**Layer 1 — Pipeline.** Acquires, stores, and transforms raw market data. Modules: Data Ingestion, Transform Layer. These modules have no opinion about trading. They produce data.

**Layer 2 — Perception.** The operator defines what the market looks like to him. He builds a personal vocabulary of named concepts — "dead momentum," "overextended," "clean break" — by calibrating transforms against his own annotated examples. These concepts become the language the strategy layer reads from.

**Layer 3 — Strategy and Execution.** The operator builds rules using his perception vocabulary. Rules produce signals. Signals drive action. This layer does not exist yet.

---

## Key Decisions and Why They Were Made

### The operator tunes perception, not just strategy

Most trading platforms let users configure strategy rules on top of fixed, pre-defined indicators. This system is different. The operator has his own definitions of momentum, velocity, and cycle strength that do not match standard indicator definitions. The transform layer must be parameterized — outputs are computed on demand with caller-supplied parameters, not pre-computed with fixed settings. The perception workbench is where he calibrates those parameters until the system sees what he sees.

### No preferred timeframe

Early drafts of this spec assumed daily cycles as primary. This was wrong. The operator actively trades intraday cycles and multi-day cycles. The system has no architectural preference for any resolution. Daily bars and 1-minute bars are equally first-class. Resolution is always a caller-supplied parameter, never a hardcoded assumption.

### Normalized derivatives, not raw price

The operator does not read raw price charts. He reads the behavior of price — how fast it is moving, whether that speed is increasing or fading, how unusual the current move is relative to recent history. All primary views show normalized derivative series, not raw OHLCV. Raw price exists in the database and is available but is not the primary visual surface.

### Stream mode is a hard requirement, not an enhancement

Polling a REST API on a schedule introduces latency that makes intraday pattern detection non-actionable. The system uses a persistent WebSocket stream for live intraday bars. Bars arrive within seconds of closing. This is not optional. Any module or feature that depends on intraday data must assume stream delivery, not polling.

### Store what cannot be reconstructed, fetch what can

Raw OHLCV bar data is universally available from external APIs. The system does not try to be a market data vendor. Raw bars are fetched on demand and cached with resolution-aware retention windows — not stored permanently. What is stored permanently: the operator's annotations and pinned examples, his concept definitions and version history, his strategy rules, and the signal and trade log. These have no external source. If they are lost they cannot be recovered.

### The gateway owns the frontend contract

The frontend never calls pipeline module APIs directly. A dedicated gateway service (Backend for Frontend) is the sole API surface for the frontend. It translates internal module APIs into frontend-friendly contracts, hosts the SSE real-time connection, and aggregates health across modules. This means module APIs can change internally without breaking the frontend, and new modules can be added without frontend architectural changes.

### Verification is visual, not log-based

Every pipeline module must be verifiable through the UI without reading log output or querying the database directly. Each module provides at least one verification view — a purpose-built visual that makes the module's health and data correctness obvious at a glance. A module without a passing verification view is considered incomplete regardless of backend functionality.

### Specs are contracts, not descriptions

ADRs record decisions and their rationale. Data model definitions are exact schemas — column names, types, and constraints are not suggestions. API contracts define exact endpoint paths, parameters, and response shapes. Acceptance criteria are binary pass/fail checks. When in doubt, treat the spec as a contract and flag ambiguity rather than resolving it independently.

---

## What Has Been Decided vs What Is Open

### Decided — do not revisit without flagging
- Stack: Python 3.11+ / FastAPI / React 18 / Vite / Docker Compose
- Database: PostgreSQL 15 with TimescaleDB
- Primary data source: Finnhub (free tier, real-time WebSocket, Canada-accessible, instant registration at finnhub.io)
- Fallback data source: yfinance (historical REST fetch only, no WebSocket)
- Upgrade path if Finnhub proves insufficient: Polygon.io Starter (~$29/month, pre-built OHLCV bars via WebSocket)
- Scheduling: APScheduler embedded in FastAPI process (fetch jobs only)
- Frontend component library: shadcn/ui + Tailwind CSS
- Financial charting: TradingView Lightweight Charts
- General charting: Recharts
- State management: Zustand (app state) + React Query (server state)
- Real-time transport: Server-Sent Events (SSE) from gateway to frontend
- Algorithm builder: no-code (visual, not scripted) — open to later scripting layer

### Open — do not assume, flag for clarification
- Whether transforms are pre-computed per ticker or strictly on-demand
- Whether transform parameters are global or per-concept
- Whether volume is a first-class input to the transform layer
- Specific transform primitives the operator needs (pending session with operator)
- Deployment target (local confirmed for Phase 1, cloud provider not yet selected)

---

## Module Completion Status

| Module | Spec Version | Status |
|---|---|---|
| 01 — Data Ingestion | 0.2.0 | Spec complete. Not built. |
| 02 — Frontend & Gateway | 0.1.0 | Spec complete. Not built. |
| 03 — Transform Layer | — | Spec in progress. Blocked on open questions above. |
| 04 — Perception Workbench | — | Not started. Depends on Module 03. |
| 05 — Strategy Builder | — | Not started. No-code confirmed. |
| 06 — Execution | — | Not started. |

---

## Non-Negotiable Constraints

These apply to every module. No exceptions.

- No business logic in the gateway. It translates and aggregates only.
- No computed columns in the ingestion module. Raw OHLCV only.
- No direct frontend-to-module API calls. All frontend traffic through the gateway.
- Every module exposes a health endpoint the gateway can query.
- Every module provides at least one verification view registered with the frontend module registry.
- All timestamps are timezone-aware ISO 8601. No naive datetimes anywhere.
- Finnhub WebSocket delivers raw trades, not pre-built bars. Bar assembly from trades happens in the ingestion module stream mode. It is not a transform and must not be delegated to the transform layer.
- All secrets via environment variables. No secrets in code or committed files.
- Docker Compose is the only supported way to run the full stack. No manual service startup steps.

---

## Repo Structure Convention

```
/
├── docker-compose.yml
├── .env.example
├── CONTEXT.md               ← this file
├── docs/
│   ├── module-01-ingestion-spec.md
│   ├── module-02-frontend-spec.md
│   └── module-0N-*.md
├── services/
│   ├── ingestion/           ← Module 01
│   ├── gateway/             ← Module 02 gateway
│   ├── frontend/            ← Module 02 frontend
│   └── transform/           ← Module 03 (when built)
└── shared/
    └── types/               ← Shared type definitions
```

Each service is self-contained with its own dependencies, Dockerfile, and README. Shared types live in `/shared/types` and are referenced by services that need them.

---

## Living Document Policy

This file is updated whenever a new module is specced, a decision is made on an open question, or the completion status of a module changes. It is always accurate. If this file and a module spec conflict, the module spec takes precedence for module-specific details. This file governs cross-cutting decisions that affect all modules.