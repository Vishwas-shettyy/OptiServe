"""Safety rules on plans and alert building."""

import numpy as np
import pandas as pd

from engine import config


def apply_guardrails(
    plan: pd.DataFrame,
    forecast: pd.DataFrame,
    profile_service: pd.DataFrame,
    history_days: int,
    current: int,
) -> tuple[pd.DataFrame, list[dict]]:
    """Apply safety rules in order and report each one."""
    raise NotImplementedError


def build_alerts(profile: pd.DataFrame, services_results: dict) -> list[dict]:
    """Build sorted critical/warning/info alerts."""
    raise NotImplementedError
