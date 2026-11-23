"""AWS connector: the only module (with actions/aws_actions.py) that calls AWS.

Read-only: STS identity, EC2 instances + status checks, Auto Scaling groups, ELBv2 target groups,
CloudWatch GetMetricData. Maps the results onto Connection / Group / Server / MetricPoint.
"""

import bisect
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, PartialCredentialsError
from pydantic import BaseModel
from sqlmodel import Session, select

from app.config import Settings
from app.models import Connection, Group, MetricPoint, Server, utcnow

log = logging.getLogger(__name__)

MANAGED_TAG = "optiserve:managed"
ASG_TAG = "aws:autoscaling:groupName"
BACKFILL = timedelta(days=14)
BACKFILL_PERIOD_S = 3600
LIVE_PERIOD_S = 60
NORMAL_PERIOD_S = 300
MAX_QUERIES_PER_CALL = 500
LIVE_STATES = ["pending", "running", "stopping", "stopped"]


class AwsError(Exception):
    """An AWS failure with a plain-words message safe to show in the UI."""


# ---------- data shapes ----------


@dataclass
class Identity:
    """Who the credentials belong to."""

    account_id: str
    arn: str


@dataclass
class InstanceInfo:
    """One EC2 instance as OptiServe needs it."""

    instance_id: str
    name: str
    state: str  # running | stopped | unknown
    instance_type: str
    tags: dict[str, str]
    managed: bool
    asg_name: Optional[str] = None
    status_ok: Optional[bool] = None  # False = a status check is impaired; None = not known yet


@dataclass
class AsgInfo:
    """One Auto Scaling group."""

    name: str
    min_size: int
    max_size: int
    desired: int
    instance_ids: list[str]
    managed: bool
    target_group_arns: list[str] = field(default_factory=list)


@dataclass
class Sample:
    """One CloudWatch bucket for an instance."""

    cpu_pct: Optional[float] = None
    net_in_kbps: float = 0.0
    net_out_kbps: float = 0.0
    requests_per_min: Optional[float] = None


class SyncResult(BaseModel):
    """Summary of one sync run."""

    connection_id: int
    instances: int
    groups: int
    points_added: int
    period_s: int
    backfill: bool
    impaired: list[str]


# ---------- helpers ----------


def _naive_utc(value: datetime) -> datetime:
    """Return a naive UTC datetime (what SQLite stores) for comparisons."""
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def align(value: datetime, period: int) -> datetime:
    """Round a UTC datetime down to a multiple of `period` seconds (CloudWatch buckets start there)."""
    value = value.astimezone(timezone.utc)
    epoch = int(value.timestamp())
    return datetime.fromtimestamp(epoch - epoch % period, tz=timezone.utc)


def _tags(raw: Optional[list[dict[str, str]]]) -> dict[str, str]:
    """Turn AWS [{Key, Value}] tags into a dict."""
    return {t["Key"]: t.get("Value", "") for t in raw or []}


def _is_managed(tags: dict[str, str]) -> bool:
    """True when the resource carries optiserve:managed=true."""
    return tags.get(MANAGED_TAG, "").strip().lower() == "true"


def friendly_error(exc: Exception) -> str:
    """Translate a boto error into plain words without leaking credentials."""
    if isinstance(exc, (NoCredentialsError, PartialCredentialsError)):
        return "No AWS credentials found. Add access keys or run the backend with an IAM role."
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        op = exc.operation_name
        if code in {"InvalidClientTokenId", "SignatureDoesNotMatch", "AuthFailure", "UnrecognizedClientException"}:
            return "AWS rejected these credentials. Check the access key and secret."
        if code in {"ExpiredToken", "ExpiredTokenException", "RequestExpired"}:
            return "The AWS credentials have expired. Add fresh ones."
        if code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}:
            return f"The AWS credentials are not allowed to call {op}. Attach the policy in demo/iam_policy.json."
        return f"AWS returned an error ({code}) for {op}."
    return f"Could not reach AWS ({type(exc).__name__})."


def make_session(
    region: str,
    access_key_id: Optional[str] = None,
    secret_access_key: Optional[str] = None,
    session_token: Optional[str] = None,
) -> boto3.Session:
    """Create a boto3 session; without keys it uses the environment or the instance's IAM role."""
    return boto3.Session(
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        aws_session_token=session_token,
        region_name=region,
    )


def set_process_credentials(access_key_id: str, secret_access_key: str, session_token: Optional[str]) -> None:
    """Keep keys in this process's environment only (never in the database or logs)."""
    os.environ["AWS_ACCESS_KEY_ID"] = access_key_id
    os.environ["AWS_SECRET_ACCESS_KEY"] = secret_access_key
    if session_token:
        os.environ["AWS_SESSION_TOKEN"] = session_token
    else:
        os.environ.pop("AWS_SESSION_TOKEN", None)


# ---------- read calls ----------


def validate_credentials(session: boto3.Session) -> Identity:
    """Call sts:GetCallerIdentity; raise AwsError if the credentials do not work."""
    try:
        res = session.client("sts").get_caller_identity()
    except (ClientError, BotoCoreError) as exc:
        raise AwsError(friendly_error(exc)) from exc
    return Identity(account_id=res["Account"], arn=res["Arn"])


def _status_checks(session: boto3.Session) -> dict[str, Optional[bool]]:
    """Return instance-id → status-checks-ok (None while initializing or unknown)."""
    ec2 = session.client("ec2")
    out: dict[str, Optional[bool]] = {}
    for page in ec2.get_paginator("describe_instance_status").paginate(IncludeAllInstances=True):
        for st in page.get("InstanceStatuses", []):
            checks = [st.get("InstanceStatus", {}).get("Status"), st.get("SystemStatus", {}).get("Status")]
            if "impaired" in checks:
                out[st["InstanceId"]] = False
            elif all(c == "ok" for c in checks):
                out[st["InstanceId"]] = True
            else:
                out[st["InstanceId"]] = None
    return out


def list_instances(session: boto3.Session) -> list[InstanceInfo]:
    """List non-terminated EC2 instances with state, type, tags and status checks."""
    ec2 = session.client("ec2")
    status = _status_checks(session)
    out: list[InstanceInfo] = []
    pages = ec2.get_paginator("describe_instances").paginate(
        Filters=[{"Name": "instance-state-name", "Values": LIVE_STATES}]
    )
    for page in pages:
        for reservation in page.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                tags = _tags(inst.get("Tags"))
                raw_state = inst.get("State", {}).get("Name", "")
                state = {"running": "running", "stopped": "stopped", "stopping": "stopped"}.get(raw_state, "unknown")
                out.append(
                    InstanceInfo(
                        instance_id=inst["InstanceId"],
                        name=tags.get("Name") or inst["InstanceId"],
                        state=state,
                        instance_type=inst.get("InstanceType", ""),
                        tags=tags,
                        managed=_is_managed(tags),
                        asg_name=tags.get(ASG_TAG),
                        status_ok=status.get(inst["InstanceId"]),
                    )
                )
    return out


def list_asgs(session: boto3.Session) -> list[AsgInfo]:
    """List Auto Scaling groups with sizes, instances, managed tag and target groups."""
    client = session.client("autoscaling")
    out: list[AsgInfo] = []
    for page in client.get_paginator("describe_auto_scaling_groups").paginate():
        for g in page.get("AutoScalingGroups", []):
            out.append(
                AsgInfo(
                    name=g["AutoScalingGroupName"],
                    min_size=g["MinSize"],
                    max_size=g["MaxSize"],
                    desired=g["DesiredCapacity"],
                    instance_ids=[i["InstanceId"] for i in g.get("Instances", [])],
                    managed=_is_managed(_tags(g.get("Tags"))),
                    target_group_arns=list(g.get("TargetGroupARNs", [])),
                )
            )
    return out


def discover(session: boto3.Session) -> tuple[list[InstanceInfo], list[AsgInfo]]:
    """List instances and Auto Scaling groups; raise AwsError with a plain message if AWS refuses."""
    try:
        return list_instances(session), list_asgs(session)
    except (ClientError, BotoCoreError) as exc:
        raise AwsError(friendly_error(exc)) from exc


def target_group_dimensions(session: boto3.Session, arns: list[str]) -> dict[str, tuple[str, str]]:
    """Map target-group ARN → (TargetGroup, LoadBalancer) CloudWatch dimension values; skip unattached ones."""
    if not arns:
        return {}
    client = session.client("elbv2")
    out: dict[str, tuple[str, str]] = {}
    for i in range(0, len(arns), 20):
        res = client.describe_target_groups(TargetGroupArns=arns[i : i + 20])
        for tg in res.get("TargetGroups", []):
            lbs = tg.get("LoadBalancerArns", [])
            if lbs:
                tg_dim = tg["TargetGroupArn"].split(":")[-1]
                lb_dim = lbs[0].split(":loadbalancer/")[-1]
                out[tg["TargetGroupArn"]] = (tg_dim, lb_dim)
    return out


def _query(qid: str, namespace: str, metric: str, dims: list[dict[str, str]], period: int, stat: str) -> dict[str, Any]:
    """Build one GetMetricData query."""
    return {
        "Id": qid,
        "MetricStat": {
            "Metric": {"Namespace": namespace, "MetricName": metric, "Dimensions": dims},
            "Period": period,
            "Stat": stat,
        },
        "ReturnData": True,
    }


def _run_queries(
    session: boto3.Session, queries: list[dict[str, Any]], start: datetime, end: datetime
) -> dict[str, list[tuple[datetime, float]]]:
    """Run GetMetricData in chunks of 500 queries, following NextToken; return id → [(ts, value)]."""
    cw = session.client("cloudwatch")
    out: dict[str, list[tuple[datetime, float]]] = {}
    for i in range(0, len(queries), MAX_QUERIES_PER_CALL):
        chunk = queries[i : i + MAX_QUERIES_PER_CALL]
        pages = cw.get_paginator("get_metric_data").paginate(
            MetricDataQueries=chunk, StartTime=start, EndTime=end, ScanBy="TimestampAscending"
        )
        for page in pages:
            for r in page.get("MetricDataResults", []):
                pairs = zip(r.get("Timestamps", []), r.get("Values", []))
                out.setdefault(r["Id"], []).extend((ts.astimezone(timezone.utc), v) for ts, v in pairs)
    return out


def fetch_metrics(
    session: boto3.Session,
    instance_ids: list[str],
    start: datetime,
    end: datetime,
    period: int,
    instance_target_groups: Optional[dict[str, list[tuple[str, str]]]] = None,
) -> dict[str, dict[datetime, Sample]]:
    """Fetch CPU, network and (if any) ALB requests per target; return instance → bucket ts → Sample."""
    queries: list[dict[str, Any]] = []
    for n, iid in enumerate(instance_ids):
        dims = [{"Name": "InstanceId", "Value": iid}]
        queries.append(_query(f"cpu{n}", "AWS/EC2", "CPUUtilization", dims, period, "Average"))
        queries.append(_query(f"nin{n}", "AWS/EC2", "NetworkIn", dims, period, "Sum"))
        queries.append(_query(f"nout{n}", "AWS/EC2", "NetworkOut", dims, period, "Sum"))
    tg_ids: dict[tuple[str, str], str] = {}
    for tgs in (instance_target_groups or {}).values():
        for dims_pair in tgs:
            if dims_pair not in tg_ids:
                qid = f"req{len(tg_ids)}"
                tg_ids[dims_pair] = qid
                tg_dims = [{"Name": "TargetGroup", "Value": dims_pair[0]}, {"Name": "LoadBalancer", "Value": dims_pair[1]}]
                queries.append(_query(qid, "AWS/ApplicationELB", "RequestCountPerTarget", tg_dims, period, "Sum"))
    if not queries:
        return {}
    # Aligned windows give whole buckets only; the current, still-filling bucket is left for the next sync.
    raw = _run_queries(session, queries, align(start, period), align(end, period))
    kbps = 8 / 1000 / period  # bytes per period → kilobits per second
    per_min = 60 / period
    out: dict[str, dict[datetime, Sample]] = {}
    for n, iid in enumerate(instance_ids):
        buckets: dict[datetime, Sample] = {}
        for ts, v in raw.get(f"cpu{n}", []):
            buckets.setdefault(ts, Sample()).cpu_pct = float(v)
        for ts, v in raw.get(f"nin{n}", []):
            buckets.setdefault(ts, Sample()).net_in_kbps = float(v) * kbps
        for ts, v in raw.get(f"nout{n}", []):
            buckets.setdefault(ts, Sample()).net_out_kbps = float(v) * kbps
        for dims_pair in (instance_target_groups or {}).get(iid, []):
            for ts, v in raw.get(tg_ids[dims_pair], []):
                s = buckets.setdefault(ts, Sample())
                s.requests_per_min = (s.requests_per_min or 0.0) + float(v) * per_min
        out[iid] = buckets
    return out


# ---------- mapping to the database ----------


def _upsert_asg_group(db: Session, asg: AsgInfo) -> Group:
    """Create or refresh the Group for an Auto Scaling group."""
    group = db.exec(select(Group).where(Group.asg_name == asg.name)).first()
    if group is None:
        group = Group(name=asg.name, provider="aws", asg_name=asg.name)
    group.provider = "aws"
    group.min_size, group.max_size, group.desired = asg.min_size, asg.max_size, asg.desired
    group.managed = asg.managed
    db.add(group)
    db.flush()
    return group


def _lone_group(db: Session, server: Server, inst: InstanceInfo) -> Group:
    """Return the single-instance Group for an EC2 instance outside any Auto Scaling group."""
    group = db.get(Group, server.group_id) if server.group_id else None
    if group is None or group.provider != "aws" or group.asg_name is not None:
        group = Group(name=inst.name, provider="aws", asg_name=None)
    group.name = inst.name
    group.min_size, group.max_size = 0, 1
    group.desired = 1 if inst.state == "running" else 0
    group.managed = inst.managed
    db.add(group)
    db.flush()
    return group


def _upsert_server(db: Session, inst: InstanceInfo, region: str) -> Server:
    """Find the server by instance id (it may already exist from the agent) and refresh AWS fields."""
    server = db.exec(select(Server).where(Server.external_id == inst.instance_id)).first()
    if server is None:
        server = Server(name=inst.name, provider="aws", external_id=inst.instance_id)
    server.provider = "aws"  # an agent-created record for this instance becomes the AWS record (merge)
    if "Name" in inst.tags or not server.name:
        server.name = inst.name
    server.instance_type = inst.instance_type
    server.region = region
    server.state = inst.state
    return server


def _insert_points(
    db: Session, server: Server, samples: dict[datetime, Sample], period: int, start: datetime, end: datetime
) -> int:
    """Insert AWS buckets that no existing sample covers; agent samples (with mem/disk) win when both exist."""
    assert server.id is not None
    lo, hi = _naive_utc(start), _naive_utc(end) + timedelta(seconds=period)
    existing = sorted(
        _naive_utc(ts)
        for ts in db.exec(
            select(MetricPoint.ts).where(
                MetricPoint.server_id == server.id,
                MetricPoint.ts >= lo.replace(tzinfo=timezone.utc),
                MetricPoint.ts < hi.replace(tzinfo=timezone.utc),
            )
        ).all()
    )
    added = 0
    latest: Optional[datetime] = None
    for ts, s in sorted(samples.items()):
        if s.cpu_pct is None:
            continue
        bucket = _naive_utc(ts)
        i = bisect.bisect_left(existing, bucket)
        if i < len(existing) and existing[i] < bucket + timedelta(seconds=period):
            continue
        db.add(
            MetricPoint(
                server_id=server.id,
                ts=bucket.replace(tzinfo=timezone.utc),
                cpu_pct=max(0.0, min(100.0, s.cpu_pct)),
                net_in_kbps=s.net_in_kbps,
                net_out_kbps=s.net_out_kbps,
                requests_per_min=s.requests_per_min,
            )
        )
        bisect.insort(existing, bucket)
        added += 1
        latest = bucket
    if latest is not None:
        seen = _naive_utc(server.last_seen_at) if server.last_seen_at else None
        if seen is None or latest > seen:
            server.last_seen_at = latest.replace(tzinfo=timezone.utc)
            db.add(server)
    return added


def metrics_window(conn: Connection, settings: Settings, now: datetime) -> tuple[datetime, datetime, int, bool]:
    """Return (start, end, period_s, is_backfill): 14 days hourly first, then 1-min (live) / 5-min increments."""
    if conn.last_sync_at is None:
        return now - BACKFILL, now, BACKFILL_PERIOD_S, True
    last = _naive_utc(conn.last_sync_at).replace(tzinfo=timezone.utc)
    period = LIVE_PERIOD_S if settings.live_mode else NORMAL_PERIOD_S
    if now - last > timedelta(days=1):
        period = BACKFILL_PERIOD_S  # long gap: fill it hourly
    start = max(now - BACKFILL, last - timedelta(seconds=3 * period))  # overlap catches late datapoints
    return start, now, period, False


def sync_connection(
    db: Session,
    conn: Connection,
    settings: Settings,
    now: Optional[datetime] = None,
    session: Optional[boto3.Session] = None,
) -> SyncResult:
    """Pull inventory and metrics for one AWS connection into the database; record errors on the connection."""
    assert conn.id is not None and conn.kind == "aws"
    now = now or utcnow()
    region = conn.region or settings.aws_region
    try:
        session = session or make_session(region)
        instances = list_instances(session)
        asgs = list_asgs(session)
        all_tgs = sorted({arn for a in asgs for arn in a.target_group_arns})
        try:
            tg_dims = target_group_dimensions(session, all_tgs)
        except (ClientError, BotoCoreError) as exc:
            log.warning("skipping ALB request counts: %s", friendly_error(exc))
            tg_dims = {}

        asg_groups = {a.name: _upsert_asg_group(db, a) for a in asgs}
        asg_of = {iid: a for a in asgs for iid in a.instance_ids}
        servers: dict[str, Server] = {}
        for inst in instances:
            server = _upsert_server(db, inst, region)
            asg = asg_of.get(inst.instance_id) or next((a for a in asgs if a.name == inst.asg_name), None)
            group = asg_groups[asg.name] if asg else _lone_group(db, server, inst)
            server.group_id = group.id
            db.add(server)
            servers[inst.instance_id] = server
        db.flush()

        seen = set(servers)
        stale = db.exec(select(Server).where(Server.provider == "aws", Server.region == region)).all()
        for s in stale:
            if s.external_id not in seen:
                s.state = "unknown"
                db.add(s)

        start, end, period, backfill = metrics_window(conn, settings, now)
        inst_tgs = {
            iid: [tg_dims[arn] for arn in asg_of[iid].target_group_arns if arn in tg_dims]
            for iid in servers
            if iid in asg_of
        }
        data = fetch_metrics(session, list(servers), start, end, period, inst_tgs)
        added = sum(_insert_points(db, servers[iid], data.get(iid, {}), period, start, end) for iid in servers)

        conn.status, conn.error_message, conn.last_sync_at = "ok", None, now
        db.add(conn)
        db.commit()
    except (ClientError, BotoCoreError) as exc:
        db.rollback()
        message = friendly_error(exc)
        conn.status, conn.error_message = "error", message
        db.add(conn)
        db.commit()
        raise AwsError(message) from exc
    return SyncResult(
        connection_id=conn.id,
        instances=len(instances),
        groups=len({s.group_id for s in servers.values()}),
        points_added=added,
        period_s=period,
        backfill=backfill,
        impaired=sorted(i.instance_id for i in instances if i.status_ok is False),
    )
