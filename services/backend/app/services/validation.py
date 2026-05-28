"""
Validation layer. Every bar — stream or fetch — passes through here.
Source mode does not affect validation rules.
Returns (validated_bars, rejected_count) where validated_bars may include flagged rows.
"""
import logging
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

SPIKE_THRESHOLD = 0.50  # Close must be within 50% of previous close


def validate_bar(
    bar: Dict,
    symbol: str,
    resolution: str,
    previous_close: Optional[float] = None,
) -> Tuple[Optional[Dict], bool]:
    """
    Validate a single bar dict.
    Returns (bar_dict_or_None, flagged).
    Returns (None, False) if the bar should be rejected entirely.
    Returns (bar, True) if the bar passes but triggered a spike warning.
    """
    o, h, l, c, v = (
        bar.get("open"),
        bar.get("high"),
        bar.get("low"),
        bar.get("close"),
        bar.get("volume"),
    )

    # OHLC integrity
    if not (h >= l and h >= o and h >= c and l <= o and l <= c):
        log.warning(
            "REJECTED %s %s — OHLC integrity failed: O=%.4f H=%.4f L=%.4f C=%.4f",
            symbol, resolution, o, h, l, c,
        )
        return None, False

    # Zero volume
    if v is None or v <= 0:
        log.warning("REJECTED %s %s — zero/null volume", symbol, resolution)
        return None, False

    # Spike detection
    flagged = False
    if previous_close is not None and previous_close > 0:
        change = abs(c - previous_close) / previous_close
        if change > SPIKE_THRESHOLD:
            log.warning(
                "FLAGGED %s %s — price spike: close=%.4f prev_close=%.4f change=%.1f%%",
                symbol, resolution, c, previous_close, change * 100,
            )
            flagged = True

    return bar, flagged


def validate_batch(
    bars: List[Dict],
    symbol: str,
    resolution: str,
    previous_close: Optional[float] = None,
) -> Tuple[List[Dict], List[bool], int]:
    """
    Validate a list of bars (fetch mode batch).
    Also checks timestamp ordering — rejects entire batch if out of order.
    Returns (valid_bars, flagged_list, rejected_count).
    """
    if not bars:
        return [], [], 0

    # Timestamp ordering check
    timestamps = [b["ts"] for b in bars]
    for i in range(1, len(timestamps)):
        if timestamps[i] <= timestamps[i - 1]:
            log.error(
                "BATCH REJECTED %s %s — timestamps out of order at index %d",
                symbol, resolution, i,
            )
            return [], [], len(bars)

    valid_bars: List[Dict] = []
    flagged_list: List[bool] = []
    rejected = 0
    prev_close = previous_close

    for bar in bars:
        result, flag = validate_bar(bar, symbol, resolution, prev_close)
        if result is None:
            rejected += 1
        else:
            result["flagged"] = flag
            valid_bars.append(result)
            flagged_list.append(flag)
            prev_close = result["close"]

    return valid_bars, flagged_list, rejected
