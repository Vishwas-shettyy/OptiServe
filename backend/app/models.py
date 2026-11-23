"""Database tables (CLAUDE.md §4). All timestamps are UTC."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Index, Text
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(timezone.utc)


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Return an aware UTC datetime (SQLite hands back naive UTC values)."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class Connection(SQLModel, table=True):
    """A data source: the OptiServe agent or an AWS account. AWS keys are never stored here."""

    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = Field(index=True)  # agent | aws
    name: str
    region: Optional[str] = None
    status: str = "ok"  # ok | error
    last_sync_at: Optional[datetime] = None
    error_message: Optional[str] = None


class Group(SQLModel, table=True):
    """A set of servers scaled together (an Auto Scaling group or an agent group)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    provider: str  # agent | aws
    asg_name: Optional[str] = Field(default=None, index=True, unique=True)
    min_size: int = 1
    max_size: int = 1
    desired: int = 1
    managed: bool = False  # has tag optiserve:managed=true


class Server(SQLModel, table=True):
    """One machine reporting metrics."""

    __table_args__ = (Index("ix_server_provider_external", "provider", "external_id", unique=True),)

    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: Optional[int] = Field(default=None, foreign_key="group.id", index=True)
    name: str
    provider: str  # agent | aws
    external_id: str  # EC2 instance id or agent host id
    region: Optional[str] = None
    instance_type: Optional[str] = None
    hourly_cost_usd: Optional[float] = None
    state: str = "unknown"  # running | stopped | unknown
    last_seen_at: Optional[datetime] = None


class MetricPoint(SQLModel, table=True):
    """One metric sample for a server."""

    __table_args__ = (Index("ix_metricpoint_server_ts", "server_id", "ts"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    server_id: int = Field(foreign_key="server.id")
    ts: datetime
    cpu_pct: float
    mem_pct: Optional[float] = None
    net_in_kbps: float = 0.0
    net_out_kbps: float = 0.0
    disk_pct: Optional[float] = None
    requests_per_min: Optional[float] = None


class Forecast(SQLModel, table=True):
    """A stored forecast for a group: points_json holds [{ts, expected, low, high}]."""

    __table_args__ = (Index("ix_forecast_group_horizon_created", "group_id", "horizon", "created_at"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id")
    created_at: datetime = Field(default_factory=utcnow)
    horizon: str  # short | plan
    points_json: str = Field(sa_column=Column(Text, nullable=False))
    method: str


class Recommendation(SQLModel, table=True):
    """A suggested change waiting for (or past) human approval."""

    __table_args__ = (Index("ix_recommendation_group_status", "group_id", "status"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id")
    server_id: Optional[int] = Field(default=None, foreign_key="server.id")
    kind: str  # scale_up | scale_down | stop_idle | hold
    from_count: int
    to_count: int
    reason: str
    savings_month_inr: float = 0.0
    confidence: float = 0.0  # 0..1
    status: str = Field(default="pending", index=True)
    blocked_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow, index=True)
    expires_at: Optional[datetime] = None


class ActionLog(SQLModel, table=True):
    """The audit record of an approved recommendation and its outcome."""

    id: Optional[int] = Field(default=None, primary_key=True)
    recommendation_id: int = Field(foreign_key="recommendation.id", index=True)
    approved_by: str
    approved_at: datetime = Field(default_factory=utcnow, index=True)
    executed_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[str] = None  # done | failed | dry_run
    details_json: str = Field(default="{}", sa_column=Column(Text, nullable=False, default="{}"))
    realized_savings_inr: float = 0.0


class AgentToken(SQLModel, table=True):
    """A hashed token that lets an agent send metrics."""

    id: Optional[int] = Field(default=None, primary_key=True)
    token_hash: str = Field(index=True, unique=True)
    label: str
    created_at: datetime = Field(default_factory=utcnow)
    revoked: bool = False
    last_used_at: Optional[datetime] = None  # last accepted ingest (onboarding waits for this)
    last_server_id: Optional[int] = None  # the server that last reported with this token
