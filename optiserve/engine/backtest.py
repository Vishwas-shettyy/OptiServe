"""Time machine: backtest the planner on the last history week."""

import numpy as np
import pandas as pd

from engine import config


def run_backtest(
    history: pd.DataFrame,
    events: pd.DataFrame,
    current: int,
    capacity_rps: float,
    monthly_cost: float,
    risk: float,
) -> dict:
    """Compare planned vs fixed capacity on the held-out week."""
    raise NotImplementedError
