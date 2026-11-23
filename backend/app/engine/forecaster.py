"""Group demand, short forecast (Holt linear, 60 min) and plan forecast (hour-of-week + trend, 7 days). Pure."""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from app.engine.common import EngineParams, normalize_metrics, utc

POINT_COLUMNS = ["ts", "expected", "low", "high"]
DEMAND_COLUMNS = ["ts", "cpu", "mem", "demand", "resource"]
HOURS_PER_WEEK = 168
ALPHAS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
BETAS = (0.05, 0.1, 0.2, 0.3, 0.4, 0.5)


@dataclass
class ForecastResult:
    """Forecast points (ts, expected, low, high) plus status 'ok' or 'learning' and a plain message."""

    points: pd.DataFrame
    method: str
    status: str
    message: str
    resource: str = "cpu"
    anomalies: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True when the forecast has usable points."""
        return self.status == "ok" and not self.points.empty


def _empty_points() -> pd.DataFrame:
    """Return an empty points frame."""
    return pd.DataFrame({
        "ts": pd.Series(dtype="datetime64[ns, UTC]"), "expected": pd.Series(dtype=float),
        "low": pd.Series(dtype=float), "high": pd.Series(dtype=float),
    })


def _per_server(m: pd.DataFrame, column: str, index: pd.DatetimeIndex, limit: int) -> pd.Series:
    """Return the per-bucket sum over servers of one metric (/100), forward-filling short gaps."""
    wide = m.groupby(["bucket", "server_id"])[column].mean().unstack("server_id")
    wide = wide.reindex(index).ffill(limit=limit)
    return wide.sum(axis=1, min_count=1) / 100.0


def group_demand(metrics: pd.DataFrame, freq: str = "1min") -> pd.DataFrame:
    """Return group demand in server-equivalents per bucket: max(Σcpu/100, Σmem/100)."""
    m = normalize_metrics(metrics)
    if m.empty:
        return pd.DataFrame({c: pd.Series(dtype=float) for c in DEMAND_COLUMNS}).assign(
            ts=pd.Series(dtype="datetime64[ns, UTC]"), resource=pd.Series(dtype=object))
    m["bucket"] = m["ts"].dt.floor(freq)
    index = pd.date_range(m["bucket"].min(), m["bucket"].max(), freq=freq)
    cpu = _per_server(m, "cpu_pct", index, 2)
    mem = _per_server(m, "mem_pct", index, 2)
    demand = np.fmax(cpu.to_numpy(dtype=float), mem.to_numpy(dtype=float))
    resource = np.where(mem.to_numpy(dtype=float) > cpu.to_numpy(dtype=float), "memory", "cpu")
    out = pd.DataFrame({"ts": index, "cpu": cpu.to_numpy(), "mem": mem.to_numpy(), "demand": demand, "resource": resource})
    return out.dropna(subset=["demand"]).reset_index(drop=True)


def _holt_run(y: np.ndarray, alpha: float, beta: float) -> tuple[float, float, np.ndarray]:
    """Run Holt linear smoothing and return (level, trend, one-step-ahead residuals)."""
    k = min(4, len(y) - 1)
    level, trend = float(y[0]), float((y[k] - y[0]) / k) if k > 0 else 0.0
    residuals = np.empty(len(y) - 1)
    for t in range(1, len(y)):
        residuals[t - 1] = y[t] - (level + trend)
        new_level = alpha * y[t] + (1 - alpha) * (level + trend)
        trend = beta * (new_level - level) + (1 - beta) * trend
        level = new_level
    return level, trend, residuals


def holt_linear(y: np.ndarray) -> tuple[float, float, float]:
    """Fit Holt linear smoothing by grid search on squared one-step errors; return (level, trend, residual std)."""
    best: Optional[tuple[float, float, float, float]] = None
    for a in ALPHAS:
        for b in BETAS:
            level, trend, res = _holt_run(y, a, b)
            sse = float(np.sum(res ** 2))
            if best is None or sse < best[0]:
                best = (sse, level, trend, float(np.std(res, ddof=1)) if len(res) > 1 else 0.0)
    assert best is not None
    return best[1], best[2], best[3]


def short_forecast(demand: pd.DataFrame, now: pd.Timestamp, params: EngineParams, z: float) -> ForecastResult:
    """Forecast the next 60 minutes at 1-minute steps from the last 60 minutes of demand."""
    now = utc(now)
    hist = demand[(demand["ts"] > now - params.short_history) & (demand["ts"] <= now)] if len(demand) else demand
    if len(hist) < params.short_min_points:
        return ForecastResult(_empty_points(), "holt", "learning",
                              f"Learning: {len(hist)} of {params.short_min_points} minutes of recent data collected")
    y = hist["demand"].to_numpy(dtype=float)
    level, trend, std = holt_linear(y)
    std = max(std, 0.005, 0.01 * abs(level))
    h = np.arange(1, params.short_horizon_min + 1)
    expected = np.maximum(0.0, level + h * trend)
    band = z * std
    ts = pd.date_range(now.floor("min") + pd.Timedelta(minutes=1), periods=len(h), freq="min")
    points = pd.DataFrame({"ts": ts, "expected": expected, "low": np.maximum(0.0, expected - band), "high": expected + band})
    resource = str(hist["resource"].iloc[-1]) if "resource" in hist else "cpu"
    return ForecastResult(points, "holt", "ok", "Forecast ready", resource=resource)


def _how(ts: pd.DatetimeIndex) -> np.ndarray:
    """Return hour-of-week (weekday*24+hour) for timestamps."""
    idx = pd.DatetimeIndex(ts)
    return (idx.day_of_week * 24 + idx.hour).to_numpy()


def detect_anomalies(series: pd.Series) -> tuple[pd.Series, list[dict]]:
    """Replace hour-of-week spikes (>1.5× median and >4 MADs) with the median and list them."""
    how = pd.Series(_how(pd.DatetimeIndex(series.index)), index=series.index)
    med = series.groupby(how).transform("median")
    dev = (series - med).abs()
    mad = dev.groupby(how).transform("median")
    is_anom = (mad > 0) & (series > med * 1.5) & (dev > 4.0 * 1.4826 * mad)
    anomalies = [{"ts": pd.Timestamp(t), "value": float(series[t]), "expected": float(med[t])}
                 for t in series.index[is_anom.to_numpy()]]
    return series.where(~is_anom, med), anomalies


def _profile(values: pd.Series, enough: bool) -> tuple[np.ndarray, np.ndarray]:
    """Return (mean, std) arrays of length 168 by hour-of-week, gaps filled and std floored."""
    how = _how(pd.DatetimeIndex(values.index))
    grouped = values.groupby(how)
    full = pd.RangeIndex(HOURS_PER_WEEK)
    mean = grouped.mean().reindex(full)
    mean = mean.fillna(mean.groupby(full % 24).transform("mean")).fillna(values.mean()).fillna(0.0)
    std = grouped.std().reindex(full).fillna(0.15 * mean) if enough else 0.15 * mean
    return mean.to_numpy(), np.maximum(np.asarray(std, dtype=float), 0.05 * mean.to_numpy())


def _trend_ratio(clean: pd.Series, end: pd.Timestamp, days: float) -> float:
    """Return mean(last 7 days)/mean(previous 7 days), clipped to 0.8–1.3, or 1.0 with < 14 days."""
    if days < 14:
        return 1.0
    last = clean[clean.index > end - pd.Timedelta(days=7)].mean()
    prev = clean[(clean.index > end - pd.Timedelta(days=14)) & (clean.index <= end - pd.Timedelta(days=7))].mean()
    if not np.isfinite(last) or not np.isfinite(prev) or prev <= 0:
        return 1.0
    return float(np.clip(last / prev, 0.8, 1.3))


def days_collected(hourly: pd.DataFrame) -> float:
    """Return how many days of hourly demand exist (first to last hour inclusive)."""
    if hourly.empty:
        return 0.0
    return ((hourly["ts"].max() - hourly["ts"].min()) / pd.Timedelta(hours=1) + 1) / 24.0


def plan_forecast(hourly: pd.DataFrame, now: pd.Timestamp, params: EngineParams, z: float, hours: int = 168) -> ForecastResult:
    """Forecast hourly demand for 7 days with an hour-of-week profile and trend, or report 'learning'."""
    now = utc(now)
    days = days_collected(hourly)
    if days < params.plan_min_days:
        return ForecastResult(_empty_points(), "hour_of_week", "learning",
                              f"Learning: {int(days)} of {params.plan_min_days} days collected")
    series = hourly.set_index("ts")["demand"].astype(float).sort_index()
    clean, anomalies = detect_anomalies(series)
    end = series.index.max()
    mean, std = _profile(clean[clean.index > end - pd.Timedelta(days=21)], days >= 14)
    ratio = _trend_ratio(clean, end, days)
    ts = pd.date_range(now.floor("h") + pd.Timedelta(hours=1), periods=hours, freq="h")
    how = _how(ts)
    expected = mean[how] * ratio
    band = z * std[how]
    points = pd.DataFrame({"ts": ts, "expected": expected, "low": np.maximum(0.0, expected - band), "high": expected + band})
    resource = str(hourly["resource"].iloc[-1]) if "resource" in hourly else "cpu"
    return ForecastResult(points, "hour_of_week", "ok", "Forecast ready", resource=resource, anomalies=anomalies)


def band_ratio(forecast: ForecastResult) -> float:
    """Return mean band width (high − low) divided by mean expected; inf when nothing is expected."""
    if not forecast.ok:
        return float("inf")
    expected = float(forecast.points["expected"].mean())
    width = float((forecast.points["high"] - forecast.points["low"]).mean())
    return width / expected if expected > 1e-9 else float("inf")
