"""Home data: /api/groups (live fleet) and /api/forecast/weather, plus the pure weather engine."""

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.groups import clear_idle_cache
from app.db import get_engine
from app.engine.weather import classify, weather_slots
from app.models import Forecast, Group, MetricPoint, Server
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD


def _login(client: TestClient) -> None:
    """Sign in as the admin."""
    assert client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).status_code == 200


def _now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(timezone.utc)


def _points(s: Session, server_id: int, cpu: float, minutes: int, every_s: int = 30, end_ago_min: float = 0.0,
            net: float = 200.0, mem: float | None = 40.0) -> None:
    """Add evenly spaced samples ending `end_ago_min` minutes ago."""
    end = _now() - timedelta(minutes=end_ago_min)
    for i in range(int(minutes * 60 / every_s)):
        s.add(MetricPoint(server_id=server_id, ts=end - timedelta(seconds=every_s * i), cpu_pct=cpu,
                          mem_pct=mem, net_in_kbps=net, net_out_kbps=0.0))


def _seed_fleet() -> dict[str, int]:
    """One managed ASG with busy / normal / stale / stopped servers."""
    with Session(get_engine()) as s:
        g = Group(name="web", provider="aws", asg_name="web-asg", min_size=1, max_size=4, desired=3, managed=True)
        s.add(g)
        s.commit()
        s.refresh(g)
        names = {"busy": "running", "calm": "running", "stale": "running", "off": "stopped"}
        ids: dict[str, int] = {}
        for name, state in names.items():
            srv = Server(group_id=g.id, name=name, provider="aws", external_id=f"i-{name}", instance_type="t3.micro", state=state)
            s.add(srv)
            s.commit()
            s.refresh(srv)
            assert srv.id is not None
            ids[name] = srv.id
        _points(s, ids["busy"], 92.0, 12)
        _points(s, ids["calm"], 30.0, 12)
        _points(s, ids["stale"], 30.0, 5, end_ago_min=20)
        s.commit()
        return ids


def test_fleet_requires_admin(client: TestClient) -> None:
    """The fleet and the weather need a session."""
    assert client.get("/api/groups").status_code == 401
    assert client.get("/api/forecast/weather").status_code == 401


def test_fleet_tiles(client: TestClient) -> None:
    """Each server becomes a tile with the profiler's status, its load and its monthly cost."""
    clear_idle_cache()
    ids = _seed_fleet()
    _login(client)
    res = client.get("/api/groups")
    assert res.status_code == 200, res.text
    [group] = res.json()
    assert (group["name"], group["managed"], group["desired"]) == ("web", True, 3)
    tiles = {t["name"]: t for t in group["servers"]}
    assert tiles["busy"]["status"] == "busy" and tiles["busy"]["cpu_pct"] == pytest.approx(92.0)
    assert tiles["busy"]["mem_pct"] == pytest.approx(40.0)
    assert tiles["busy"]["monthly_cost_inr"] == pytest.approx(round(0.0104 * 83 * 730, 2))
    assert tiles["calm"]["status"] == "normal"
    assert tiles["stale"]["status"] == "unhealthy" and "no data" in tiles["stale"]["reason"]
    assert tiles["off"]["status"] == "stopped" and tiles["off"]["monthly_cost_inr"] is None
    assert tiles["busy"]["id"] == ids["busy"]


def test_fleet_idle_over_long_window(client: TestClient) -> None:
    """In normal mode a server quiet for the whole 7-day window is shown asleep."""
    clear_idle_cache()
    with Session(get_engine()) as s:
        srv = Server(name="sleepy", provider="agent", external_id="h-1", state="running")
        s.add(srv)
        s.commit()
        s.refresh(srv)
        assert srv.id is not None
        _points(s, srv.id, 1.0, 60 * 24 * 7 + 30, every_s=1800, net=2.0, mem=None)
        _points(s, srv.id, 1.0, 5, net=2.0, mem=None)
        s.commit()
    _login(client)
    [group] = client.get("/api/groups").json()
    assert group["name"] == "Ungrouped"
    [tile] = group["servers"]
    assert tile["status"] == "idle" and tile["mem_pct"] is None and tile["monthly_cost_inr"] is None


def test_weather_no_data(client: TestClient) -> None:
    """Without servers or forecasts the strip is empty with a plain reason."""
    _login(client)
    body = client.get("/api/forecast/weather").json()
    assert body["status"] == "no_data" and body["slots"] == [] and "nothing to forecast" in body["message"]


def _forecast(group_id: int, horizon: str, steps: int, step: timedelta, value: float) -> Forecast:
    """Build a stored forecast with a flat value starting now."""
    start = _now()
    pts = [{"ts": (start + step * i).isoformat(), "expected": value, "low": value * 0.8, "high": value * 1.1}
           for i in range(steps)]
    return Forecast(group_id=group_id, horizon=horizon, points_json=json.dumps(pts), method="test")


def test_weather_learning_uses_short_forecast(client: TestClient) -> None:
    """With under 7 days of history the strip shows the next 60 minutes and says OptiServe is learning."""
    _seed_fleet()
    with Session(get_engine()) as s:
        s.add(_forecast(1, "short", 61, timedelta(minutes=1), 2.7))
        s.commit()
    _login(client)
    body = client.get("/api/forecast/weather").json()
    assert body["horizon"] == "60 min" and body["status"] == "learning" and "0 of 7 days" in body["message"]
    assert body["capacity"] == 3 and len(body["slots"]) == 12
    assert {sl["kind"] for sl in body["slots"]} == {"storm"}


def test_weather_plan_gives_24h(client: TestClient) -> None:
    """A fresh plan forecast gives a 24-hour strip."""
    _seed_fleet()
    with Session(get_engine()) as s:
        s.add(_forecast(1, "plan", 30, timedelta(hours=1), 0.6))
        s.commit()
    _login(client)
    body = client.get("/api/forecast/weather").json()
    assert body["horizon"] == "24 h" and body["status"] == "ok" and body["message"] == ""
    assert len(body["slots"]) == 12 and {sl["kind"] for sl in body["slots"]} == {"sun"}


def test_classify_thresholds() -> None:
    """Sun when quiet, cloud in between, storm when busy or the band's top runs very hot."""
    assert classify(0.2, 0.3) == "sun"
    assert classify(0.5, 0.6) == "cloud"
    assert classify(0.8, 0.85) == "storm"
    assert classify(0.6, 0.95) == "storm"


def test_weather_slots_bucket_and_skip_gaps() -> None:
    """Slots use the peak inside each bucket and leave out buckets with no points."""
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    ts = [now + timedelta(minutes=m) for m in (0, 4, 10, 50)]
    pts = pd.DataFrame({"ts": ts, "expected": [1.0, 3.0, 1.0, 1.0], "low": [0.5] * 4, "high": [1.2, 3.2, 1.2, 1.2]})
    slots = weather_slots(pts, 4.0, now, timedelta(minutes=60))
    assert [s.start.minute for s in slots] == [0, 10, 50]
    assert slots[0].kind == "storm" and slots[0].expected_util == pytest.approx(0.75)
    assert slots[1].kind == "sun"
    assert weather_slots(pts, 0.0, now, timedelta(minutes=60)) == []
    later = weather_slots(pts, 4.0, now + timedelta(minutes=3), timedelta(minutes=60))
    assert later[0].start == now and later[0].kind == "storm"  # rounded down to a whole 5-minute step
