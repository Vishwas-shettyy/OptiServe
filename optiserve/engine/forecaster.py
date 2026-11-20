"""Demand forecasting, anomaly detection and naive baseline."""

import numpy as np
import pandas as pd

from engine.data_gen import ZOMBIE_SERVICE

FORECAST_COLUMNS = ["timestamp", "expected", "low", "high", "mem_high", "is_event"]
HOURS_PER_WEEK = 168


def _how(ts: pd.DatetimeIndex | pd.Series) -> np.ndarray:
    """Return hour-of-week (weekday*24+hour) for timestamps."""
    idx = pd.DatetimeIndex(ts)
    return (idx.day_of_week * 24 + idx.hour).to_numpy()


def _event_mask(ts: pd.DatetimeIndex, events: pd.DataFrame, service: str | None) -> pd.Series:
    """Return a boolean Series marking timestamps inside any event of the service."""
    mask = np.zeros(len(ts), dtype=bool)
    evs = events if service is None or events.empty else events[events["service"] == service]
    for ev in evs.itertuples(index=False):
        mask |= (ts >= ev.start) & (ts <= ev.end)
    return pd.Series(mask, index=ts)


def _event_multiplier(ts: pd.DatetimeIndex, events: pd.DataFrame, service: str | None) -> np.ndarray:
    """Return the event multiplier per timestamp (1.0 outside events)."""
    mult = np.ones(len(ts))
    evs = events if service is None or events.empty else events[events["service"] == service]
    for ev in evs.itertuples(index=False):
        mult[(ts >= ev.start) & (ts <= ev.end)] *= float(ev.multiplier)
    return mult


def service_demand(metrics: pd.DataFrame, servers: pd.DataFrame) -> pd.DataFrame:
    """Aggregate hourly demand per service, excluding zombies."""
    active = servers.loc[servers["service"] != ZOMBIE_SERVICE, "server_id"]
    m = metrics[metrics["server_id"].isin(active)].copy()
    m["mem_load_eq"] = (m["mem_pct"] - 30.0).clip(lower=0.0) / 70.0
    demand = m.groupby(["timestamp", "service"], as_index=False).agg(
        requests=("requests", "sum"), mem_load_eq=("mem_load_eq", "sum")
    )
    return demand.sort_values(["service", "timestamp"]).reset_index(drop=True)


def detect_anomalies(series: pd.Series, event_mask: pd.Series) -> tuple[pd.Series, list[dict]]:
    """Replace hour-of-week outliers with the median and list them."""
    idx = pd.DatetimeIndex(series.index)
    how = pd.Series(_how(idx), index=series.index)
    events = event_mask.reindex(series.index).fillna(False).astype(bool)
    base = series[~events]
    median = base.groupby(how[~events]).median()
    med = how.map(median).fillna(series.groupby(how).transform("median"))
    dev = (series - med).abs()
    mad = dev[~events].groupby(how[~events]).median()
    mad_pt = how.map(mad).fillna(0.0)
    is_anom = (~events) & (mad_pt > 0) & (series > med * 1.5) & (dev > 4.0 * 1.4826 * mad_pt)
    cleaned = series.where(~is_anom, med)
    anomalies = [
        {"timestamp": pd.Timestamp(t), "value": float(series[t]), "expected": float(med[t])}
        for t in series.index[is_anom.to_numpy()]
    ]
    return cleaned, anomalies


def _profile(values: pd.Series, enough: bool) -> tuple[np.ndarray, np.ndarray]:
    """Return (mean, std) arrays of length 168 indexed by hour-of-week, with gaps filled and std floored."""
    how = _how(pd.DatetimeIndex(values.index))
    grouped = values.groupby(how)
    full = pd.RangeIndex(HOURS_PER_WEEK)
    mean = grouped.mean().reindex(full)
    hour_mean = mean.groupby(full % 24).transform("mean")
    mean = mean.fillna(hour_mean).fillna(values.mean()).fillna(0.0)
    if enough:
        std = grouped.std().reindex(full).fillna(0.15 * mean)
    else:
        std = 0.15 * mean
    std = np.maximum(std.to_numpy(), 0.05 * mean.to_numpy())
    return mean.to_numpy(), std


def _trend_ratio(clean: pd.Series, end: pd.Timestamp, days_available: float) -> float:
    """Return mean(last 7 days)/mean(previous 7 days), clipped, or 1.0 with too little data."""
    if days_available < 14:
        return 1.0
    last = clean[clean.index > end - pd.Timedelta(days=7)].mean()
    prev = clean[(clean.index > end - pd.Timedelta(days=14)) & (clean.index <= end - pd.Timedelta(days=7))].mean()
    if not np.isfinite(last) or not np.isfinite(prev) or prev <= 0:
        return 1.0
    return float(np.clip(last / prev, 0.8, 1.3))


def weekly_growth(history: pd.DataFrame, events: pd.DataFrame) -> float:
    """Return mean(last 7 days)/mean(previous 7 days) of event-free, anomaly-cleaned demand (1.0 if unknown)."""
    if history.empty:
        return 1.0
    service = history["service"].iloc[0] if "service" in history else None
    hist = history.sort_values("timestamp").set_index("timestamp")
    idx = pd.DatetimeIndex(hist.index)
    ev_mask = _event_mask(idx, events, service)
    cleaned, _ = detect_anomalies(hist["requests"].astype(float), ev_mask)
    clean = cleaned[~ev_mask.to_numpy()]
    end = idx.max()
    last = clean[clean.index > end - pd.Timedelta(days=7)].mean()
    prev = clean[(clean.index > end - pd.Timedelta(days=14)) & (clean.index <= end - pd.Timedelta(days=7))].mean()
    if not np.isfinite(last) or not np.isfinite(prev) or prev <= 0:
        return 1.0
    return float(last / prev)


def forecast_service(
    history: pd.DataFrame,
    events: pd.DataFrame,
    start: pd.Timestamp,
    hours: int = 168,
    z: float = 1.25,
) -> tuple[pd.DataFrame, list[dict]]:
    """Forecast hourly demand with low/high bands and event multipliers."""
    service = history["service"].iloc[0] if "service" in history and len(history) else None
    hist = history.sort_values("timestamp").set_index("timestamp")
    idx = pd.DatetimeIndex(hist.index)
    ev_mask = _event_mask(idx, events, service)
    cleaned, anomalies = detect_anomalies(hist["requests"].astype(float), ev_mask)
    keep = ~ev_mask.to_numpy()
    clean = cleaned[keep]
    mem = hist["mem_load_eq"].astype(float)[keep]
    end = idx.max()
    days_available = (end - idx.min()) / pd.Timedelta(days=1) + 1.0 / 24.0
    recent = clean.index > end - pd.Timedelta(days=21)
    enough = days_available >= 14
    mean, std = _profile(clean[recent], enough)
    mem_mean, mem_std = _profile(mem[recent], enough)
    ratio = _trend_ratio(clean, end, days_available)
    ts = pd.date_range(pd.Timestamp(start), periods=hours, freq="h")
    how = _how(ts)
    expected = mean[how] * ratio
    band = z * std[how]
    low = np.maximum(0.0, expected - band)
    high = expected + band
    mem_high = mem_mean[how] * ratio + z * mem_std[how]
    mult = _event_multiplier(ts, events, service)
    forecast = pd.DataFrame({
        "timestamp": ts, "expected": expected * mult, "low": low * mult, "high": high * mult,
        "mem_high": mem_high, "is_event": mult != 1.0,
    })
    return forecast[FORECAST_COLUMNS], anomalies


def naive_forecast(history: pd.DataFrame, start: pd.Timestamp, hours: int) -> pd.Series:
    """Forecast each hour as the value one week earlier."""
    s = history.groupby("timestamp")["requests"].sum().sort_index()
    ts = pd.date_range(pd.Timestamp(start), periods=hours, freq="h")
    values = s.reindex(ts - pd.Timedelta(hours=HOURS_PER_WEEK))
    last_week = s.iloc[-HOURS_PER_WEEK:]
    fallback = pd.Series(last_week.to_numpy(), index=_how(pd.DatetimeIndex(last_week.index)))
    fallback = fallback.groupby(level=0).mean()
    filled = np.where(values.isna(), pd.Series(_how(ts)).map(fallback).to_numpy(), values.to_numpy())
    return pd.Series(np.nan_to_num(filled.astype(float)), index=ts, name="naive")


def wape(actual: pd.Series, forecast: pd.Series) -> float:
    """Return weighted absolute percentage error."""
    a = np.asarray(actual, dtype=float)
    f = np.asarray(forecast, dtype=float)
    total = np.abs(a).sum()
    if total <= 0:
        return 0.0
    return float(np.abs(a - f).sum() / total)
