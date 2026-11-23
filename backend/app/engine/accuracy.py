"""Forecast accuracy as 100 − WAPE, measured on real outcomes. Pure."""

from datetime import timedelta
from typing import Optional

import numpy as np
import pandas as pd

from app.engine.common import utc


def wape(actual: np.ndarray, forecast: np.ndarray) -> Optional[float]:
    """Return Σ|actual − forecast| / Σ|actual|, or None when there is nothing to compare."""
    a = np.asarray(actual, dtype=float)
    f = np.asarray(forecast, dtype=float)
    ok = np.isfinite(a) & np.isfinite(f)
    a, f = a[ok], f[ok]
    total = float(np.abs(a).sum())
    if len(a) == 0 or total <= 0:
        return None
    return float(np.abs(a - f).sum() / total)


def accuracy_pct(actual: np.ndarray, forecast: np.ndarray) -> Optional[float]:
    """Return 100 − WAPE×100, clipped to 0–100, or None."""
    w = wape(actual, forecast)
    return None if w is None else round(float(np.clip(100.0 - w * 100.0, 0.0, 100.0)), 1)


def score_forecasts(
    forecast_points: pd.DataFrame, actual: pd.DataFrame, now: pd.Timestamp, window: timedelta = timedelta(hours=24),
) -> dict:
    """Match past forecast points (ts, expected) to actual demand (ts, demand) by minute over the window."""
    now = utc(now)
    if forecast_points.empty or actual.empty:
        return {"accuracy_pct": None, "wape": None, "points": 0}
    fc = forecast_points[["ts", "expected"]].copy()
    fc["ts"] = pd.to_datetime(fc["ts"], utc=True).dt.floor("min")
    fc = fc[(fc["ts"] > now - window) & (fc["ts"] <= now)]
    act = actual[["ts", "demand"]].copy()
    act["ts"] = pd.to_datetime(act["ts"], utc=True).dt.floor("min")
    act = act.groupby("ts", as_index=False)["demand"].mean()
    joined = fc.merge(act, on="ts", how="inner")
    w = wape(joined["demand"].to_numpy(), joined["expected"].to_numpy())
    return {
        "accuracy_pct": None if w is None else round(float(np.clip(100.0 - w * 100.0, 0.0, 100.0)), 1),
        "wape": None if w is None else round(w, 4),
        "points": int(len(joined)),
    }
