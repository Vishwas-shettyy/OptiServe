"""AWS connector and /api/connections, against moto (never real AWS)."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlmodel import Session, select

from app.config import get_settings
from app.connectors import aws
from app.db import get_engine
from app.models import Connection, Group, MetricPoint, Server
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD

REGION = "ap-south-1"
SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"


@dataclass
class World:
    """Ids of the moto resources built for a test."""

    asg_instance: str
    lone_instance: str
    tg_arn: str
    lb_arn: str


@pytest.fixture
def mocked(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fake credentials and a moto AWS for the test; env changes are undone afterwards."""
    for key, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": REGION,
    }.items():
        monkeypatch.setenv(key, value)
    with mock_aws():
        yield


def _hour(now: datetime, hours_ago: int) -> datetime:
    """Return the start of the hour `hours_ago` hours before now."""
    return now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours_ago)


def build_world(hours: int = 48) -> World:
    """Create the demo layout in moto: a managed ASG behind an ALB, a lone idle instance, and CloudWatch data."""
    ec2 = boto3.client("ec2", region_name=REGION)
    asg = boto3.client("autoscaling", region_name=REGION)
    elb = boto3.client("elbv2", region_name=REGION)
    cw = boto3.client("cloudwatch", region_name=REGION)
    vpc_id = ec2.describe_vpcs()["Vpcs"][0]["VpcId"]
    subnets = [s["SubnetId"] for s in ec2.describe_subnets()["Subnets"]][:2]
    ami = ec2.describe_images()["Images"][0]["ImageId"]

    lone = ec2.run_instances(
        ImageId=ami,
        InstanceType="t3.micro",
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [{"Key": "Name", "Value": "forgotten-test-box"}, {"Key": "optiserve:managed", "Value": "true"}],
            }
        ],
    )["Instances"][0]["InstanceId"]

    lb_arn = elb.create_load_balancer(Name="optiserve-demo-alb", Subnets=subnets, Type="application")[
        "LoadBalancers"
    ][0]["LoadBalancerArn"]
    tg_arn = elb.create_target_group(Name="optiserve-demo-tg", Protocol="HTTP", Port=80, VpcId=vpc_id)[
        "TargetGroups"
    ][0]["TargetGroupArn"]
    elb.create_listener(
        LoadBalancerArn=lb_arn, Protocol="HTTP", Port=80, DefaultActions=[{"Type": "forward", "TargetGroupArn": tg_arn}]
    )
    ec2.create_launch_template(
        LaunchTemplateName="optiserve-demo", LaunchTemplateData={"ImageId": ami, "InstanceType": "t3.micro"}
    )
    asg.create_auto_scaling_group(
        AutoScalingGroupName="optiserve-demo",
        LaunchTemplate={"LaunchTemplateName": "optiserve-demo"},
        MinSize=1,
        MaxSize=3,
        DesiredCapacity=1,
        VPCZoneIdentifier=subnets[0],
        TargetGroupARNs=[tg_arn],
        Tags=[{"Key": "optiserve:managed", "Value": "true", "PropagateAtLaunch": True}],
    )
    asg_instance = asg.describe_auto_scaling_groups()["AutoScalingGroups"][0]["Instances"][0]["InstanceId"]

    now = datetime.now(timezone.utc)
    tg_dim = tg_arn.split(":")[-1]
    lb_dim = lb_arn.split(":loadbalancer/")[-1]
    for h in range(1, hours + 1):
        ts = _hour(now, h)
        for iid, cpu in ((asg_instance, 40.0), (lone, 1.0)):
            dims = [{"Name": "InstanceId", "Value": iid}]
            cw.put_metric_data(
                Namespace="AWS/EC2",
                MetricData=[
                    {"MetricName": "CPUUtilization", "Dimensions": dims, "Timestamp": ts, "Value": cpu},
                    {"MetricName": "NetworkIn", "Dimensions": dims, "Timestamp": ts, "Value": 450_000.0},
                    {"MetricName": "NetworkOut", "Dimensions": dims, "Timestamp": ts, "Value": 900_000.0},
                ],
            )
        cw.put_metric_data(
            Namespace="AWS/ApplicationELB",
            MetricData=[
                {
                    "MetricName": "RequestCountPerTarget",
                    "Dimensions": [{"Name": "TargetGroup", "Value": tg_dim}, {"Name": "LoadBalancer", "Value": lb_dim}],
                    "Timestamp": ts,
                    "Value": 1800.0,
                }
            ],
        )
    return World(asg_instance=asg_instance, lone_instance=lone, tg_arn=tg_arn, lb_arn=lb_arn)


def _login(client: TestClient) -> None:
    """Sign in as the admin."""
    assert client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).status_code == 200


def _connect(client: TestClient, **extra: Any) -> dict[str, Any]:
    """Connect AWS through the API and return the body."""
    _login(client)
    res = client.post("/api/connections/aws", json={"region": REGION, **extra})
    assert res.status_code == 201, res.text
    return res.json()


# ---------- connector functions ----------


def test_validate_and_list(mocked: None) -> None:
    """Credentials validate; instances and ASGs come back with state, tags, managed flag and membership."""
    world = build_world(hours=1)
    session = aws.make_session(REGION)
    assert aws.validate_credentials(session).account_id == "123456789012"
    instances = {i.instance_id: i for i in aws.list_instances(session)}
    assert instances[world.lone_instance].name == "forgotten-test-box"
    assert instances[world.lone_instance].managed and instances[world.lone_instance].state == "running"
    assert instances[world.lone_instance].instance_type == "t3.micro"
    (group,) = aws.list_asgs(session)
    assert (group.name, group.min_size, group.max_size, group.desired, group.managed) == ("optiserve-demo", 1, 3, 1, True)
    assert group.instance_ids == [world.asg_instance] and group.target_group_arns == [world.tg_arn]
    assert aws.target_group_dimensions(session, [world.tg_arn])[world.tg_arn][1].startswith("app/optiserve-demo-alb/")


def test_fetch_metrics_converts_units(mocked: None) -> None:
    """NetworkIn bytes/hour become kbps; RequestCountPerTarget per hour becomes per minute."""
    world = build_world(hours=3)
    session = aws.make_session(REGION)
    dims = aws.target_group_dimensions(session, [world.tg_arn])
    now = datetime.now(timezone.utc)
    data = aws.fetch_metrics(
        session, [world.asg_instance], now - timedelta(hours=4), now, 3600, {world.asg_instance: [dims[world.tg_arn]]}
    )
    sample = data[world.asg_instance][_hour(now, 2)]
    assert sample.cpu_pct == pytest.approx(40.0)
    assert sample.net_in_kbps == pytest.approx(450_000 * 8 / 1000 / 3600)
    assert sample.requests_per_min == pytest.approx(30.0)


def test_metrics_window(mocked: None) -> None:
    """First sync backfills 14 days hourly; later syncs are 5-min, or 1-min in live mode."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    conn = Connection(kind="aws", name="x", region=REGION)
    start, _, period, backfill = aws.metrics_window(conn, settings, now)
    assert (now - start, period, backfill) == (timedelta(days=14), 3600, True)
    conn.last_sync_at = now - timedelta(minutes=5)
    assert aws.metrics_window(conn, settings, now)[2:] == (300, False)
    assert aws.metrics_window(conn, settings.model_copy(update={"live_mode": True}), now)[2] == 60


def test_friendly_errors() -> None:
    """Access-denied and bad-key errors become plain words without secrets."""
    denied = ClientError({"Error": {"Code": "UnauthorizedOperation", "Message": "x"}}, "DescribeInstances")
    assert "iam_policy.json" in aws.friendly_error(denied)
    bad = ClientError({"Error": {"Code": "InvalidClientTokenId", "Message": SECRET}}, "GetCallerIdentity")
    assert SECRET not in aws.friendly_error(bad)


# ---------- API ----------


def test_connect_backfills_and_maps(client: TestClient, mocked: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Connecting stores keys only in the process env, backfills hourly history and maps groups/servers."""
    world = build_world(hours=48)
    body = _connect(client, access_key_id="AKIAIOSFODNN7EXAMPLE", secret_access_key=SECRET)
    assert body["connection"]["status"] == "ok" and body["connection"]["name"] == "AWS 123456789012"
    assert body["sync"]["backfill"] is True and body["sync"]["period_s"] == 3600
    assert body["sync"]["instances"] == 2 and body["sync"]["points_added"] == 96
    import os

    assert os.environ["AWS_SECRET_ACCESS_KEY"] == SECRET and "AWS_SESSION_TOKEN" not in os.environ
    db_url = get_settings().database_url.removeprefix("sqlite:///")
    with open(db_url, "rb") as fh:
        assert SECRET.encode() not in fh.read()

    with Session(get_engine()) as s:
        asg_server = s.exec(select(Server).where(Server.external_id == world.asg_instance)).one()
        group = s.get(Group, asg_server.group_id)
        assert group is not None and (group.asg_name, group.min_size, group.max_size, group.managed) == (
            "optiserve-demo", 1, 3, True,
        )
        lone = s.exec(select(Server).where(Server.external_id == world.lone_instance)).one()
        lone_group = s.get(Group, lone.group_id)
        assert lone.name == "forgotten-test-box" and lone_group is not None
        assert lone_group.asg_name is None and lone_group.managed and lone_group.min_size == 0
        point = s.exec(select(MetricPoint).where(MetricPoint.server_id == asg_server.id)).first()
        assert point is not None and point.requests_per_min == pytest.approx(30.0) and point.mem_pct is None
        assert asg_server.last_seen_at is not None

    listed = client.get("/api/connections").json()
    assert [c["kind"] for c in listed] == ["aws"]


def test_sync_is_incremental_and_idempotent(client: TestClient, mocked: None) -> None:
    """A second sync uses 5-minute periods and does not duplicate points already stored."""
    build_world(hours=3)
    conn_id = _connect(client)["connection"]["id"]
    with Session(get_engine()) as s:
        before = len(s.exec(select(MetricPoint)).all())
    res = client.post(f"/api/connections/{conn_id}/sync")
    assert res.status_code == 200, res.text
    assert res.json()["backfill"] is False and res.json()["period_s"] == 300
    with Session(get_engine()) as s:
        assert len(s.exec(select(MetricPoint)).all()) == before + res.json()["points_added"]
    again = client.post(f"/api/connections/{conn_id}/sync").json()
    assert again["points_added"] == 0


def test_agent_and_aws_merge_on_instance_id(client: TestClient, mocked: None) -> None:
    """An agent-created server with the EC2 instance id becomes the AWS record; agent samples (mem/disk) win."""
    world = build_world(hours=3)
    _login(client)
    token = client.post("/api/agent-tokens", json={"label": "ec2"}).json()["token"]
    now = datetime.now(timezone.utc)
    covered = aws.align(now, 300) - timedelta(minutes=5)  # last complete 5-min bucket: agent + AWS data
    uncovered = covered - timedelta(minutes=5)  # the bucket before: AWS data only
    agent = client.post(
        "/api/ingest",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "host": {"external_id": world.asg_instance, "name": "ip-10-0-0-5", "asg_name": "optiserve-demo"},
            "metrics": [
                {
                    "ts": (covered + timedelta(seconds=150)).isoformat(),
                    "cpu_pct": 41, "mem_pct": 63, "net_in_kbps": 1, "net_out_kbps": 1, "disk_pct": 30,
                }
            ],
        },
    ).json()
    conn_id = _connect(client)["connection"]["id"]
    cw = boto3.client("cloudwatch", region_name=REGION)
    for ts in (covered, uncovered):
        cw.put_metric_data(
            Namespace="AWS/EC2",
            MetricData=[
                {
                    "MetricName": "CPUUtilization",
                    "Dimensions": [{"Name": "InstanceId", "Value": world.asg_instance}],
                    "Timestamp": ts + timedelta(seconds=10),
                    "Value": 90.0,
                }
            ],
        )
    assert client.post(f"/api/connections/{conn_id}/sync").status_code == 200

    with Session(get_engine()) as s:
        servers = s.exec(select(Server).where(Server.external_id == world.asg_instance)).all()
        assert len(servers) == 1 and servers[0].id == agent["server_id"] and servers[0].provider == "aws"
        group = s.get(Group, servers[0].group_id)
        assert group is not None and group.asg_name == "optiserve-demo"
        points = s.exec(select(MetricPoint).where(MetricPoint.server_id == agent["server_id"])).all()

        def in_bucket(p: MetricPoint, start: datetime) -> bool:
            """True when the point falls in the 5-minute bucket starting at `start`."""
            ts = p.ts.replace(tzinfo=timezone.utc) if p.ts.tzinfo is None else p.ts
            return start <= ts < start + timedelta(minutes=5)

        assert [(p.cpu_pct, p.mem_pct) for p in points if in_bucket(p, covered)] == [(41, 63)]
        assert [(p.cpu_pct, p.mem_pct) for p in points if in_bucket(p, uncovered)] == [(90.0, None)]


def test_connect_bad_credentials(client: TestClient, mocked: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rejected credentials give 400 with a plain message, and nothing is saved."""

    def reject(_: Any) -> aws.Identity:
        """Simulate STS rejecting the keys."""
        raise aws.AwsError("AWS rejected these credentials. Check the access key and secret.")

    monkeypatch.setattr(aws, "validate_credentials", reject)
    _login(client)
    res = client.post(
        "/api/connections/aws", json={"region": REGION, "access_key_id": "AKIAIOSFODNN7EXAMPLE", "secret_access_key": SECRET}
    )
    assert res.status_code == 400 and "rejected" in res.json()["detail"]
    assert client.get("/api/connections").json() == []
    half = client.post("/api/connections/aws", json={"region": REGION, "access_key_id": "AKIAIOSFODNN7EXAMPLE"})
    assert half.status_code == 422


def test_sync_errors(client: TestClient, mocked: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing sync gives 502 and marks the connection as error; unknown and agent connections are refused."""
    build_world(hours=1)
    conn_id = _connect(client)["connection"]["id"]

    def denied(_: Any) -> list[aws.InstanceInfo]:
        """Simulate a missing EC2 permission."""
        raise ClientError({"Error": {"Code": "UnauthorizedOperation", "Message": "no"}}, "DescribeInstances")

    monkeypatch.setattr(aws, "list_instances", denied)
    res = client.post(f"/api/connections/{conn_id}/sync")
    assert res.status_code == 502 and "DescribeInstances" in res.json()["detail"]
    conn = client.get("/api/connections").json()[0]
    assert conn["status"] == "error" and "iam_policy.json" in conn["error_message"]
    assert client.post("/api/connections/999/sync").status_code == 404
    with Session(get_engine()) as s:
        s.add(Connection(kind="agent", name="OptiServe agent"))
        s.commit()
        agent_id = s.exec(select(Connection).where(Connection.kind == "agent")).one().id
    assert client.post(f"/api/connections/{agent_id}/sync").status_code == 400


def test_connections_require_admin(client: TestClient) -> None:
    """All connection routes need a session."""
    assert client.get("/api/connections").status_code == 401
    assert client.post("/api/connections/aws", json={"region": REGION}).status_code == 401
    assert client.post("/api/connections/1/sync").status_code == 401
