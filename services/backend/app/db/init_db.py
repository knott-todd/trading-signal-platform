"""
DB init: creates tables, sets up TimescaleDB hypertable + retention policies.
Run once on startup via app lifespan.
"""
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from app.db.session import engine, Base
from app.db import models  # noqa: F401 — ensures models are registered on Base

log = logging.getLogger(__name__)

# Retention windows in days, keyed by resolution
RETENTION_DAYS = {
    "1m":  60,
    "5m":  90,
    "15m": 180,
    "1h":  730,   # 2 years
    "1d":  1825,  # 5 years
}


async def init_db() -> None:
    async with engine.begin() as conn:
        await _ensure_timescale(conn)
        await _create_tables(conn)
        await _setup_hypertable(conn)
        await _setup_retention_policies(conn)
    log.info("Database initialised.")


async def _ensure_timescale(conn: AsyncConnection) -> None:
    try:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
        log.info("TimescaleDB extension ready.")
    except Exception as exc:
        log.warning("Could not create timescaledb extension (may already exist): %s", exc)


async def _create_tables(conn: AsyncConnection) -> None:
    await conn.run_sync(Base.metadata.create_all)
    log.info("Tables created (if not existing).")


async def _setup_hypertable(conn: AsyncConnection) -> None:
    """Convert bars to a TimescaleDB hypertable if not already."""
    try:
        await conn.execute(text(
            "SELECT create_hypertable('bars', 'ts', if_not_exists => TRUE, "
            "migrate_data => TRUE)"
        ))
        log.info("bars hypertable ready.")
    except Exception as exc:
        log.warning("Hypertable setup skipped (may already exist): %s", exc)


async def _setup_retention_policies(conn: AsyncConnection) -> None:
    """
    TimescaleDB retention policies drop chunks older than the window automatically.
    We can't set per-row filters natively, so we handle resolution-aware retention
    via a nightly APScheduler job that issues DELETE statements filtered by resolution.
    This function is a no-op placeholder — the scheduler handles retention.
    """
    log.info("Retention will be managed by nightly APScheduler job (resolution-aware).")
