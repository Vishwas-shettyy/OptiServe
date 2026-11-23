"""Approval, execution and verification against moto (never real AWS), plus the jobs and APIs around them."""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import boto3
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlmodel import Session, select

from app.actions import aws_actions, executor
from app.config import get_settings
from app.connectors import aws
from app.db import get_engine
from app.jobs import engine_run, scheduler
from app.models import ActionLog, Forecast, Group, MetricPoint, Recommendation, Server
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD
from tests.fixtures.engine_data import NOW, server_metrics

REGION = "ap-south-1"
ASG = "optiserve-demo"


@pytest.fixture
def mocked(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fake credentials and a moto AWS for the test."""
    for key, value in {"AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
                       "AWS_SESSION_TOKEN": "testing", "AWS_DEFAULT_REGION": REGION}.items():
        monkeypatch.setenv(key, value)
    with mock_aws():
        yield


@dataclass
class Setup:
    """Database ids and the AWS instance used by a test."""

    group_id: int
    server_id: int
    instance_id: str
    now: datetime


def _now() -> datetime:
    """Return the current UTC time rounded down to the minute."""
    return datetime.now(timezone.utc).replace(second=0, microsecond=0)


def make_asg(managed: bool = True, desired: int = 1) -> list[str]:
    """Create a moto Auto Scaling group (min 1, max 3); return its instance ids."""
    ec2 = boto3.client("ec2", region_name=REGION)
    asg = boto3.client("autoscaling", region_name=REGION)
    subnet = ec2.describe_subnets()["Subnets"][0]["SubnetId"]
    ami = ec2.describe_images()["Images"][0]["ImageId"]
    ec2.create_launch_template(LaunchTemplateName=ASG, LaunchTemplateData={"ImageId": ami, "InstanceType": "t3.micro"})
    tags = [{"Key": "optiserve:managed", "Value": "true", "PropagateAtLaunch": True}] if managed else []
    asg.create_auto_scaling_group(
        AutoScalingGroupName=ASG, LaunchTemplate={"LaunchTemplateName": ASG}, MinSize=1, MaxSize=3,
        DesiredCapacity=desired, VPCZoneIdentifier=subnet, Tags=tags,
    )
    return [i["InstanceId"] for i in asg.describe_auto_scaling_groups()["AutoScalingGroups"][0]["Instances"]]


def desired_capacity() -> int:
    """Return the moto ASG's desired capacity."""
    return boto3.client("autoscaling", region_name=REGION).describe_auto_scaling_groups(
        AutoScalingGroupNames=[ASG])["AutoScalingGroups"][0]["DesiredCapacity"]


def add_metrics(db: Session, server_id: int, df: pd.DataFrame, now: datetime) -> None:
    """Insert fixture rows for a server, shifted so the fixture's NOW is `now`."""
    shift = pd.Timestamp(now) - NOW
    for row in df.assign(ts=df["ts"] + shift).itertuples():
        db.add(MetricPoint(server_id=server_id, ts=row.ts.to_pydatetime(), cpu_pct=float(row.cpu_pct),
                           mem_pct=float(row.mem_pct), net_in_kbps=float(row.net_in_kbps),
                           net_out_kbps=float(row.net_out_kbps)))


def rising(ago: np.ndarray) -> np.ndarray:
    """40% CPU for a day, then climbing to 62% over the last hour."""
    return np.where(ago > 60, 40.0, 40.0 + 22.0 * (60 - ago) / 60)


def build(managed: bool = True, provider: str = "aws") -> Setup:
    """Create a 1-server managed ASG in moto and the matching rows with 26 h of rising load."""
    (instance,) = make_asg(managed)
    now = _now()
    with Session(get_engine()) as db:
        group = Group(name=ASG, provider=provider, asg_name=ASG if provider == "aws" else None,
                      min_size=1, max_size=3, desired=1, managed=managed)
        db.add(group)
        db.flush()
        server = Server(group_id=group.id, name="web-1", provider=provider, external_id=instance, region=REGION,
                        instance_type="t3.micro", state="running")
        db.add(server)
        db.flush()
        assert group.id is not None and server.id is not None
        add_metrics(db, server.id, server_metrics(1, pd.Timedelta(hours=26), rising), now)
        db.commit()
        return Setup(group.id, server.id, instance, now)


def engine_once(now: datetime) -> list[Recommendation]:
    """Run the engine job once."""
    with Session(get_engine()) as db:
        recs = engine_run.run_engine(db, get_settings(), now)
        for r in recs:
            db.expunge(r)
        return recs


def login(client: TestClient) -> None:
    """Sign in as the admin."""
    assert client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).status_code == 200


def set_env(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    """Change settings for the rest of the test."""
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()


def scale_up_rec(client: TestClient, s: Setup) -> dict:
    """Run the engine and return the pending scale-up card from the API."""
    engine_once(s.now)
    login(client)
    cards = client.get("/api/recommendations").json()
    assert len(cards) == 1, cards
    card = cards[0]
    assert (card["kind"], card["from_count"], card["to_count"], card["status"]) == ("scale_up", 1, 2, "pending"), card
    return card


# ---------- the four required scenarios ----------


def test_approve_changes_desired_capacity(client: TestClient, mocked: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Approve with DRY_RUN=false → SetDesiredCapacity runs, verify_actions sees it finish and logs who approved."""
    set_env(monkeypatch, DRY_RUN="false")
    s = build()
    card = scale_up_rec(client, s)
    assert card["can_execute"] and "minutes" in card["reason"]

    res = client.post(f"/api/recommendations/{card['id']}/approve")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["recommendation"]["status"] == "executing"
    assert body["action"]["approved_by"] == ADMIN_EMAIL
    assert body["action"]["details"]["called"]["call"] == "autoscaling:SetDesiredCapacity"
    assert desired_capacity() == 2

    assert scheduler.verify_actions(get_settings()) == 1
    (action,) = client.get("/api/actions").json()
    assert (action["result"], action["status"], action["kind"]) == ("done", "done", "scale_up")
    assert action["details"]["seen"] == {"desired": 2, "in_service": 2}
    with Session(get_engine()) as db:
        assert db.get(Group, s.group_id).desired == 2  # type: ignore[union-attr]


def test_dry_run_changes_nothing_in_aws(client: TestClient, mocked: None) -> None:
    """DRY_RUN=true (default) → logged as dry_run with the call it would make; ASG untouched."""
    s = build()
    card = scale_up_rec(client, s)
    body = client.post(f"/api/recommendations/{card['id']}/approve").json()
    assert body["action"]["result"] == "dry_run"
    assert body["action"]["details"]["would_call"] == {
        "call": "autoscaling:SetDesiredCapacity", "asg_name": ASG, "from": 1, "to": 2}
    assert body["recommendation"]["status"] == "done"
    assert desired_capacity() == 1


def test_blocked_at_execution_makes_no_call(client: TestClient, mocked: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """A change made after the suggestion trips the cooldown → status blocked, no AWS write call."""
    set_env(monkeypatch, DRY_RUN="false")
    s = build()
    card = scale_up_rec(client, s)
    with Session(get_engine()) as db:  # someone else's change on this group just ran
        old = Recommendation(group_id=s.group_id, kind="scale_up", from_count=1, to_count=1, reason="x", status="done")
        db.add(old)
        db.flush()
        assert old.id is not None
        db.add(ActionLog(recommendation_id=old.id, approved_by=ADMIN_EMAIL, executed_at=datetime.now(timezone.utc),
                         finished_at=datetime.now(timezone.utc), result="done"))
        db.commit()

    def boom(*_: object, **__: object) -> None:
        """Fail the test if AWS is called."""
        raise AssertionError("AWS write call made")

    monkeypatch.setattr(aws_actions, "set_desired_capacity", boom)
    monkeypatch.setattr(aws_actions, "stop_instance", boom)
    body = client.post(f"/api/recommendations/{card['id']}/approve").json()
    assert body["recommendation"]["status"] == "blocked"
    assert "Waiting" in body["recommendation"]["blocked_reason"]
    assert body["action"]["details"]["outcome"] == "blocked" and body["action"]["executed_at"] is None
    assert desired_capacity() == 1


def test_unmanaged_group_is_refused(client: TestClient, mocked: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without optiserve:managed=true the card is recommendation-only and approving is refused."""
    set_env(monkeypatch, DRY_RUN="false")
    s = build(managed=False)
    card = scale_up_rec(client, s)
    assert not card["can_execute"] and "optiserve:managed" in card["recommendation_only_reason"]
    res = client.post(f"/api/recommendations/{card['id']}/approve")
    assert res.status_code == 409 and "recommendation only" in res.json()["detail"]
    assert client.get("/api/actions").json() == []
    assert desired_capacity() == 1


def test_agent_group_is_refused(client: TestClient, mocked: None) -> None:
    """Agent-only servers: recommendation only, never executed."""
    s = build(provider="agent")
    card = scale_up_rec(client, s)
    res = client.post(f"/api/recommendations/{card['id']}/approve")
    assert res.status_code == 409 and "agent" in res.json()["detail"]


# ---------- AWS calls ----------


def test_stop_instance_in_asg_uses_standby_and_never_terminates(mocked: None) -> None:
    """stop_idle on an ASG member: standby (desired −1) then StopInstances; the instance still exists."""
    ids = make_asg(desired=2)
    session = aws.make_session(REGION)
    aws_actions.stop_instance(session, ids[0], ASG)
    assert aws_actions.instance_state(session, ids[0])[0] == "stopped"
    assert desired_capacity() == 1


def test_set_desired_capacity_refuses_unmanaged(mocked: None) -> None:
    """The AWS layer itself refuses groups without the managed tag."""
    make_asg(managed=False)
    with pytest.raises(aws.AwsError, match="not tagged"):
        aws_actions.set_desired_capacity(aws.make_session(REGION), ASG, 2)
    assert desired_capacity() == 1


# ---------- recommendation upsert / expiry / reject ----------


def test_upsert_keeps_one_card_and_expires(client: TestClient, mocked: None) -> None:
    """Same suggestion a minute later keeps its id; it expires 15 min after the last refresh; forecasts are stored."""
    s = build()
    (first,) = engine_once(s.now)
    (again,) = engine_once(s.now + timedelta(seconds=30))
    assert again.id == first.id
    with Session(get_engine()) as db:
        assert len(db.exec(select(Recommendation)).all()) == 1
        assert len(db.exec(select(Forecast).where(Forecast.horizon == "short")).all()) == 2
        assert engine_run.expire_stale(db, s.now + timedelta(minutes=16)) == 1
        db.commit()
        assert db.get(Recommendation, first.id).status == "expired"  # type: ignore[union-attr]


def test_reject_snoozes_the_same_suggestion(client: TestClient, mocked: None) -> None:
    """'Not now' hides the card and the engine does not bring the same change back right away."""
    s = build()
    card = scale_up_rec(client, s)
    assert client.post(f"/api/recommendations/{card['id']}/reject").json()["status"] == "rejected"
    assert engine_once(s.now + timedelta(seconds=30)) == []
    assert client.get("/api/recommendations").json() == []
    assert len(client.get("/api/recommendations?status=all").json()) == 1
    assert client.post(f"/api/recommendations/{card['id']}/approve").status_code == 409


def test_verify_times_out(client: TestClient, mocked: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """An executing action that never finishes is marked failed after 10 minutes."""
    set_env(monkeypatch, DRY_RUN="false")
    s = build()
    card = scale_up_rec(client, s)
    client.post(f"/api/recommendations/{card['id']}/approve")
    monkeypatch.setattr(aws_actions, "capacity_status",
                        lambda *_: aws_actions.CapacityStatus(2, 1, 1, 3, True))
    later = datetime.now(timezone.utc) + timedelta(minutes=11)
    assert scheduler.verify_actions(get_settings(), later) == 1
    (action,) = client.get("/api/actions").json()
    assert action["result"] == "failed" and "10 minutes" in action["details"]["message"]


# ---------- realized savings and stats ----------


def test_realized_savings_and_stats(client: TestClient, mocked: None) -> None:
    """A finished scale-down saves removed servers × hours × price; /api/stats reports it with the other numbers."""
    s = build()
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        rec = Recommendation(group_id=s.group_id, kind="scale_down", from_count=2, to_count=1, reason="x", status="done")
        db.add(rec)
        db.flush()
        assert rec.id is not None
        db.add(ActionLog(recommendation_id=rec.id, approved_by=ADMIN_EMAIL, executed_at=now - timedelta(hours=10),
                         finished_at=now - timedelta(hours=10), result="done"))
        db.add(Recommendation(group_id=s.group_id, kind="stop_idle", from_count=2, to_count=1, reason="y",
                              savings_month_inr=631.0, status="pending"))
        db.commit()
        total = executor.refresh_realized_savings(db, get_settings(), now)
    assert total == pytest.approx(0.0104 * 83.0 * 1 * 10, abs=0.01)

    login(client)
    stats = client.get("/api/stats").json()
    assert stats["servers"] == 1 and stats["servers_without_price"] == 0
    assert stats["avg_busy_pct"] == pytest.approx(60, abs=4)
    assert stats["monthly_cost_inr"] == pytest.approx(0.0104 * 83.0 * 730, abs=0.01)
    assert stats["potential_savings_inr"] == 631.0
    assert stats["realized_savings_inr"] == pytest.approx(total)
    assert stats["accuracy_pct"] is None and stats["dry_run"] is True


def test_accuracy_scores_stored_forecasts(client: TestClient, mocked: None) -> None:
    """After forecasts and later actuals exist, accuracy is 100 − WAPE on real matches."""
    s = build()
    past = s.now - timedelta(minutes=30)
    engine_once(past)
    result = scheduler.score_accuracy(s.now)
    assert result["points"] > 0 and 50 <= result["accuracy_pct"] <= 100


def test_downsample_averages_old_rows(client: TestClient) -> None:
    """Raw rows older than 14 days become one 5-minute average per bucket."""
    now = _now()
    old = now - timedelta(days=15)
    with Session(get_engine()) as db:
        g = Group(name="g", provider="agent")
        db.add(g)
        db.flush()
        srv = Server(group_id=g.id, name="a", provider="agent", external_id="h1", state="running")
        db.add(srv)
        db.flush()
        assert srv.id is not None
        base = old.replace(minute=0)
        for i, cpu in enumerate([10.0, 20.0, 30.0, 40.0, 50.0]):
            db.add(MetricPoint(server_id=srv.id, ts=base + timedelta(minutes=i), cpu_pct=cpu))
        db.add(MetricPoint(server_id=srv.id, ts=now, cpu_pct=5.0))
        db.commit()
    assert scheduler.downsample(now) == 4
    with Session(get_engine()) as db:
        rows = db.exec(select(MetricPoint).order_by(MetricPoint.ts)).all()
        assert [r.cpu_pct for r in rows] == [30.0, 5.0]


def test_scheduler_has_all_jobs_and_live_intervals() -> None:
    """All six §6 jobs are registered; AWS sync runs every minute in live mode."""
    settings = get_settings()
    live = settings.model_copy(update={"live_mode": True})
    assert scheduler.job_intervals(settings)["sync_aws"] == timedelta(minutes=5)
    assert scheduler.job_intervals(live)["sync_aws"] == timedelta(minutes=1)
    ids = {j.id for j in scheduler.build_scheduler(settings).get_jobs()}
    assert ids == {"sync_aws", "run_engine", "plan_forecast", "verify_actions", "score_accuracy", "downsample"}


def test_routes_require_login(client: TestClient) -> None:
    """The new routes are admin-only."""
    for path in ("/api/recommendations", "/api/actions", "/api/stats"):
        assert client.get(path).status_code == 401
    assert client.post("/api/recommendations/1/approve").status_code == 401


def test_details_json_is_valid(client: TestClient, mocked: None) -> None:
    """Action details are stored as JSON."""
    s = build()
    card = scale_up_rec(client, s)
    client.post(f"/api/recommendations/{card['id']}/approve")
    with Session(get_engine()) as db:
        (row,) = db.exec(select(ActionLog)).all()
        assert json.loads(row.details_json)["outcome"] == "dry_run"
