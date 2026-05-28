"""
Perception Platform — Data Ingestion Module
Entry point. Manages app lifespan: DB init, scheduler start, stream lifecycle.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.backend.app.db.init_db import init_db
from services.backend.app.scheduler.jobs import get_scheduler, is_trading_day
from services.backend.app.api.routers.tickers import router as tickers_router
from services.backend.app.api.routers.bars import router as bars_router
from services.backend.app.api.routers.ingest import router as ingest_router
from services.backend.app.api.routers.stream import router as stream_router
from services.backend.app.api.routers.health import health_router, scheduler_router, set_scheduler
from services.backend.app.stream.manager import stream_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    log.info("Initialising database...")
    await init_db()

    log.info("Starting scheduler...")
    scheduler = get_scheduler()
    set_scheduler(scheduler)
    scheduler.start()

    # Start stream if market is open today
    # In production, the stream lifecycle is triggered by the scheduler / market calendar
    # For now, stream startup is manual via /stream/subscribe or at market open cron
    log.info("Stream manager ready. Connect via /stream/subscribe or scheduled market open.")

    yield

    # --- Shutdown ---
    log.info("Shutting down...")
    if stream_manager.state.value != "disconnected":
        await stream_manager.stop()
    scheduler.shutdown(wait=False)
    log.info("Shutdown complete.")


app = FastAPI(
    title="Perception Platform — Module 01: Data Ingestion",
    version="0.2.0",
    description=(
        "Foundational market data ingestion layer. "
        "Acquires, validates, stores, and serves raw OHLCV data. "
        "No transformation or signal logic lives here."
    ),
    lifespan=lifespan,
)

# Register routers
app.include_router(health_router)
app.include_router(scheduler_router)
app.include_router(tickers_router)
app.include_router(bars_router)
app.include_router(ingest_router)
app.include_router(stream_router)
