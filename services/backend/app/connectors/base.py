"""
Abstract base class for all market data connectors.
Every connector must implement all five methods.
The ingestion service never calls Finnhub or yfinance directly.
"""
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Callable, List
import pandas as pd


class ConnectorInterface(ABC):

    @abstractmethod
    def get_daily_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """
        Return daily OHLCV bars for symbol between start and end (inclusive).
        DataFrame columns: ts (DatetimeTZDtype), open, high, low, close, volume
        """

    @abstractmethod
    def get_intraday_bars(
        self, symbol: str, resolution: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        """
        Return intraday OHLCV bars at given resolution.
        resolution: '1m' | '5m' | '15m' | '1h'
        DataFrame columns: ts, open, high, low, close, volume
        """

    @abstractmethod
    def stream_bars(
        self, symbols: List[str], resolutions: List[str], callback: Callable
    ) -> None:
        """
        Open a WebSocket stream for the given symbols and resolutions.
        Calls callback(symbol: str, resolution: str, bar: dict) for each incoming bar.
        bar dict keys: ts, open, high, low, close, volume
        """

    @abstractmethod
    def stop_stream(self) -> None:
        """Gracefully close the WebSocket stream."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the connector can reach its data source."""
