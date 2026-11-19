"""Turn a forecast into servers per hour and a recommendation."""

import math

import numpy as np
import pandas as pd

from engine import config


def needed_servers(forecast: pd.DataFrame, capacity_rps: float, target_util: float) -> pd.Series:
    """Return servers needed per forecast hour."""
    raise NotImplementedError


def build_plan(forecast: pd.DataFrame, current: int, capacity_rps: float, target_util: float) -> pd.DataFrame:
    """Build the raw hourly plan before guardrails."""
    raise NotImplementedError


def recommend(plan: pd.DataFrame, monthly_cost: float, current: int) -> dict:
    """Summarise a plan into a recommendation dict."""
    raise NotImplementedError
