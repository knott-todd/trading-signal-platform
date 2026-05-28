"""
WebSocket stream manager.
Manages the full lifecycle: connect at market open, disconnect at close,
fallback to fetch on drop, reconnect with backoff, backfill on reconnect.

Finnhub delivers raw trades (not pre-built bars). This manager assembles
trades into OHLCV bars at each configured resolution before writing.
Assembly rule (spec ADR-005):
  open = first trade price in window
  high = max trade price
  low  = min trade price
  close = last trade price
  volume = sum of trade sizes
A bar window closes when the next trade falls outside it.
"""
import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from app.config import settings
from app.connectors.finnhub_connector import FinnhubConnector
from app.db.session import AsyncSessionLocal
from app.services.ingestion import ingest_single_bar, ingest_bars, get_latest_close

log = logging.getLogger(__name__)

# Resolution window sizes in seconds
_RESOLUTION_SECONDS: Dict[str, int] = {
    "1m":  60,
    "5m":  300,
    "15m": 900,
    "1h":  3600,
    "1d":  86400,
}


def _window_start(ts: datetime, resolution: str) -> datetime:
    """Truncate ts to the resolution boundary (UTC epoch-aligned)."""
    secs = _RESOLUTION_SECONDS[resolution]
    epoch = ts.timestamp()
    return datetime.fromtimestamp(epoch - (epoch % secs), tz=timezone.utc)


class _BarWindow:
    """Accumulates trades for one (symbol, resolution) time window."""
    __slots__ = ("window_start", "open", "high", "low", "close", "volume")

    def __init__(self, window_start: datetime, price: float, volume: float) -> None:
        self.window_start = window_start
        self.open   = price
        self.high   = price
        self.low    = price
        self.close  = price
        self.volume = volume

    def update(self, price: float, volume: float) -> None:
        self.high   = max(self.high, price)
        self.low    = min(self.low,  price)
        self.close  = price
        self.volume += volume

    def to_bar(self) -> dict:
        return {
            "ts":     self.window_start,
            "open":   self.open,
            "high":   self.high,
            "low":    self.low,
            "close":  self.close,
            "volume": self.volume,
        }


class StreamState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTED    = "connected"
    RECONNECTING = "reconnecting"
    FALLBACK     = "fallback"


class StreamManager:
    def __init__(self) -> None:
        self._connector = FinnhubConnector()
        self._state: StreamState = StreamState.DISCONNECTED
        self._subscribed_symbols: Set[str] = set()
        self._session_started_at: Optional[datetime] = None
        self._session_log_id: Optional[int] = None
        self._fallback_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._drop_time: Optional[datetime] = None
        self._bars_written_session: int = 0
        self._resolutions: List[str] = settings.stream_resolutions_list
        # Bar assembly state: (symbol, resolution) -> open window
        self._bar_windows: Dict[Tuple[str, str], _BarWindow] = {}
        # Event loop reference — set on first start(), used for thread-safe scheduling
        self._loop: Optional[asyncio.AbstractEventLoop] = None

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

        self._loop = asyncio.get_event_loop()
        self._subscribed_symbols = set(symbols)
        self._session_started_at = datetime.now(tz=timezone.utc)
        self._bars_written_session = 0
        self._bar_windows.clear()

        try:
            self._connector.stream_bars(symbols, self._resolutions, self._on_trade)
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

    # ------------------------------------------------------------------
    # Trade receipt and bar assembly (Finnhub-specific path)
    # ------------------------------------------------------------------

    def _on_trade(self, symbol: str, trade: dict) -> None:
        """
        Callback from FinnhubConnector. Runs in the WebSocket thread.
        Assembles trades into bars; flushes closed windows to the DB.
        """
        if self._loop is None:
            return
        price  = trade["price"]
        volume = trade["volume"]
        ts     = trade["ts"]

        for resolution in self._resolutions:
            if resolution not in _RESOLUTION_SECONDS:
                continue
            key       = (symbol, resolution)
            win_start = _window_start(ts, resolution)
            win       = self._bar_windows.get(key)

            if win is None:
                self._bar_windows[key] = _BarWindow(win_start, price, volume)
            elif win.window_start == win_start:
                win.update(price, volume)
            else:
                # Window elapsed — flush it, start the next one
                closed_bar = win.to_bar()
                asyncio.run_coroutine_threadsafe(
                    self._write_bar(symbol, resolution, closed_bar),
                    self._loop,
                )
                self._bar_windows[key] = _BarWindow(win_start, price, volume)

    async def _write_bar(self, symbol: str, resolution: str, bar: dict) -> None:
        async with AsyncSessionLocal() as db:
            prev_close = await get_latest_close(db, symbol, resolution)
            written = await ingest_single_bar(db, symbol, resolution, bar, "finnhub_stream", prev_close)
            await db.commit()
            if written:
                self._bars_written_session += 1

    # ------------------------------------------------------------------
    # Dynamic subscribe / unsubscribe
    # ------------------------------------------------------------------

    async def subscribe(self, symbols: List[str]) -> None:
        """Add tickers to live stream without restarting the connection."""
        new_symbols = [s for s in symbols if s not in self._subscribed_symbols]
        if not new_symbols:
            return
        if len(self._subscribed_symbols) + len(new_symbols) > settings.max_stream_tickers:
            raise ValueError(f"Would exceed MAX_STREAM_TICKERS={settings.max_stream_tickers}")
        self._subscribed_symbols.update(new_symbols)
        if self._state == StreamState.CONNECTED:
            self._connector.subscribe_symbols(new_symbols)
            log.info("Subscribed to live stream: %s", new_symbols)

    async def unsubscribe(self, symbols: List[str]) -> None:
        """Remove tickers from live stream."""
        self._subscribed_symbols -= set(symbols)
        if self._state == StreamState.CONNECTED:
            self._connector.unsubscribe_symbols(symbols)

    # ------------------------------------------------------------------
    # Connection drop handling
    # ------------------------------------------------------------------

    async def on_connection_drop(self) -> None:
        """Called when stream drops unexpectedly during market hours."""
        log.warning("Stream CONNECTION DROP detected.")
        self._drop_time = datetime.now(tz=timezone.utc)
        self._state = StreamState.RECONNECTING
        await self._start_fallback()
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    # ------------------------------------------------------------------
    # Fallback + reconnect
    # ------------------------------------------------------------------

    async def _start_fallback(self) -> None:
        self._state = StreamState.FALLBACK
        log.info("Switching to FALLBACK fetch mode at %ds interval.", settings.stream_fallback_poll_seconds)
        self._fallback_task = asyncio.create_task(self._fallback_poll_loop())

    async def _fallback_poll_loop(self) -> None:
        from datetime import timedelta
        connector = FinnhubConnector()
        while self._state in (StreamState.FALLBACK, StreamState.RECONNECTING):
            for symbol in list(self._subscribed_symbols):
                for resolution in self._resolutions:
                    try:
                        now   = datetime.now(tz=timezone.utc)
                        start = now - timedelta(minutes=30)
                        df = connector.get_intraday_bars(symbol, resolution, start, now)
                        if df.empty:
                            continue
                        bars = df.to_dict("records")
                        async with AsyncSessionLocal() as db:
                            await ingest_bars(
                                db, bars, symbol, resolution,
                                "finnhub_fetch", "fetch", "intraday_poll",
                            )
                    except RuntimeError as exc:
                        # Rate limit hit — back off for the rest of this poll cycle
                        log.warning("Fallback rate limit: %s — skipping remainder of poll.", exc)
                        break
                    except Exception as exc:
                        log.warning("Fallback poll error %s %s: %s", symbol, resolution, exc)
            await asyncio.sleep(settings.stream_fallback_poll_seconds)

    async def _reconnect_loop(self) -> None:
        delay     = 30
        max_delay = 300
        while self._state in (StreamState.RECONNECTING, StreamState.FALLBACK):
            await asyncio.sleep(delay)
            log.info("Attempting stream reconnect...")
            try:
                symbols = list(self._subscribed_symbols)
                self._connector.stop_stream()
                self._bar_windows.clear()
                self._connector.stream_bars(symbols, self._resolutions, self._on_trade)
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
        """Fill the gap from drop-time to now using Finnhub REST."""
        if not self._drop_time:
            return
        connector = FinnhubConnector()
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
                            "finnhub_fetch", "fetch", "backfill",
                        )
                except Exception as exc:
                    log.warning("Gap backfill error %s %s: %s", symbol, resolution, exc)
        self._drop_time = None

    # ------------------------------------------------------------------
    # Session logging
    # ------------------------------------------------------------------

    async def _open_stream_log(self) -> None:
        from app.db.models import IngestionLog
        async with AsyncSessionLocal() as db:
            entry = IngestionLog(
                symbol=None,
                mode="stream",
                job_type="stream_session",
                source="finnhub_stream",
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


# Module-level singleton
stream_manager = StreamManager()
