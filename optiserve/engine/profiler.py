"""Server status and waste profiling."""

import numpy as np
import pandas as pd

from engine import config


def profile_servers(metrics: pd.DataFrame, servers: pd.DataFrame) -> pd.DataFrame:
    """Return one status row per server."""
    raise NotImplementedError


def waste_score(profile: pd.DataFrame) -> float:
    """Return wasted monthly cost as a percentage of total cost."""
    raise NotImplementedError
