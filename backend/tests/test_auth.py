"""Tests for health, login, logout and protected routes."""

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.auth import COOKIE_NAME
from app.db import get_engine
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD


def test_health_ok(client: TestClient) -> None:
    """Health returns ok with mode flags."""
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["dry_run"] is True


def test_tables_created_on_startup(client: TestClient) -> None:
    """All §4 tables exist after startup."""
    tables = set(inspect(get_engine()).get_table_names())
    expected = {"connection", "group", "server", "metricpoint", "forecast", "recommendation", "actionlog", "agenttoken"}
    assert expected <= tables


def test_login_ok_sets_httponly_cookie(client: TestClient) -> None:
    """Correct credentials sign in and set an httpOnly cookie."""
    res = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert res.status_code == 200
    assert res.json() == {"email": ADMIN_EMAIL}
    set_cookie = res.headers["set-cookie"]
    assert COOKIE_NAME in set_cookie and "HttpOnly" in set_cookie


def test_login_wrong_password(client: TestClient) -> None:
    """A wrong password is rejected without a cookie."""
    res = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "nope"})
    assert res.status_code == 401
    assert "set-cookie" not in res.headers


def test_login_wrong_email(client: TestClient) -> None:
    """An unknown email is rejected."""
    res = client.post("/api/auth/login", json={"email": "other@test.local", "password": ADMIN_PASSWORD})
    assert res.status_code == 401


def test_me_requires_auth(client: TestClient) -> None:
    """The protected route returns 401 without a session."""
    assert client.get("/api/auth/me").status_code == 401


def test_me_rejects_forged_token(client: TestClient) -> None:
    """A token signed with another secret is rejected."""
    client.cookies.set(COOKIE_NAME, "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.bad")
    assert client.get("/api/auth/me").status_code == 401


def test_me_after_login_and_logout(client: TestClient) -> None:
    """After login /me works; after logout it is 401 again."""
    client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["email"] == ADMIN_EMAIL
    assert client.post("/api/auth/logout").json() == {"ok": True}
    assert client.get("/api/auth/me").status_code == 401
