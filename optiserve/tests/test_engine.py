"""Engine tests."""

import importlib

import pandas as pd
import pytest

ENGINE_MODULES = [
    "config", "data_gen", "profiler", "forecaster", "planner",
    "guardrails", "backtest", "explainer", "pipeline",
]


def test_imports_and_risk_params() -> None:
    """All engine modules import; risk_params endpoints match presets."""
    for name in ENGINE_MODULES:
        importlib.import_module(f"engine.{name}")
    from engine.config import RISK_CHEAP, RISK_SAFE, risk_params
    assert risk_params(0) == pytest.approx(RISK_CHEAP)
    assert risk_params(1) == pytest.approx(RISK_SAFE)


from engine import data_gen
from engine.data_gen import list_scenarios, load_scenario

KEYS = [k for k, _ in list_scenarios()]


@pytest.mark.parametrize("key", KEYS)
def test_scenario_shape_and_columns(key: str) -> None:
    """Every server has 672 hourly timestamps and columns match section 3."""
    sc = load_scenario(key)
    assert list(sc.servers.columns) == data_gen.SERVER_COLUMNS
    assert list(sc.metrics.columns) == data_gen.METRIC_COLUMNS
    assert list(sc.events.columns) == data_gen.EVENT_COLUMNS
    counts = sc.metrics.groupby("server_id")["timestamp"].nunique()
    assert set(counts.index) == set(sc.servers["server_id"])
    assert (counts == 672).all()
    ts = sc.metrics["timestamp"].drop_duplicates().sort_values()
    assert (ts.diff().dropna() == pd.Timedelta(hours=1)).all()
    assert ts.iloc[0] == pd.Timestamp("2026-10-19 00:00")
    assert ts.iloc[-1] == pd.Timestamp("2026-11-15 23:00")


def test_current_servers() -> None:
    """current_servers counts non-zombie servers per active service."""
    assert load_scenario("office_hours").current_servers == {"hr-portal": 12}
    assert load_scenario("sick_server").current_servers == {"payments-api": 8}


def test_flash_sale_events() -> None:
    """Flash sale has both past and future sales as events."""
    ev = load_scenario("flash_sale").events
    starts = set(ev["start"])
    assert pd.Timestamp("2026-11-12 18:00") in starts
    assert pd.Timestamp("2026-11-20 18:00") in starts
    assert sorted(ev["multiplier"]) == [5.0, 6.0]


def test_sick_server_memory_and_spike() -> None:
    """pay-07 leaks memory above 90% in the last 24h; spike exists."""
    m = load_scenario("sick_server").metrics
    last = m["timestamp"].max() - pd.Timedelta(hours=23)
    pay7 = m[(m["server_id"] == "pay-07") & (m["timestamp"] >= last)]
    assert pay7["mem_pct"].max() > 90
    assert (pay7["error_rate"] == 0.08).all()
    pay1 = m[m["server_id"] == "pay-01"].set_index("timestamp")["requests"]
    spike = pay1[pd.Timestamp("2026-10-29 14:00")]
    assert spike > 3 * pay1[pd.Timestamp("2026-10-22 14:00")]


@pytest.mark.parametrize("key", ["office_hours", "flash_sale", "forgotten_servers"])
def test_zombie_cpu_low(key: str) -> None:
    """Zombie servers never exceed 5% CPU."""
    m = load_scenario(key).metrics
    assert (m.loc[m["service"] == "legacy", "cpu_pct"] < 5).all()


@pytest.mark.parametrize("key", KEYS)
def test_deterministic(key: str) -> None:
    """Two loads give identical data."""
    a, b = load_scenario(key), load_scenario(key)
    pd.testing.assert_frame_equal(a.metrics, b.metrics)
    pd.testing.assert_frame_equal(a.servers, b.servers)
    pd.testing.assert_frame_equal(a.events, b.events)
    assert a.current_servers == b.current_servers
