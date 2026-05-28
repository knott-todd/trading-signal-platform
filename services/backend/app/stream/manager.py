"""
WebSocket stream manager.
Manages the full lifecycle: connect at open, disconnect at close,
fallback to fetch on drop, reconnect with backoff, backfill on reconnect.
"""
import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Set

from services.backend.app.config import settings
from services.backend.app.connectors.alpaca import AlpacaConnector
from services.backend.app.db.session import AsyncSessionLocal
from services.backend.app.services.ingestion import ingest_single_bar, ingest_bars, get_latest_close

log = logging.getLogger(__name__)


class StreamState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FALLBACK = "fallback"  # fetch polling active due to stream drop


class StreamManager:
    def __init__(self) -> None:
        self._connector = AlpacaConnector()
        self._state: StreamState = StreamState.DISCONNECTED
        self._subscribed_symbols: Set[str] = set()
        self._session_started_at: Optional[datetime] = None
        self._session_log_id: Optional[int] = None
        self._fallback_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._drop_time: Optional[datetime] = None
        self._bars_written_session: int = 0
        self._resolutions: List[str] = settings.stream_resolutions_list

    @property
    def state(self) -> StreamState:
        return self._state

    @property
    def subscribed_symbols(self) -> List[str]:
        return sorted(self._subscribed_symbols)

    @property
    def session_started_at(self) -> Optional[datetime]:
        return self._session_started_at

    async def start(self, symbols: List[str]) -> None:
        """Open the stream for the given symbols. Called at market open."""
        if len(symbols) > settings.max_stream_tickers:
            symbols = symbols[:settings.max_stream_tickers]
            log.warning("Stream ticker cap hit — streaming first %d tickers.", settings.max_stream_tickers)

        self._subscribed_symbols = set(symbols)
        self._session_started_at = datetime.now(tz=timezone.utc)
        self._bars_written_session = 0

        try:
            self._connector.stream_bars(symbols, self._resolutions, self._on_bar)
            self._state = StreamState.CONNECTED
            log.info("Stream CONNECTED: %d symbols, resolutions=%s", len(symbols), self._resolutions)
            await self._open_stream_log()
        except Exception as exc:
            log.error("Failed to open stream: %s", exc)
            self._state = StreamState.FALLBACK
            await self._start_fallback()

    async def stop(self) -> None:
        """Graceful disconnect. Called at market close."""
        log.info("Stream stopping (market close).")
        self._connector.stop_stream()
        self._state = StreamState.DISCONNECTED
        await self._close_stream_log()
        if self._fallback_task:
            self._fallback_task.cancel()
        if self._reconnect_task:
            self._reconnect_task.cancel()

    def _on_bar(self, symbol: str, resolution: str, bar: dict) -> None:
        """
        Callback from connector. Runs in the stream thread.
        Schedules async write via event loop.
        """
        asyncio.run_coroutine_threadsafe(
            self._write_bar(symbol, resolution, bar),
            asyncio.get_event_loop(),
        )

    async def _write_bar(self, symbol: str, resolution: str, bar: dict) -> None:
        async with AsyncSessionLocal() as db:
            prev_close = await get_latest_close(db, symbol, resolution)
            written = await ingest_single_bar(db, symbol, resolution, bar, "alpaca_stream", prev_close)
            await db.commit()
            if written:
                self._bars_written_session += 1

    async def on_connection_drop(self) -> None:
        """Called when stream drops unexpectedly during market hours."""
        log.warning("Stream CONNECTION DROP detected.")
        self._drop_time = datetime.now(tz=timezone.utc)
        self._state = StreamState.RECONNECTING
        await self._start_fallback()
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def subscribe(self, symbols: List[str]) -> None:
        """Add tickers to live stream without restarting the connection."""
        new_symbols = [s for s in symbols if s not in self._subscribed_symbols]
        if not new_symbols:
            return
        if len(self._subscribed_symbols) + len(new_symbols) > settings.max_stream_tickers:
            raise ValueError(f"Would exceed MAX_STREAM_TICKERS={settings.max_stream_tickers}")
        self._subscribed_symbols.update(new_symbols)
        # alpaca-py: re-subscribe on the existing stream
        if self._state == StreamState.CONNECTED:
            self._connector._stream.subscribe_bars(
                lambda bar: self._on_bar(bar.symbol, _infer_res(bar), _to_dict(bar)),
                *new_symbols
            )
            log.info("Subscribed %s to live stream.", new_symbols)

    async def unsubscribe(self, symbols: List[str]) -> None:
        """Remove tickers from live stream."""
        self._subscribed_symbols -= set(symbols)
        if self._state == StreamState.CONNECTED and self._connector._stream:
            try:
                self._connector._stream.unsubscribe_bars(*symbols)
            except Exception as exc:
                log.warning("Unsubscribe error: %s", exc)

    # ------------------------------------------------------------------
    # Fallback + reconnect
    # ------------------------------------------------------------------

    async def _start_fallback(self) -> None:
        self._state = StreamState.FALLBACK
        log.info("Switching to FALLBACK fetch mode at %ds interval.", settings.stream_fallback_poll_seconds)
        self._fallback_task = asyncio.create_task(self._fallback_poll_loop())

    async def _fallback_poll_loop(self) -> None:
        from services.backend.app.connectors.alpaca import AlpacaConnector
        from datetime import timedelta
        connector = AlpacaConnector()
        while self._state in (StreamState.FALLBACK, StreamState.RECONNECTING):
            for symbol in list(self._subscribed_symbols):
                for resolution in self._resolutions:
                    try:
                        now = datetime.now(tz=timezone.utc)
                        start = now - timedelta(minutes=30)
                        df = connector.get_intraday_bars(symbol, resolution, start, now)
                        if df.empty:
                            continue
                        bars = df.to_dict("records")
                        async with AsyncSessionLocal() as db:
                            await ingest_bars(
                                db, bars, symbol, resolution,
                                "alpaca_fetch", "fetch", "intraday_poll"
                            )
                    except Exception as exc:
                        log.warning("Fallback poll error %s %s: %s", symbol, resolution, exc)
            await asyncio.sleep(settings.stream_fallback_poll_seconds)

    async def _reconnect_loop(self) -> None:
        import time
        delay = 30
        max_delay = 300
        while self._state in (StreamState.RECONNECTING, StreamState.FALLBACK):
            await asyncio.sleep(delay)
            log.info("Attempting stream reconnect...")
            try:
                symbols = list(self._subscribed_symbols)
                self._connector.stop_stream()
                self._connector.stream_bars(symbols, self._resolutions, self._on_bar)
                self._state = StreamState.CONNECTED
                log.info("Stream RECONNECTED.")
                await self._backfill_gap()
                if self._fallback_task:
                    self._fallback_task.cancel()
                return
            except Exception as exc:
                log.warning("Reconnect failed: %s — retrying in %ds.", exc, delay)
                delay = min(delay * 2, max_delay)

    async def _backfill_gap(self) -> None:
        """Fill the gap from drop to now using fetch data already collected."""
        if not self._drop_time:
            return
        from services.backend.app.connectors.alpaca import AlpacaConnector
        connector = AlpacaConnector()
        now = datetime.now(tz=timezone.utc)
        log.info("Backfilling gap: %s → %s", self._drop_time.isoformat(), now.isoformat())
        for symbol in list(self._subscribed_symbols):
            for resolution in self._resolutions:
                try:
                    df = connector.get_intraday_bars(symbol, resolution, self._drop_time, now)
                    if df.empty:
                        continue
                    bars = df.to_dict("records")
                    async with AsyncSessionLocal() as db:
                        await ingest_bars(
                            db, bars, symbol, resolution,
                            "alpaca_fetch", "fetch", "backfill"
                        )
                except Exception as exc:
                    log.warning("Gap backfill error %s %s: %s", symbol, resolution, exc)
        self._drop_time = None

    # ------------------------------------------------------------------
    # Session logging
    # ------------------------------------------------------------------

    async def _open_stream_log(self) -> None:
        from services.backend.app.db.models import IngestionLog
        async with AsyncSessionLocal() as db:
            entry = IngestionLog(
                symbol=None,
                mode="stream",
                job_type="stream_session",
                source="alpaca_stream",
                status="ok",
                rows_written=0,
                started_at=self._session_started_at,
            )
            db.add(entry)
            await db.commit()
            await db.refresh(entry)
            self._session_log_id = entry.id

    async def _close_stream_log(self) -> None:
        if not self._session_log_id:
            return
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("""
                    UPDATE ingestion_log
                    SET ended_at = NOW(), rows_written = :rows, status = 'ok'
                    WHERE id = :id
                """),
                {"rows": self._bars_written_session, "id": self._session_log_id},
            )
            await db.commit()


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------
stream_manager = StreamManager()


def _infer_res(bar) -> str:
    try:
        tf = bar.timeframe
        m = {"1Min": "1m", "5Min": "5m", "15Min": "15m", "1Hour": "1h", "1Day": "1d"}
        return m.get(tf, "1m")
    except AttributeError:
        return "1m"


def _to_dict(bar) -> dict:
    return {
        "ts": bar.timestamp,
        "open": float(bar.open),
        "high": float(bar.high),
        "low": float(bar.low),
        "close": float(bar.close),
        "volume": int(bar.volume),
    }
