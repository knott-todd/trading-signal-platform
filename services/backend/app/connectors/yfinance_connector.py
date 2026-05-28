"""
yfinance connector — historical backfill fallback only.
No API key required. Does not implement stream_bars.
"""
import logging
from datetime import date, datetime
from typing import Callable, List

import pandas as pd
import yfinance as yf

from services.backend.app.connectors.base import ConnectorInterface

log = logging.getLogger(__name__)

_YF_INTERVAL_MAP = {
    "1m":  "1m",
    "5m":  "5m",
    "15m": "15m",
    "1h":  "1h",
    "1d":  "1d",
}


class YFinanceConnector(ConnectorInterface):

    def get_daily_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        ticker = yf.Ticker(symbol)
        df = ticker.history(
            start=start.isoformat(),
            end=end.isoformat(),
            interval="1d",
            auto_adjust=True,
        )
        return self._normalise(df)

    def get_intraday_bars(
        self, symbol: str, resolution: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        if resolution not in _YF_INTERVAL_MAP:
            raise ValueError(f"Unsupported resolution: {resolution}")
        ticker = yf.Ticker(symbol)
        df = ticker.history(
            start=start.isoformat(),
            end=end.isoformat(),
            interval=_YF_INTERVAL_MAP[resolution],
            auto_adjust=True,
        )
        return self._normalise(df)

    def stream_bars(
        self, symbols: List[str], resolutions: List[str], callback: Callable
    ) -> None:
        raise NotImplementedError(
            "yfinance does not support WebSocket streaming. "
            "Module will operate in fetch-only mode."
        )

    def stop_stream(self) -> None:
        pass  # No stream to stop

    def health_check(self) -> bool:
        try:
            ticker = yf.Ticker("SPY")
            hist = ticker.history(period="1d")
            return not hist.empty
        except Exception as exc:
            log.warning("yfinance health check failed: %s", exc)
            return False

    @staticmethod
    def _normalise(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])

        df = df.reset_index()
        # yfinance returns 'Date' or 'Datetime' depending on interval
        date_col = "Datetime" if "Datetime" in df.columns else "Date"
        df = df.rename(columns={
            date_col: "ts",
            "Open":   "open",
            "High":   "high",
            "Low":    "low",
            "Close":  "close",
            "Volume": "volume",
        })
        df = df[["ts", "open", "high", "low", "close", "volume"]]
        df["open"]   = df["open"].astype(float)
        df["high"]   = df["high"].astype(float)
        df["low"]    = df["low"].astype(float)
        df["close"]  = df["close"].astype(float)
        df["volume"] = df["volume"].astype(int)

        # Ensure timezone-aware
        if not pd.api.types.is_datetime64tz_dtype(df["ts"]):
            df["ts"] = pd.to_datetime(df["ts"], utc=True)

        return df
