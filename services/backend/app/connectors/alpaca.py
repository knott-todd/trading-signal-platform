"""
Alpaca connector using alpaca-py SDK.
Live trading account required for real-time WebSocket data.
"""
import asyncio
import logging
import threading
from datetime import date, datetime
from typing import Callable, Dict, List, Optional

import pandas as pd
from alpaca.data import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from app.config import settings
from app.connectors.base import ConnectorInterface

log = logging.getLogger(__name__)

# Map spec resolution strings → Alpaca TimeFrame objects
_RESOLUTION_MAP: Dict[str, TimeFrame] = {
    "1m":  TimeFrame(1,  TimeFrameUnit.Minute),
    "5m":  TimeFrame(5,  TimeFrameUnit.Minute),
    "15m": TimeFrame(15, TimeFrameUnit.Minute),
    "1h":  TimeFrame(1,  TimeFrameUnit.Hour),
    "1d":  TimeFrame(1,  TimeFrameUnit.Day),
}


class AlpacaConnector(ConnectorInterface):

    def __init__(self) -> None:
        self._client = StockHistoricalDataClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
        )
        self._stream: Optional[StockDataStream] = None
        self._stream_thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Fetch methods
    # ------------------------------------------------------------------

    def get_daily_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=_RESOLUTION_MAP["1d"],
            start=datetime.combine(start, datetime.min.time()),
            end=datetime.combine(end, datetime.min.time()),
            adjustment="all",
        )
        bars = self._client.get_stock_bars(request)
        return self._to_dataframe(bars, symbol)

    def get_intraday_bars(
        self, symbol: str, resolution: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        if resolution not in _RESOLUTION_MAP:
            raise ValueError(f"Unsupported resolution: {resolution}")
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=_RESOLUTION_MAP[resolution],
            start=start,
            end=end,
            adjustment="all",
        )
        bars = self._client.get_stock_bars(request)
        return self._to_dataframe(bars, symbol)

    # ------------------------------------------------------------------
    # Stream methods
    # ------------------------------------------------------------------

    def stream_bars(
        self, symbols: List[str], resolutions: List[str], callback: Callable
    ) -> None:
        """
        Open a WebSocket stream for the given symbols.
        alpaca-py streams by resolution via separate subscriptions — we subscribe
        to bars for each (symbol, resolution) combination.
        The callback is called per bar: callback(symbol, resolution, bar_dict).
        """
        self._callback = callback
        self._stream = StockDataStream(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
        )

        async def _bar_handler(bar) -> None:
            if self._callback is None:
                return
            # Infer resolution from the incoming bar's timeframe if available,
            # otherwise emit for all subscribed resolutions (alpaca-py streams all)
            bar_dict = {
                "ts":     bar.timestamp,
                "open":   float(bar.open),
                "high":   float(bar.high),
                "low":    float(bar.low),
                "close":  float(bar.close),
                "volume": int(bar.volume),
            }
            # alpaca-py bar objects carry .timeframe for minute bars
            resolution = _infer_resolution(bar)
            self._callback(bar.symbol, resolution, bar_dict)

        self._stream.subscribe_bars(_bar_handler, *symbols)

        def _run() -> None:
            self._stream.run()

        self._stream_thread = threading.Thread(target=_run, daemon=True, name="alpaca-stream")
        self._stream_thread.start()
        log.info("Alpaca WebSocket stream started for %d symbols.", len(symbols))

    def stop_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                log.info("Alpaca WebSocket stream stopped.")
            except Exception as exc:
                log.warning("Error stopping stream: %s", exc)
            finally:
                self._stream = None
                self._stream_thread = None

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        try:
            # Lightweight call — fetch latest bar for a known liquid ticker
            request = StockBarsRequest(
                symbol_or_symbols="SPY",
                timeframe=_RESOLUTION_MAP["1d"],
                limit=1,
            )
            self._client.get_stock_bars(request)
            return True
        except Exception as exc:
            log.warning("Alpaca health check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dataframe(bars, symbol: str) -> pd.DataFrame:
        """Normalise alpaca-py BarSet response to standard DataFrame format."""
        try:
            df = bars.df
        except AttributeError:
            return _empty_df()

        if df.empty:
            return _empty_df()

        # alpaca-py returns a MultiIndex (symbol, timestamp) when multi-symbol
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level="symbol")

        df = df.reset_index()
        df = df.rename(columns={"timestamp": "ts"})
        df = df[["ts", "open", "high", "low", "close", "volume"]]
        df["open"]   = df["open"].astype(float)
        df["high"]   = df["high"].astype(float)
        df["low"]    = df["low"].astype(float)
        df["close"]  = df["close"].astype(float)
        df["volume"] = df["volume"].astype(int)

        if not pd.api.types.is_datetime64tz_dtype(df["ts"]):
            df["ts"] = pd.to_datetime(df["ts"], utc=True)

        return df


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])


def _infer_resolution(bar) -> str:
    """Best-effort resolution inference from an alpaca-py bar object."""
    try:
        tf = bar.timeframe
        if tf == "1Min":
            return "1m"
        if tf == "5Min":
            return "5m"
        if tf == "15Min":
            return "15m"
        if tf == "1Hour":
            return "1h"
        if tf == "1Day":
            return "1d"
    except AttributeError:
        pass
    return "1m"  # default for stream bars
