"""
Concrete fetch job implementations.
Called by the scheduler and also available as manual triggers via API.
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

import pandas_market_calendars as mcal

from services.backend.app.config import settings
from services.backend.app.connectors.alpaca import AlpacaConnector
from services.backend.app.connectors.yfinance_connector import YFinanceConnector
from services.backend.app.db.init_db import RETENTION_DAYS
from services.backend.app.db.session import AsyncSessionLocal
from services.backend.app.services.ingestion import ingest_bars

log = logging.getLogger(__name__)

NYSE = mcal.get_calendar("NYSE")

# Backfill depths on ticker add (spec: 5 years daily, 90 days intraday)
INITIAL_DAILY_YEARS = 5
INITIAL_INTRADAY_DAYS = 90


async def _get_active_symbols(stream_only: bool = False) -> List[str]:
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        if stream_only:
            result = await db.execute(
                text("SELECT symbol FROM tickers WHERE active = true AND stream_live = true")
            )
        else:
            result = await db.execute(
                text("SELECT symbol FROM tickers WHERE active = true")
            )
        return [row[0] for row in result.fetchall()]


async def run_eod_pull() -> None:
    """Pull today's official daily bar for all active tickers via Alpaca."""
    connector = AlpacaConnector()
    symbols = await _get_active_symbols()
    today = date.today()

    for symbol in symbols:
        try:
            df = connector.get_daily_bars(symbol, today, today)
            if df.empty:
                log.warning("EOD pull: no data for %s on %s", symbol, today)
                continue
            bars = df.to_dict("records")
            async with AsyncSessionLocal() as db:
                written = await ingest_bars(
                    db, bars, symbol, "1d", "alpaca_fetch", "fetch", "eod"
                )
            log.info("EOD pull: %s — %d bars written.", symbol, written)
        except Exception as exc:
            log.error("EOD pull error %s: %s", symbol, exc)
            # Attempt yfinance fallback
            try:
                yf = YFinanceConnector()
                df = yf.get_daily_bars(symbol, today, today)
                if not df.empty:
                    bars = df.to_dict("records")
                    async with AsyncSessionLocal() as db:
                        await ingest_bars(db, bars, symbol, "1d", "yfinance", "fetch", "eod")
            except Exception as yf_exc:
                log.error("EOD yfinance fallback also failed %s: %s", symbol, yf_exc)


async def run_monday_gap_pull() -> None:
    """Pull Friday's close bars before stream opens on Mondays."""
    connector = AlpacaConnector()
    symbols = await _get_active_symbols(stream_only=True)
    today = date.today()
    friday = today - timedelta(days=3)  # Monday - 3 = Friday

    for symbol in symbols:
        try:
            df = connector.get_daily_bars(symbol, friday, friday)
            if df.empty:
                continue
            bars = df.to_dict("records")
            async with AsyncSessionLocal() as db:
                await ingest_bars(db, bars, symbol, "1d", "alpaca_fetch", "fetch", "eod")
            log.info("Monday gap pull: %s Friday bar written.", symbol)
        except Exception as exc:
            log.error("Monday gap pull error %s: %s", symbol, exc)


async def run_gap_audit() -> None:
    """
    Compare stored daily bars against NYSE trading calendar.
    Log any gaps. Queue backfill for missing dates.
    """
    from sqlalchemy import text
    symbols = await _get_active_symbols()
    today = date.today()
    audit_start = today - timedelta(days=30)  # Audit last 30 calendar days

    schedule = NYSE.schedule(
        start_date=audit_start.isoformat(),
        end_date=today.isoformat(),
    )
    expected_dates = {d.date() for d in schedule.index}

    for symbol in symbols:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    text("""
                        SELECT DISTINCT DATE(ts) as bar_date
                        FROM bars
                        WHERE symbol = :sym AND resolution = '1d'
                          AND ts >= :start
                    """),
                    {"sym": symbol, "start": audit_start.isoformat()},
                )
                stored_dates = {row[0] for row in result.fetchall()}

            missing = expected_dates - stored_dates
            if missing:
                log.warning(
                    "GAP AUDIT: %s missing %d daily bars: %s",
                    symbol, len(missing), sorted(missing)
                )
                # Queue backfill for the missing range
                min_date = min(missing)
                max_date = max(missing)
                await run_backfill(symbol, "1d", min_date, max_date)
        except Exception as exc:
            log.error("Gap audit error %s: %s", symbol, exc)


async def run_retention_cleanup() -> None:
    """Drop bars older than retention window per resolution."""
    from sqlalchemy import text
    now = datetime.now(tz=timezone.utc)

    async with AsyncSessionLocal() as db:
        for resolution, days in RETENTION_DAYS.items():
            cutoff = now - timedelta(days=days)
            result = await db.execute(
                text("""
                    DELETE FROM bars
                    WHERE resolution = :resolution AND ts < :cutoff
                """),
                {"resolution": resolution, "cutoff": cutoff},
            )
            deleted = result.rowcount
            if deleted:
                log.info("Retention cleanup: %s — deleted %d bars older than %d days.", resolution, deleted, days)
        await db.commit()


async def run_backfill(
    symbol: str,
    resolution: str,
    start: date,
    end: date,
) -> int:
    """
    Manual or automatic backfill for a given symbol/resolution/range.
    Returns total rows written.
    """
    connector = AlpacaConnector()
    total_written = 0

    try:
        if resolution == "1d":
            df = connector.get_daily_bars(symbol, start, end)
        else:
            start_dt = datetime.combine(start, datetime.min.time()).replace(tzinfo=timezone.utc)
            end_dt = datetime.combine(end, datetime.max.time()).replace(tzinfo=timezone.utc)
            df = connector.get_intraday_bars(symbol, resolution, start_dt, end_dt)

        if df.empty:
            log.info("Backfill: no data for %s %s %s–%s", symbol, resolution, start, end)
            # Attempt yfinance fallback
            yf = YFinanceConnector()
            if resolution == "1d":
                df = yf.get_daily_bars(symbol, start, end)
            else:
                start_dt = datetime.combine(start, datetime.min.time()).replace(tzinfo=timezone.utc)
                end_dt = datetime.combine(end, datetime.max.time()).replace(tzinfo=timezone.utc)
                df = yf.get_intraday_bars(symbol, resolution, start_dt, end_dt)
            source = "yfinance"
        else:
            source = "alpaca_fetch"

        if not df.empty:
            bars = df.to_dict("records")
            async with AsyncSessionLocal() as db:
                total_written = await ingest_bars(
                    db, bars, symbol, resolution, source, "fetch", "backfill"
                )

    except Exception as exc:
        log.error("Backfill error %s %s: %s", symbol, resolution, exc)

    log.info("Backfill %s %s: %d rows written.", symbol, resolution, total_written)
    return total_written


async def run_initial_backfill(symbol: str) -> None:
    """
    On ticker add: backfill 5 years of daily + 90 days of intraday.
    Runs asynchronously — does not block the ticker add response.
    """
    import asyncio
    log.info("Starting initial backfill for %s.", symbol)
    today = date.today()

    # Daily — 5 years
    daily_start = today.replace(year=today.year - INITIAL_DAILY_YEARS)
    await run_backfill(symbol, "1d", daily_start, today)

    # Intraday resolutions — 90 days
    intraday_start = today - timedelta(days=INITIAL_INTRADAY_DAYS)
    for resolution in ["1h", "15m", "5m", "1m"]:
        await run_backfill(symbol, resolution, intraday_start, today)
        await asyncio.sleep(1)  # rate limit courtesy

    log.info("Initial backfill complete for %s.", symbol)
