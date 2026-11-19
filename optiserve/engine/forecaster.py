"""Demand forecasting, anomaly detection and naive baseline."""

import numpy as np
import pandas as pd

from engine import config


def service_demand(metrics: pd.DataFrame, servers: pd.DataFrame) -> pd.DataFrame:
    """Aggregate hourly demand per service, excluding zombies."""
    raise NotImplementedError


def detect_anomalies(series: pd.Series, event_mask: pd.Series) -> tuple[pd.Series, list[dict]]:
    """Replace hour-of-week outliers with the median and list them."""
    raise NotImplementedError


def forecast_service(
    history: pd.DataFrame,
    events: pd.DataFrame,
    start: pd.Timestamp,
    hours: int = 168,
    z: float = 1.25,
) -> tuple[pd.DataFrame, list[dict]]:
    """Forecast hourly demand with low/high bands and event multipliers."""
    raise NotImplementedError


def naive_forecast(history: pd.DataFrame, start: pd.Timestamp, hours: int) -> pd.Series:
    """Forecast each hour as the value one week earlier."""
    raise NotImplementedError


def wape(actual: pd.Series, forecast: pd.Series) -> float:
    """Return weighted absolute percentage error."""
    raise NotImplementedError
