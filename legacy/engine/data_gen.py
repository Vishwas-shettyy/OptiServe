"""Synthetic scenario generator (6 scenarios)."""

import zlib
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from engine import config


@dataclass
class Scenario:
    """One synthetic scenario with servers, metrics and events."""

    key: str
    title: str
    story: str
    servers: pd.DataFrame
    metrics: pd.DataFrame
    events: pd.DataFrame
    current_servers: dict[str, int] = field(default_factory=dict)


SERVER_COLUMNS = ["server_id", "name", "service", "instance_type", "monthly_cost", "capacity_rps"]
METRIC_COLUMNS = ["timestamp", "server_id", "service", "requests", "cpu_pct", "mem_pct", "error_rate"]
EVENT_COLUMNS = ["service", "start", "end", "multiplier", "label"]
ZOMBIE_SERVICE = "legacy"
ZOMBIE_COST = 5000.0


def _office_hours(ts: pd.DatetimeIndex) -> np.ndarray:
    """HR portal demand: busy weekday office hours, quiet nights and weekends."""
    hour = ts.hour.to_numpy()
    weekend = ts.day_of_week.to_numpy() >= 5
    base = np.full(len(ts), 300.0)
    base[(hour >= 9) & (hour <= 18)] = 6000.0
    base[(hour == 8) | (hour == 19)] = 3000.0
    base[weekend] = 400.0
    return base


def _flash_sale(ts: pd.DatetimeIndex) -> np.ndarray:
    """Shop demand: daytime sine curve, weekends x1.2."""
    hour = ts.hour.to_numpy()
    day = (hour >= 8) & (hour <= 23)
    base = np.where(day, 2500.0 + 2000.0 * np.sin(np.pi * (hour - 8) / 16), 800.0)
    return base * np.where(ts.day_of_week.to_numpy() >= 5, 1.2, 1.0)


def _analytics(ts: pd.DatetimeIndex) -> np.ndarray:
    """Analytics demand: daytime sine curve every day."""
    hour = ts.hour.to_numpy()
    day = (hour >= 6) & (hour <= 20)
    return np.where(day, 1500.0 + 2100.0 * np.sin(np.pi * (hour - 6) / 14), 900.0)


def _payments(ts: pd.DatetimeIndex) -> np.ndarray:
    """Payments demand: long daytime sine curve every day."""
    hour = ts.hour.to_numpy()
    day = (hour >= 7) & (hour <= 22)
    return np.where(day, 1200.0 + 2800.0 * np.sin(np.pi * (hour - 7) / 15), 1000.0)


def _growth(ts: pd.DatetimeIndex) -> np.ndarray:
    """App API demand: daytime sine curve, weekends x0.9, whole series growing 8% per week."""
    hour = ts.hour.to_numpy()
    day = (hour >= 8) & (hour <= 22)
    base = np.where(day, 1000.0 + 1800.0 * np.sin(np.pi * (hour - 8) / 14), 700.0)
    base = base * np.where(ts.day_of_week.to_numpy() >= 5, 0.9, 1.0)
    days = ((ts - pd.Timestamp(config.START)) // pd.Timedelta(days=1)).to_numpy()
    return base * 1.08 ** (days / 7.0)


def _night_batch(ts: pd.DatetimeIndex) -> np.ndarray:
    """Reports batch demand: heavy 01:00-04:59 every night, light the rest of the day."""
    hour = ts.hour.to_numpy()
    return np.where((hour >= 1) & (hour <= 4), 5500.0, 900.0)


SCENARIOS: dict[str, dict] = {
    "office_hours": {
        "title": "Office-hours HR portal",
        "story": "An HR portal that is busy only 9-to-7 on weekdays but runs 12 servers around the clock, "
        "plus two forgotten legacy boxes.",
        "services": [("hr-portal", "hr", 12, 7000.0, _office_hours)],
        "zombies": ["old-staging-1", "old-jenkins"],
        "events": [],
        "spikes": [],
        "sick": None,
    },
    "flash_sale": {
        "title": "Festive flash sale",
        "story": "An online shop with a big evening flash sale coming on Friday 20 Nov; a similar sale "
        "last week pushed traffic six-fold.",
        "services": [("shop-web", "shop", 10, 8000.0, _flash_sale)],
        "zombies": ["demo-2024"],
        "events": [
            ("shop-web", "2026-11-12 18:00", "2026-11-12 23:00", 6.0, "Past flash sale"),
            ("shop-web", "2026-11-20 18:00", "2026-11-20 23:00", 5.0, "Festive flash sale"),
        ],
        "spikes": [],
        "sick": None,
    },
    "forgotten_servers": {
        "title": "Forgotten servers",
        "story": "An analytics team whose cloud bill hides five servers nobody has touched in weeks.",
        "services": [("analytics", "an", 6, 6000.0, _analytics)],
        "zombies": ["old-staging-1", "old-staging-2", "test-db-replica", "demo-2024", "old-jenkins"],
        "events": [],
        "spikes": [],
        "sick": None,
    },
    "sick_server": {
        "title": "Payments API with a sick server",
        "story": "A payments API where one server is quietly leaking memory and throwing errors, "
        "and an unexplained traffic spike hit two weeks ago.",
        "services": [("payments-api", "pay", 8, 9000.0, _payments)],
        "zombies": [],
        "events": [],
        "spikes": [("payments-api", "2026-10-29 14:00", 4.0)],
        "sick": "pay-07",
    },
    "growth_startup": {
        "title": "Growing startup",
        "story": "A startup API whose traffic grows about 8% every week; today's 6 servers will not last "
        "the month.",
        "services": [("app-api", "app", 6, 7000.0, _growth)],
        "zombies": [],
        "events": [],
        "spikes": [],
        "sick": None,
    },
    "night_batch": {
        "title": "Nightly batch jobs",
        "story": "A reporting service that crunches batch jobs from 1 to 5 am and idles the rest of the day "
        "on 8 always-on servers.",
        "services": [("reports-batch", "rb", 8, 6000.0, _night_batch)],
        "zombies": [],
        "events": [],
        "spikes": [],
        "sick": None,
    },
}
# The first four scenarios keep their original index-based seeds so their data never changes;
# later scenarios derive their seed from SEED + their own key.
INDEX_SEEDED = ("office_hours", "flash_sale", "forgotten_servers", "sick_server")


def list_scenarios() -> list[tuple[str, str]]:
    """Return (key, title) for every scenario."""
    return [(key, spec["title"]) for key, spec in SCENARIOS.items()]


def scenario_seed(key: str) -> int | list[int]:
    """Return the RNG seed for a scenario: SEED + index for the original four, else [SEED, crc32(key)]."""
    if key in INDEX_SEEDED:
        return config.SEED + list(SCENARIOS).index(key)
    return [config.SEED, zlib.crc32(key.encode("utf-8"))]


def _timestamps() -> pd.DatetimeIndex:
    """Return the 672 hourly history timestamps."""
    return pd.date_range(config.START, periods=config.HISTORY_DAYS * 24, freq="h")


def _build_servers(spec: dict) -> pd.DataFrame:
    """Build the servers table for a scenario spec."""
    rows = []
    for service, prefix, count, cost, _ in spec["services"]:
        for i in range(1, count + 1):
            sid = f"{prefix}-{i:02d}"
            rows.append((sid, sid, service, "general-4vcpu", cost, config.CAPACITY_RPS))
    for name in spec["zombies"]:
        rows.append((name, name, ZOMBIE_SERVICE, "general-2vcpu", ZOMBIE_COST, config.CAPACITY_RPS))
    return pd.DataFrame(rows, columns=SERVER_COLUMNS)


def _build_events(spec: dict) -> pd.DataFrame:
    """Build the events table for a scenario spec."""
    rows = [(s, pd.Timestamp(a), pd.Timestamp(b), m, lbl) for s, a, b, m, lbl in spec["events"]]
    events = pd.DataFrame(rows, columns=EVENT_COLUMNS)
    events["start"] = pd.to_datetime(events["start"])
    events["end"] = pd.to_datetime(events["end"])
    events["multiplier"] = events["multiplier"].astype(float)
    return events


def _service_demand(
    ts: pd.DatetimeIndex, service: str, pattern: Callable, spec: dict, events: pd.DataFrame, rng: np.random.Generator
) -> np.ndarray:
    """Return noisy hourly demand for one service including past events and spikes."""
    demand = pattern(ts) * (1.0 + rng.normal(0.0, 0.08, len(ts)))
    demand = np.maximum(demand, 0.0)
    for ev in events[events["service"] == service].itertuples():
        mask = (ts >= ev.start) & (ts <= ev.end)
        demand[mask] *= ev.multiplier
    for svc, when, mult in spec["spikes"]:
        if svc == service:
            demand[ts == pd.Timestamp(when)] *= mult
    return demand


def _server_metrics(
    ts: pd.DatetimeIndex, sid: str, service: str, requests: np.ndarray, rng: np.random.Generator
) -> pd.DataFrame:
    """Return hourly metrics for one active server."""
    n = len(ts)
    cpu = np.clip(requests / config.CAPACITY_RPS * 100.0 * (1.0 + rng.normal(0.0, 0.05, n)) + 2.0, 0.0, 100.0)
    mem = np.clip(30.0 + 0.3 * cpu + rng.normal(0.0, 2.0, n), 0.0, 100.0)
    err = 0.002 + np.abs(rng.normal(0.0, 0.001, n))
    return pd.DataFrame(
        {"timestamp": ts, "server_id": sid, "service": service, "requests": requests,
         "cpu_pct": cpu, "mem_pct": mem, "error_rate": err}
    )


def _zombie_metrics(ts: pd.DatetimeIndex, sid: str, rng: np.random.Generator) -> pd.DataFrame:
    """Return hourly metrics for one idle zombie server."""
    n = len(ts)
    return pd.DataFrame(
        {"timestamp": ts, "server_id": sid, "service": ZOMBIE_SERVICE,
         "requests": rng.uniform(0.0, 5.0, n), "cpu_pct": rng.uniform(1.0, 4.0, n),
         "mem_pct": rng.uniform(10.0, 20.0, n), "error_rate": 0.002 + np.abs(rng.normal(0.0, 0.001, n))}
    )


def _make_sick(frame: pd.DataFrame) -> None:
    """Apply the memory leak (last 72h) and error burst (last 24h) to one server's metrics in place."""
    frame.loc[frame.index[-72:], "mem_pct"] = np.linspace(40.0, 96.0, 72)
    frame.loc[frame.index[-24:], "error_rate"] = 0.08


def load_scenario(key: str) -> Scenario:
    """Build the scenario identified by key."""
    if key not in SCENARIOS:
        raise KeyError(f"Unknown scenario: {key}")
    spec = SCENARIOS[key]
    rng = np.random.default_rng(scenario_seed(key))
    ts = _timestamps()
    servers = _build_servers(spec)
    events = _build_events(spec)
    frames = []
    current: dict[str, int] = {}
    for service, prefix, count, _, pattern in spec["services"]:
        demand = _service_demand(ts, service, pattern, spec, events, rng)
        per_server = demand / count
        current[service] = count
        for i in range(1, count + 1):
            sid = f"{prefix}-{i:02d}"
            frame = _server_metrics(ts, sid, service, per_server.copy(), rng)
            if sid == spec["sick"]:
                _make_sick(frame)
            frames.append(frame)
    for name in spec["zombies"]:
        frames.append(_zombie_metrics(ts, name, rng))
    metrics = pd.concat(frames, ignore_index=True)[METRIC_COLUMNS]
    return Scenario(key, spec["title"], spec["story"], servers, metrics, events, current)
