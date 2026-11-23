"""Agent tokens, ingest validation, per-token rate limiting and server upsert."""

import hashlib
import secrets
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from app.models import AgentToken, Connection, Group, MetricPoint, Server, utcnow

TOKEN_PREFIX = "osa_"
UNGROUPED = "Ungrouped"
MAX_POINTS_PER_REQUEST = 120  # 10 min of offline buffer at 10 s = 60, with headroom
MAX_POINT_AGE = timedelta(minutes=30)
MAX_POINT_SKEW = timedelta(minutes=5)


# ---------- tokens ----------


def generate_token() -> str:
    """Return a new random agent token (shown to the admin once, never stored)."""
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest stored for a token (tokens are high-entropy, so no salt is needed)."""
    return hashlib.sha256(token.encode()).hexdigest()


def find_active_token(session: Session, token: str) -> Optional[AgentToken]:
    """Return the non-revoked AgentToken matching a plaintext token, or None."""
    row = session.exec(select(AgentToken).where(AgentToken.token_hash == hash_token(token))).first()
    if row is None or row.revoked:
        return None
    return row


# ---------- rate limit ----------


class RateLimiter:
    """Sliding one-minute window of request times per key, in memory."""

    def __init__(self, limit_per_min: int, window_s: float = 60.0) -> None:
        """Create a limiter allowing `limit_per_min` hits per window."""
        self.limit = limit_per_min
        self.window = window_s
        self._hits: dict[int, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: int, now: Optional[float] = None) -> Optional[int]:
        """Record a hit; return None if allowed, else seconds until the next hit is allowed."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(1, int(self.window - (now - hits[0])) + 1)
            hits.append(now)
            return None


# ---------- ingest payload ----------


class HostInfo(BaseModel):
    """Who is reporting: an EC2 instance (instance id) or a plain host (hostname)."""

    external_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    instance_type: Optional[str] = Field(default=None, max_length=64)
    region: Optional[str] = Field(default=None, max_length=64)
    asg_name: Optional[str] = Field(default=None, max_length=255)


class MetricIn(BaseModel):
    """One 10-second sample from the agent."""

    ts: datetime
    cpu_pct: float = Field(ge=0, le=100)
    mem_pct: Optional[float] = Field(default=None, ge=0, le=100)
    net_in_kbps: float = Field(ge=0)
    net_out_kbps: float = Field(ge=0)
    disk_pct: Optional[float] = Field(default=None, ge=0, le=100)
    requests_per_min: Optional[float] = Field(default=None, ge=0)

    @field_validator("ts")
    @classmethod
    def ts_recent_utc(cls, value: datetime) -> datetime:
        """Treat naive timestamps as UTC and reject samples too old or in the future."""
        value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        if value > now + MAX_POINT_SKEW:
            raise ValueError("timestamp is in the future; check the server clock")
        if value < now - MAX_POINT_AGE:
            raise ValueError("timestamp is older than 30 minutes")
        return value


class IngestRequest(BaseModel):
    """Body of POST /api/ingest: host identity plus one or more samples."""

    host: HostInfo
    metrics: list[MetricIn] = Field(min_length=1, max_length=MAX_POINTS_PER_REQUEST)


class IngestResponse(BaseModel):
    """What was stored."""

    server_id: int
    group_id: int
    accepted: int


# ---------- storage ----------


def _ungrouped(session: Session) -> Group:
    """Return the 'Ungrouped' agent group, creating it if needed."""
    group = session.exec(select(Group).where(Group.name == UNGROUPED, Group.provider == "agent")).first()
    if group is None:
        group = Group(name=UNGROUPED, provider="agent", min_size=0, max_size=0, desired=0, managed=False)
        session.add(group)
        session.flush()
    return group


def _touch_agent_connection(session: Session, now: datetime) -> None:
    """Mark the agent data source as healthy and recently synced."""
    conn = session.exec(select(Connection).where(Connection.kind == "agent")).first()
    if conn is None:
        conn = Connection(kind="agent", name="OptiServe agent")
    conn.status = "ok"
    conn.error_message = None
    conn.last_sync_at = now
    session.add(conn)


def upsert_server(session: Session, host: HostInfo, now: datetime) -> Server:
    """Find the server by external_id (agent or AWS record) or create it in 'Ungrouped'; refresh its details."""
    server = session.exec(select(Server).where(Server.external_id == host.external_id)).first()
    if server is None:
        group: Optional[Group] = None
        if host.asg_name:
            group = session.exec(select(Group).where(Group.asg_name == host.asg_name)).first()
        group = group or _ungrouped(session)
        server = Server(group_id=group.id, name=host.name, provider="agent", external_id=host.external_id)
    elif server.group_id is None:
        server.group_id = _ungrouped(session).id
    if server.provider == "agent":
        server.name = host.name
    server.instance_type = host.instance_type or server.instance_type
    server.region = host.region or server.region
    server.state = "running"
    server.last_seen_at = now
    session.add(server)
    session.flush()
    return server


def ingest(session: Session, body: IngestRequest) -> IngestResponse:
    """Store a batch of samples for one host and commit."""
    now = utcnow()
    server = upsert_server(session, body.host, now)
    assert server.id is not None and server.group_id is not None
    for m in body.metrics:
        session.add(
            MetricPoint(
                server_id=server.id,
                ts=m.ts,
                cpu_pct=m.cpu_pct,
                mem_pct=m.mem_pct,
                net_in_kbps=m.net_in_kbps,
                net_out_kbps=m.net_out_kbps,
                disk_pct=m.disk_pct,
                requests_per_min=m.requests_per_min,
            )
        )
    _touch_agent_connection(session, now)
    session.commit()
    return IngestResponse(server_id=server.id, group_id=server.group_id, accepted=len(body.metrics))
