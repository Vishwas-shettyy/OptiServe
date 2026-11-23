"""Demo app (counter, real CPU work, routes) and load generator (plan, URL, percentiles)."""

import time

import pytest
from fastapi.testclient import TestClient

import app as demo_app
import loadgen


def test_counter_sliding_window() -> None:
    """Hits older than the window drop out; the rate is per minute."""
    c = demo_app.RequestCounter(window_s=30)
    for t in (0.0, 10.0, 20.0):
        c.hit(now=t)
    assert c.per_minute(now=25.0) == pytest.approx(6.0)
    assert c.per_minute(now=45.0) == pytest.approx(2.0)
    assert c.total == 3


def test_burn_takes_real_time() -> None:
    """burn(ms) keeps the CPU busy for about that long."""
    t0 = time.process_time()
    rounds = demo_app.burn(60)
    assert rounds > 0 and time.process_time() - t0 >= 0.05


def test_routes_count_requests() -> None:
    """/ and /work are counted; /metrics is not; /work validates ms."""
    with TestClient(demo_app.app) as client:
        before = client.get("/metrics").json()["requests_total"]
        assert "OptiServe demo app" in client.get("/").text
        body = client.get("/work", params={"ms": 20}).json()
        assert body["work_ms"] == 20 and body["took_ms"] >= 15 and body["rounds"] > 0
        assert client.get("/work", params={"ms": 0}).status_code == 422
        assert client.get("/work", params={"ms": 5000}).status_code == 422
        m = client.get("/metrics").json()
        assert m["requests_total"] - before == 4 and m["requests_per_min"] >= 4 and m["workers"] >= 1


def test_plan_ramps() -> None:
    """Linear ramp up, hold, ramp down; zero outside the run."""
    p = loadgen.Plan(rps=100, total_s=100, ramp_s=20)
    assert [p.rate(t) for t in (-1, 0, 10, 20, 50, 90, 100)] == [0, 0, 50, 100, 100, 50, 0]
    assert (p.phase(5), p.phase(50), p.phase(95)) == ("ramp up", "hold", "ramp down")
    short = loadgen.Plan(rps=10, total_s=10, ramp_s=60)
    assert short.rate(5) == pytest.approx(10)


def test_target_url_and_percentiles() -> None:
    """A bare base URL calls /work; full URLs are kept; bad URLs are refused."""
    assert loadgen.target_url("http://alb.example.com", 50) == "http://alb.example.com/work?ms=50"
    assert loadgen.target_url("http://h:8000/", 80) == "http://h:8000/work?ms=80"
    assert loadgen.target_url("http://h/work?ms=10", 50) == "http://h/work?ms=10"
    with pytest.raises(ValueError):
        loadgen.target_url("alb.example.com", 50)
    assert loadgen.percentile([], 50) is None
    assert loadgen.percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.0
    assert loadgen.percentile([1.0, 2.0, 3.0, 4.0], 95) == 4.0
