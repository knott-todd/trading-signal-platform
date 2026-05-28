"""
Concrete fetch job implementations.
Called by the scheduler and also available as manual triggers via API.
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

import pandas_market_calendars as mcal
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.connectors.finnhub_connector import FinnhubConnector
from app.connectors.yfinance_connector import YFinanceConnector
from app.db.init_db import RETENTION_DAYS
from app.db.session import AsyncSessionLocal
from app.services.ingestion import ingest_bars

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
    """Pull today's official daily bar for all active tickers via Finnhub."""
    connector = FinnhubConnector()
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
                    db, bars, symbol, "1d", "finnhub_fetch", "fetch", "eod"
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
    connector = FinnhubConnector()
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
                await ingest_bars(db, bars, symbol, "1d", "finnhub_fetch", "fetch", "eod")
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
    connector = FinnhubConnector()
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
            source = "finnhub_fetch"

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


def is_trading_day(check_date: Optional[date] = None) -> bool:
    """Return True if check_date (default: today) is a NYSE trading day."""
    d = check_date or date.today()
    schedule = NYSE.schedule(start_date=d.isoformat(), end_date=d.isoformat())
    return not schedule.empty


def get_scheduler() -> AsyncIOScheduler:
    """Build and return a configured AsyncIOScheduler with all production jobs."""
    scheduler = AsyncIOScheduler(timezone="America/New_York")

    # Wrap each market-dependent job so it skips NYSE holidays.
    # Retention cleanup is calendar-agnostic and runs unconditionally.
    async def _eod_pull():
        if is_trading_day():
            await run_eod_pull()

    async def _monday_gap_pull():
        if is_trading_day():
            await run_monday_gap_pull()

    async def _gap_audit():
        if is_trading_day():
            await run_gap_audit()

    # Spec: EOD daily bar pull — weekdays 16:30 ET
    scheduler.add_job(
        _eod_pull,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=30),
        id="eod_pull",
        name="EOD daily bar pull",
        replace_existing=True,
    )

    # Spec: Monday gap pull — Mondays 08:00 ET
    scheduler.add_job(
        _monday_gap_pull,
        CronTrigger(day_of_week="mon", hour=8, minute=0),
        id="monday_gap_pull",
        name="Monday Friday-gap fill",
        replace_existing=True,
    )

    # Spec: Gap audit — daily 17:00 ET
    scheduler.add_job(
        _gap_audit,
        CronTrigger(hour=17, minute=0),
        id="gap_audit",
        name="Daily gap audit",
        replace_existing=True,
    )

    # Spec: Retention cleanup — daily 02:00 ET
    scheduler.add_job(
        run_retention_cleanup,
        CronTrigger(hour=2, minute=0),
        id="retention_cleanup",
        name="Bar retention cleanup",
        replace_existing=True,
    )

    return scheduler
