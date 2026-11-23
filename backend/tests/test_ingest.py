"""Agent tokens and /api/ingest: auth, validation, rate limit and server upsert."""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import get_engine
from app.models import AgentToken, Connection, Group, MetricPoint, Server
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD


def _login(client: TestClient) -> None:
    """Sign in as the admin."""
    assert client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).status_code == 200


def _new_token(client: TestClient, label: str = "laptop") -> dict[str, Any]:
    """Create an agent token through the API and return the response body."""
    _login(client)
    res = client.post("/api/agent-tokens", json={"label": label})
    assert res.status_code == 201
    return res.json()


def _payload(external_id: str = "host-a", name: str = "host-a", n: int = 1, **host: Any) -> dict[str, Any]:
    """Build an ingest body with n recent samples."""
    now = datetime.now(timezone.utc)
    metrics = [
        {
            "ts": (now - timedelta(seconds=10 * (n - i))).isoformat(),
            "cpu_pct": 12.5 + i,
            "mem_pct": 40.0,
            "net_in_kbps": 3.2,
            "net_out_kbps": 1.1,
            "disk_pct": 55.0,
            "requests_per_min": 30.0,
        }
        for i in range(n)
    ]
    return {"host": {"external_id": external_id, "name": name, **host}, "metrics": metrics}


def _auth(token: str) -> dict[str, str]:
    """Return a Bearer header."""
    return {"Authorization": f"Bearer {token}"}


def test_token_crud_requires_admin_and_stores_hash(client: TestClient) -> None:
    """Token routes need a session; only the hash is stored; revoke works."""
    assert client.get("/api/agent-tokens").status_code == 401
    created = _new_token(client)
    assert created["token"].startswith("osa_") and created["revoked"] is False
    listed = client.get("/api/agent-tokens").json()
    assert [t["id"] for t in listed] == [created["id"]] and "token" not in listed[0]
    with Session(get_engine()) as s:
        assert created["token"] not in s.exec(select(AgentToken)).one().token_hash
    assert client.delete(f"/api/agent-tokens/{created['id']}").json()["revoked"] is True
    assert client.delete("/api/agent-tokens/9999").status_code == 404


def test_ingest_happy_path(client: TestClient) -> None:
    """A valid token stores samples, creates the server in Ungrouped and marks it seen."""
    token = _new_token(client)["token"]
    res = client.post("/api/ingest", json=_payload(n=3), headers=_auth(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["accepted"] == 3
    with Session(get_engine()) as s:
        server = s.get(Server, body["server_id"])
        assert server is not None and server.provider == "agent" and server.state == "running"
        assert server.last_seen_at is not None
        group = s.get(Group, body["group_id"])
        assert group is not None and group.name == "Ungrouped"
        assert len(s.exec(select(MetricPoint).where(MetricPoint.server_id == server.id)).all()) == 3
        assert s.exec(select(Connection).where(Connection.kind == "agent")).one().status == "ok"


def test_ingest_bad_token(client: TestClient) -> None:
    """Missing, unknown and revoked tokens are rejected with 401."""
    assert client.post("/api/ingest", json=_payload()).status_code == 401
    assert client.post("/api/ingest", json=_payload(), headers=_auth("osa_nope")).status_code == 401
    created = _new_token(client)
    client.delete(f"/api/agent-tokens/{created['id']}")
    assert client.post("/api/ingest", json=_payload(), headers=_auth(created["token"])).status_code == 401


def test_ingest_validation(client: TestClient) -> None:
    """Out-of-range values and stale timestamps are rejected with 422."""
    token = _new_token(client)["token"]
    bad = _payload()
    bad["metrics"][0]["cpu_pct"] = 140
    assert client.post("/api/ingest", json=bad, headers=_auth(token)).status_code == 422
    stale = _payload()
    stale["metrics"][0]["ts"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert client.post("/api/ingest", json=stale, headers=_auth(token)).status_code == 422
    assert client.post("/api/ingest", json={"host": _payload()["host"], "metrics": []}, headers=_auth(token)).status_code == 422


def test_ingest_rate_limit(client: TestClient) -> None:
    """Past the per-minute limit a token gets 429 with Retry-After; other tokens are unaffected."""
    first = _new_token(client, "a")["token"]
    second = _new_token(client, "b")["token"]
    for _ in range(30):
        assert client.post("/api/ingest", json=_payload(), headers=_auth(first)).status_code == 200
    limited = client.post("/api/ingest", json=_payload(), headers=_auth(first))
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1
    assert client.post("/api/ingest", json=_payload(), headers=_auth(second)).status_code == 200


def test_ingest_upserts_server(client: TestClient) -> None:
    """The same external_id updates one server; an existing AWS record is linked, not duplicated."""
    token = _new_token(client)["token"]
    first = client.post("/api/ingest", json=_payload(name="old-name"), headers=_auth(token)).json()
    second = client.post(
        "/api/ingest", json=_payload(name="new-name", instance_type="t3.micro", region="ap-south-1"), headers=_auth(token)
    ).json()
    assert first["server_id"] == second["server_id"]
    with Session(get_engine()) as s:
        asg = Group(name="optiserve-demo", provider="aws", asg_name="optiserve-demo", min_size=1, max_size=3, desired=1)
        s.add(asg)
        s.commit()
        s.refresh(asg)
        asg_id = asg.id
        s.add(Server(group_id=asg_id, name="web-1", provider="aws", external_id="i-0abc", state="running"))
        s.commit()
    linked = client.post("/api/ingest", json=_payload(external_id="i-0abc", name="ip-10-0-0-5"), headers=_auth(token)).json()
    with Session(get_engine()) as s:
        servers = s.exec(select(Server)).all()
        assert len(servers) == 2
        renamed = s.get(Server, first["server_id"])
        assert renamed is not None and renamed.name == "new-name" and renamed.instance_type == "t3.micro"
        aws = s.get(Server, linked["server_id"])
        assert aws is not None and aws.provider == "aws" and aws.name == "web-1" and aws.group_id == asg_id
