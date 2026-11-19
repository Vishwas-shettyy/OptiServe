"""All OptiServe constants and risk helpers."""

CURRENCY = "₹"
HOURS_PER_MONTH = 730
SEED = 42
START = "2026-10-19 00:00"      # Monday
HISTORY_DAYS = 28                # 2026-10-19 .. 2026-11-15 23:00
FORECAST_HOURS = 168             # 2026-11-16 00:00 .. 2026-11-22 23:00
TRAIN_DAYS = 21                  # backtest: train first 21 days, test last 7
CAPACITY_RPS = 1000.0
MIN_SERVERS = 2
MAX_STEP_DOWN = 2                # max servers removed per hour
PREWARM_HOURS = 2                # capacity ready this many hours before demand
MIN_HISTORY_DAYS = 7
LOW_CONFIDENCE_RATIO = 1.0       # mean((high-low)/expected) above this -> hold
ZOMBIE_CPU_P95 = 5.0
ZOMBIE_DAYS = 14
WASTEFUL_AVG_CPU = 25.0
HOT_CPU_P95 = 85.0
UNHEALTHY_MEM = 90.0
UNHEALTHY_ERROR = 0.05
OVERPROV_UTIL = 0.30
TARGET_CPU_FOR_WASTE = 65.0
RISK_CHEAP = {"target_util": 0.85, "z": 0.5}
RISK_SAFE = {"target_util": 0.55, "z": 2.0}
DEFAULT_RISK = 0.5


def risk_params(risk: float) -> dict:
    """Linearly interpolate RISK_CHEAP (risk=0) to RISK_SAFE (risk=1)."""
    r = min(max(float(risk), 0.0), 1.0)
    return {k: RISK_CHEAP[k] + (RISK_SAFE[k] - RISK_CHEAP[k]) * r for k in RISK_CHEAP}


def risk_label(risk: float) -> str:
    """Return the human label for a risk setting."""
    if risk < 0.34:
        return "Cheapest"
    if risk < 0.67:
        return "Balanced"
    return "Safest"
