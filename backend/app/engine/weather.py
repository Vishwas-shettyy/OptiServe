"""Capacity weather: turn a demand forecast into a strip of sun / cloud / storm slots. Pure: no I/O."""

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from app.engine.common import utc

QUIET_BELOW = 0.35  # share of current capacity: below this the slot is "sun"
STORM_FROM = 0.75  # at or above this (same as the "busy" CPU threshold) the slot is "storm"


@dataclass
class WeatherSlot:
    """One slot of the strip: its start, the expected and high share of capacity, and the icon."""

    start: datetime
    expected_util: float
    high_util: float
    kind: str  # sun | cloud | storm


def classify(expected_util: float, high_util: float) -> str:
    """Return sun / cloud / storm. Storm when the expected load, or the top of the band, reaches 'busy'."""
    if expected_util >= STORM_FROM or high_util >= STORM_FROM + 0.15:
        return "storm"
    if expected_util < QUIET_BELOW:
        return "sun"
    return "cloud"


def weather_slots(
    points: pd.DataFrame, capacity: float, now: datetime, horizon: timedelta, slots: int = 12,
) -> list[WeatherSlot]:
    """Bucket future forecast points (ts, expected, low, high in server-equivalents) into equal slots.

    Slots start at `now` rounded down to the slot size, so their time labels are whole steps.

    Each slot uses its peak expected and peak high value divided by capacity (servers running now).
    Slots without forecast points are left out rather than guessed.
    """
    if points.empty or capacity <= 0 or slots <= 0:
        return []
    now_ts = utc(now)
    step = horizon / slots
    base = now_ts.floor(pd.Timedelta(step))  # clean labels: 14:00, 16:00… or 14:05, 14:10…
    df = points.copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df[(df["ts"] >= now_ts) & (df["ts"] < base + horizon)]
    out: list[WeatherSlot] = []
    for i in range(slots):
        start = base + step * i
        chunk = df[(df["ts"] >= start) & (df["ts"] < start + step)]
        if chunk.empty:
            continue
        exp = max(0.0, float(chunk["expected"].max())) / capacity
        high = max(0.0, float(chunk["high"].max())) / capacity
        out.append(WeatherSlot(start.to_pydatetime(), round(exp, 3), round(high, 3), classify(exp, high)))
    return out
