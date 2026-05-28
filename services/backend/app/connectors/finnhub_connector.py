"""
Finnhub connector — primary data source (ADR-002).
REST: finnhub-python SDK with a 60 calls/minute rate limiter.
WebSocket: wss://ws.finnhub.io delivers raw trades; bar assembly is the
           stream manager's responsibility, not this connector's.
Requires FINNHUB_API_KEY environment variable (free tier, finnhub.io).
"""
import json
import logging
import threading
import time
from collections import deque
from datetime import date, datetime, timezone
from typing import Callable, Dict, List, Optional

import finnhub
import pandas as pd
import websocket

from app.config import settings
from app.connectors.base import ConnectorInterface

log = logging.getLogger(__name__)

# Finnhub REST resolution strings
_RESOLUTION_MAP: Dict[str, str] = {
    "1m":  "1",
    "5m":  "5",
    "15m": "15",
    "1h":  "60",
    "1d":  "D",
}

_FINNHUB_WS_URL = "wss://ws.finnhub.io"


class _RateLimiter:
    """Sliding-window rate limiter — raises RuntimeError if the call budget is
    exhausted rather than silently queuing, so the caller can decide to fall back."""

    def __init__(self, calls_per_minute: int = 60) -> None:
        self._max = calls_per_minute
        self._calls: deque = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            cutoff = now - 60.0
            while self._calls and self._calls[0] < cutoff:
                self._calls.popleft()
            if len(self._calls) >= self._max:
                raise RuntimeError(
                    f"Finnhub REST rate limit reached ({self._max} calls/min). "
                    "Caller should fall back to yfinance or retry after 60 s."
                )
            self._calls.append(now)


class FinnhubConnector(ConnectorInterface):
    """
    Primary market data connector using Finnhub free tier.
    stream_bars delivers raw trades to callback(symbol, trade) — resolution is
    not included because Finnhub streams individual trades, not assembled bars.
    Bar assembly at the requested resolutions is the stream manager's job.
    """

    def __init__(self) -> None:
        self._client = finnhub.Client(api_key=settings.finnhub_api_key)
        self._rate_limiter = _RateLimiter(calls_per_minute=60)
        self._ws: Optional[websocket.WebSocketApp] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable] = None
        self._subscribed: set = set()
        self._ws_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Fetch methods
    # ------------------------------------------------------------------

    def get_daily_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        from_ts = int(datetime.combine(start, datetime.min.time()).replace(tzinfo=timezone.utc).timestamp())
        to_ts   = int(datetime.combine(end,   datetime.max.time()).replace(tzinfo=timezone.utc).timestamp())
        self._rate_limiter.acquire()
        data = self._client.stock_candles(symbol, "D", from_ts, to_ts)
        return self._to_dataframe(data)

    def get_intraday_bars(
        self, symbol: str, resolution: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        if resolution not in _RESOLUTION_MAP:
            raise ValueError(f"Unsupported resolution: {resolution}")
        fh_res = _RESOLUTION_MAP[resolution]
        from_ts = int(start.timestamp())
        to_ts   = int(end.timestamp())
        self._rate_limiter.acquire()
        data = self._client.stock_candles(symbol, fh_res, from_ts, to_ts)
        return self._to_dataframe(data)

    # ------------------------------------------------------------------
    # Stream methods
    # ------------------------------------------------------------------

    def stream_bars(
        self, symbols: List[str], resolutions: List[str], callback: Callable
    ) -> None:
        """
        Open a Finnhub WebSocket and subscribe to the given symbols.
        For each incoming trade message, calls:
            callback(symbol: str, trade: dict)
        where trade = {"price": float, "volume": float, "ts": datetime (UTC)}.
        resolutions is accepted per the interface contract but ignored here —
        bar assembly from these raw trades is the stream manager's responsibility.
        """
        self._callback = callback
        self._subscribed = set(symbols)

        def _on_open(ws: websocket.WebSocketApp) -> None:
            log.info("Finnhub WebSocket opened — subscribing to %d symbols.", len(symbols))
            for sym in symbols:
                ws.send(json.dumps({"type": "subscribe", "symbol": sym}))

        def _on_message(ws: websocket.WebSocketApp, raw: str) -> None:
            try:
                msg = json.loads(raw)
            except Exception:
                return
            if msg.get("type") != "trade" or not msg.get("data"):
                return
            for trade in msg["data"]:
                sym = trade.get("s")
                price = trade.get("p")
                volume = trade.get("v", 0)
                ts_ms = trade.get("t")
                if sym is None or price is None or ts_ms is None:
                    continue
                ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
                if self._callback:
                    self._callback(sym, {"price": float(price), "volume": float(volume), "ts": ts})

        def _on_error(ws: websocket.WebSocketApp, error: Exception) -> None:
            log.error("Finnhub WebSocket error: %s", error)

        def _on_close(ws: websocket.WebSocketApp, code: int, msg: str) -> None:
            log.info("Finnhub WebSocket closed (code=%s).", code)

        url = f"{_FINNHUB_WS_URL}?token={settings.finnhub_api_key}"
        self._ws = websocket.WebSocketApp(
            url,
            on_open=_on_open,
            on_message=_on_message,
            on_error=_on_error,
            on_close=_on_close,
        )

        self._ws_thread = threading.Thread(
            target=self._ws.run_forever,
            kwargs={"ping_interval": 30, "ping_timeout": 10},
            daemon=True,
            name="finnhub-ws",
        )
        self._ws_thread.start()
        log.info("Finnhub WebSocket stream started for %d symbols.", len(symbols))

    def stop_stream(self) -> None:
        with self._ws_lock:
            if self._ws is not None:
                try:
                    self._ws.close()
                    log.info("Finnhub WebSocket stream stopped.")
                except Exception as exc:
                    log.warning("Error stopping Finnhub stream: %s", exc)
                finally:
                    self._ws = None
                    self._ws_thread = None
                    self._subscribed.clear()

    def subscribe_symbols(self, symbols: List[str]) -> None:
        """Add symbols to an already-running stream."""
        with self._ws_lock:
            if self._ws is None:
                return
            for sym in symbols:
                if sym not in self._subscribed:
                    self._ws.send(json.dumps({"type": "subscribe", "symbol": sym}))
                    self._subscribed.add(sym)
                    log.debug("Finnhub subscribed: %s", sym)

    def unsubscribe_symbols(self, symbols: List[str]) -> None:
        """Remove symbols from a running stream."""
        with self._ws_lock:
            if self._ws is None:
                return
            for sym in symbols:
                if sym in self._subscribed:
                    self._ws.send(json.dumps({"type": "unsubscribe", "symbol": sym}))
                    self._subscribed.discard(sym)
                    log.debug("Finnhub unsubscribed: %s", sym)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        try:
            self._rate_limiter.acquire()
            quote = self._client.quote("SPY")
            return quote.get("c", 0) > 0
        except Exception as exc:
            log.warning("Finnhub health check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dataframe(data: dict) -> pd.DataFrame:
        if not data or data.get("s") != "ok":
            return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])

        df = pd.DataFrame({
            "ts":     data["t"],
            "open":   data["o"],
            "high":   data["h"],
            "low":    data["l"],
            "close":  data["c"],
            "volume": data["v"],
        })
        df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True)
        df["open"]   = df["open"].astype(float)
        df["high"]   = df["high"].astype(float)
        df["low"]    = df["low"].astype(float)
        df["close"]  = df["close"].astype(float)
        df["volume"] = df["volume"].astype(int)
        return df
