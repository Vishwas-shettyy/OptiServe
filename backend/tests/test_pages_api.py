"""Servers list/detail/price, settings, connection removal and the action mini-chart."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.api.groups import clear_idle_cache
from app.api.settings import apply_stored
from app.config import Settings, get_settings
from app.db import get_engine
from app.models import ActionLog, AppSetting, Connection, Group, MetricPoint, Recommendation, Server
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD


def _login(client: TestClient) -> None:
    """Sign in as the admin."""
    assert client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).status_code == 200


def _now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(timezone.utc)


def _seed(minutes: int = 70, region: str = "ap-south-1") -> dict[str, int]:
    """A managed ASG with two AWS servers reporting every minute, plus an AWS connection."""
    clear_idle_cache()
    with Session(get_engine()) as s:
        s.add(Connection(kind="aws", name="AWS 1", region=region))
        g = Group(name="web", provider="aws", asg_name="web-asg", min_size=1, max_size=3, desired=2, managed=True)
        s.add(g)
        s.commit()
        s.refresh(g)
        ids = {}
        for name, cpu in (("web-1", 60.0), ("web-2", 40.0)):
            srv = Server(group_id=g.id, name=name, provider="aws", external_id=f"i-{name}", region=region,
                         instance_type="t3.micro", state="running")
            s.add(srv)
            s.commit()
            s.refresh(srv)
            assert srv.id is not None
            ids[name] = srv.id
            for m in range(minutes):
                s.add(MetricPoint(server_id=srv.id, ts=_now() - timedelta(minutes=m), cpu_pct=cpu + (m % 3),
                                  net_in_kbps=100.0, net_out_kbps=10.0))
        assert g.id is not None
        ids["group"] = g.id
        s.commit()
        return ids


def test_new_routes_require_admin(client: TestClient) -> None:
    """Every new route needs a session."""
    for method, path in (("GET", "/api/servers"), ("GET", "/api/servers/1"), ("PUT", "/api/servers/1/price"),
                         ("GET", "/api/settings"), ("PUT", "/api/settings"), ("DELETE", "/api/connections/1"),
                         ("GET", "/api/actions/1/chart")):
        assert client.request(method, path, json={}).status_code == 401, path


def test_servers_list_and_price_override(client: TestClient) -> None:
    """Rows carry group, managed flag and price source; an override replaces the table price and can be cleared."""
    ids = _seed()
    _login(client)
    rows = {r["name"]: r for r in client.get("/api/servers").json()}
    web1 = rows["web-1"]
    assert web1["group_name"] == "web" and web1["managed"] is True and web1["status"] == "normal"
    assert web1["price_source"] == "table" and web1["hourly_usd"] == pytest.approx(0.0104)
    res = client.put(f"/api/servers/{ids['web-1']}/price", json={"hourly_usd": 0.05})
    assert res.status_code == 200
    assert res.json()["price_source"] == "override" and res.json()["monthly_cost_inr"] == pytest.approx(0.05 * 83 * 730)
    cleared = client.put(f"/api/servers/{ids['web-1']}/price", json={"hourly_usd": None}).json()
    assert cleared["price_source"] == "table"
    assert client.put("/api/servers/999/price", json={"hourly_usd": 1}).status_code == 404
    assert client.put(f"/api/servers/{ids['web-1']}/price", json={"hourly_usd": -1}).status_code == 422


def test_server_detail(client: TestClient) -> None:
    """Detail has the chart (measured + forecast), plain sentences, nine safety checks and the open suggestion."""
    ids = _seed()
    with Session(get_engine()) as s:
        s.add(Recommendation(group_id=ids["group"], kind="hold", from_count=2, to_count=2, reason="Wait.", status="pending"))
        s.commit()
    _login(client)
    res = client.get(f"/api/servers/{ids['web-1']}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["capacity"] == 2 and body["target_util_pct"] == 70
    measured = [p for p in body["chart"] if p["load"] is not None]
    future = [p for p in body["chart"] if p["expected"] is not None]
    assert len(measured) >= 55 and len(future) == 60
    assert all(p["server"] is None or 0.5 <= p["server"] <= 0.7 for p in measured)
    sees = " ".join(body["sees"])
    assert "AWS doesn't report memory" in sees and "group web is" in sees and "peak at" in sees
    assert "waits for 24 hours" in sees
    assert [c["number"] for c in body["safety"]] == list(range(1, 10))
    assert body["recommendation"]["reason"] == "Wait."
    assert client.get("/api/servers/999").status_code == 404


def test_settings_change_persist_and_reload(client: TestClient) -> None:
    """Changes apply at once, are recorded with who made them, and come back after a restart."""
    _login(client)
    first = client.get("/api/settings").json()
    assert (first["risk"], first["live_mode"], first["dry_run"], first["target_util_pct"]) == (0.5, False, True, 70)
    res = client.put("/api/settings", json={"risk": 1.0, "live_mode": True})
    assert res.status_code == 200
    body = res.json()
    assert body["risk"] == 1.0 and body["live_mode"] is True and body["target_util_pct"] == 55
    assert body["updated_by"] == ADMIN_EMAIL
    assert get_settings().live_mode is True and client.get("/api/health").json()["live_mode"] is True
    assert client.put("/api/settings", json={"risk": 2}).status_code == 422
    fresh = Settings(live_mode=False, risk=0.5)
    with Session(get_engine()) as s:
        apply_stored(s, fresh)
        assert {r.key for r in s.exec(select(AppSetting)).all()} == {"risk", "live_mode"}
    assert fresh.live_mode is True and fresh.risk == 1.0 and fresh.dry_run is True


def test_remove_connection(client: TestClient) -> None:
    """Removing an AWS connection drops its servers and metrics; the agent connection can't be removed."""
    ids = _seed(minutes=5)
    with Session(get_engine()) as s:
        agent = Connection(kind="agent", name="Agent")
        s.add(agent)
        s.commit()
        s.refresh(agent)
        aws_id = s.exec(select(Connection).where(Connection.kind == "aws")).one().id
        s.add(Recommendation(group_id=ids["group"], kind="scale_down", from_count=2, to_count=1, reason="x", status="pending"))
        s.commit()
        agent_id = agent.id
    _login(client)
    assert client.delete(f"/api/connections/{agent_id}").status_code == 400
    res = client.delete(f"/api/connections/{aws_id}")
    assert res.status_code == 200 and res.json()["servers_removed"] == 2
    assert client.delete(f"/api/connections/{aws_id}").status_code == 404
    with Session(get_engine()) as s:
        assert s.exec(select(Server)).all() == [] and s.exec(select(MetricPoint)).all() == []
        assert s.exec(select(Recommendation)).one().status == "expired"
        assert s.get(Group, ids["group"]) is not None  # kept: its suggestion is part of the history
    assert client.get("/api/servers").json() == []


def test_action_chart(client: TestClient) -> None:
    """The mini-chart covers 30 minutes before the change up to now, in 5-minute steps."""
    ids = _seed(minutes=40)
    with Session(get_engine()) as s:
        rec = Recommendation(group_id=ids["group"], kind="scale_down", from_count=2, to_count=1, reason="x", status="done")
        s.add(rec)
        s.commit()
        s.refresh(rec)
        assert rec.id is not None
        action = ActionLog(recommendation_id=rec.id, approved_by=ADMIN_EMAIL, approved_at=_now() - timedelta(minutes=10),
                           executed_at=_now() - timedelta(minutes=10), result="done")
        s.add(action)
        s.commit()
        s.refresh(action)
        action_id = action.id
    _login(client)
    body = client.get(f"/api/actions/{action_id}/chart").json()
    assert body["before_servers"] == 2 and body["after_servers"] == 1
    assert 7 <= len(body["points"]) <= 9 and all(0.9 <= p["load"] <= 1.1 for p in body["points"])
    assert client.get("/api/actions/999/chart").status_code == 404
