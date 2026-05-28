"""
Unit tests for the validation layer. No DB required.
"""
import pytest
from datetime import datetime, timezone
from app.services.validation import validate_bar, validate_batch


def _make_bar(o=100.0, h=105.0, l=98.0, c=102.0, v=10000, ts=None):
    return {
        "ts": ts or datetime.now(tz=timezone.utc),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
    }


class TestValidateBar:
    def test_valid_bar_passes(self):
        bar, flagged = validate_bar(_make_bar(), "AAPL", "1d")
        assert bar is not None
        assert flagged is False

    def test_ohlc_integrity_high_lt_low_rejected(self):
        bar, _ = validate_bar(_make_bar(h=95.0, l=100.0), "AAPL", "1d")
        assert bar is None

    def test_ohlc_integrity_close_gt_high_rejected(self):
        bar, _ = validate_bar(_make_bar(h=101.0, c=110.0), "AAPL", "1d")
        assert bar is None

    def test_zero_volume_rejected(self):
        bar, _ = validate_bar(_make_bar(v=0), "AAPL", "1d")
        assert bar is None

    def test_negative_volume_rejected(self):
        bar, _ = validate_bar(_make_bar(v=-1), "AAPL", "1d")
        assert bar is None

    def test_spike_flagged_not_rejected(self):
        # Close must be <= high for OHLC to pass
        bar, flagged = validate_bar(_make_bar(o=180.0, h=210.0, l=178.0, c=200.0), "AAPL", "1d", previous_close=100.0)
        assert bar is not None
        assert flagged is True

    def test_no_spike_without_previous_close(self):
        bar, flagged = validate_bar(_make_bar(o=180.0, h=210.0, l=178.0, c=200.0), "AAPL", "1d", previous_close=None)
        assert bar is not None
        assert flagged is False

    def test_spike_threshold_above_50pct_flagged(self):
        # >50% above previous close triggers flag
        bar, flagged = validate_bar(_make_bar(o=151.0, h=156.0, l=150.0, c=151.0), "AAPL", "1d", previous_close=100.0)
        assert flagged is True

    def test_spike_threshold_exactly_50pct_not_flagged(self):
        # Exactly 50% is NOT above threshold (strict >)
        bar, flagged = validate_bar(_make_bar(o=148.0, h=155.0, l=147.0, c=150.0), "AAPL", "1d", previous_close=100.0)
        assert flagged is False

    def test_below_spike_threshold_not_flagged(self):
        bar, flagged = validate_bar(_make_bar(c=110.0, h=115.0), "AAPL", "1d", previous_close=100.0)
        assert flagged is False


class TestValidateBatch:
    def _ts(self, offset_minutes: int):
        from datetime import timedelta
        return datetime.now(tz=timezone.utc) + timedelta(minutes=offset_minutes)

    def test_valid_batch_passes(self):
        bars = [
            _make_bar(ts=self._ts(0)),
            _make_bar(ts=self._ts(1)),
            _make_bar(ts=self._ts(2)),
        ]
        valid, flagged, rejected = validate_batch(bars, "AAPL", "1m")
        assert len(valid) == 3
        assert rejected == 0

    def test_out_of_order_batch_rejected(self):
        bars = [
            _make_bar(ts=self._ts(2)),
            _make_bar(ts=self._ts(0)),  # out of order
        ]
        valid, flagged, rejected = validate_batch(bars, "AAPL", "1m")
        assert len(valid) == 0
        assert rejected == 2

    def test_partial_batch_invalid_bars_counted(self):
        bars = [
            _make_bar(ts=self._ts(0)),
            _make_bar(ts=self._ts(1), v=0),  # invalid — zero volume
            _make_bar(ts=self._ts(2)),
        ]
        valid, _, rejected = validate_batch(bars, "AAPL", "1m")
        assert len(valid) == 2
        assert rejected == 1
