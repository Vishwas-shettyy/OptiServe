"""Data-source connections: connect AWS, list connections, trigger a sync."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete
from sqlmodel import Session, col, select

from app.auth import require_admin
from app.config import Settings, get_settings
from app.connectors import aws
from app.db import get_session
from app.models import Connection, Group, MetricPoint, Recommendation, Server

router = APIRouter(prefix="/api/connections", tags=["connections"], dependencies=[Depends(require_admin)])


class AwsConnectRequest(BaseModel):
    """Region plus optional keys. Without keys the backend's environment or IAM role is used."""

    region: str = Field(min_length=4, max_length=32, pattern=r"^[a-z]{2}(-[a-z]+)+-\d$")
    access_key_id: Optional[str] = Field(default=None, min_length=16, max_length=128)
    secret_access_key: Optional[str] = Field(default=None, min_length=16, max_length=256)
    session_token: Optional[str] = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def keys_together(self) -> "AwsConnectRequest":
        """Require the access key and secret to be given together."""
        if bool(self.access_key_id) != bool(self.secret_access_key):
            raise ValueError("Give both the access key ID and the secret access key, or neither.")
        return self


class ConnectionOut(BaseModel):
    """A connection as shown in the UI (never includes credentials)."""

    id: int
    kind: str
    name: str
    region: Optional[str]
    status: str
    last_sync_at: Optional[datetime]
    error_message: Optional[str]


class AwsConnectResponse(BaseModel):
    """The connection plus the result of its first (backfill) sync, if it succeeded."""

    connection: ConnectionOut
    sync: Optional[aws.SyncResult]


class FoundInstance(BaseModel):
    """An EC2 instance found by a connection test."""

    instance_id: str
    name: str
    state: str
    instance_type: str
    managed: bool
    group: Optional[str]


class FoundGroup(BaseModel):
    """An Auto Scaling group found by a connection test."""

    name: str
    min_size: int
    max_size: int
    desired: int
    managed: bool


class AwsTestResponse(BaseModel):
    """What OptiServe can see with these credentials. Nothing is saved."""

    account_id: str
    region: str
    instances: list[FoundInstance]
    groups: list[FoundGroup]


def _out(conn: Connection) -> ConnectionOut:
    """Convert a table row to the response model."""
    assert conn.id is not None
    return ConnectionOut(
        id=conn.id,
        kind=conn.kind,
        name=conn.name,
        region=conn.region,
        status=conn.status,
        last_sync_at=conn.last_sync_at,
        error_message=conn.error_message,
    )


@router.post("/aws/test", response_model=AwsTestResponse)
def test_aws(body: AwsConnectRequest) -> AwsTestResponse:
    """Check the credentials and list instances and groups, without saving anything or keeping the keys."""
    session = aws.make_session(body.region, body.access_key_id, body.secret_access_key, body.session_token)
    try:
        identity = aws.validate_credentials(session)
        instances, groups = aws.discover(session)
    except aws.AwsError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return AwsTestResponse(
        account_id=identity.account_id,
        region=body.region,
        instances=[
            FoundInstance(
                instance_id=i.instance_id,
                name=i.name,
                state=i.state,
                instance_type=i.instance_type,
                managed=i.managed,
                group=i.asg_name,
            )
            for i in instances
        ],
        groups=[
            FoundGroup(name=g.name, min_size=g.min_size, max_size=g.max_size, desired=g.desired, managed=g.managed)
            for g in groups
        ],
    )


@router.post("/aws", response_model=AwsConnectResponse, status_code=status.HTTP_201_CREATED)
def connect_aws(
    body: AwsConnectRequest,
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AwsConnectResponse:
    """Validate credentials, keep keys in process env only, save the connection and backfill 14 days."""
    session = aws.make_session(body.region, body.access_key_id, body.secret_access_key, body.session_token)
    try:
        identity = aws.validate_credentials(session)
    except aws.AwsError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if body.access_key_id and body.secret_access_key:
        aws.set_process_credentials(body.access_key_id, body.secret_access_key, body.session_token)
    name = f"AWS {identity.account_id}"
    conn = db.exec(
        select(Connection).where(Connection.kind == "aws", Connection.name == name, Connection.region == body.region)
    ).first()
    if conn is None:
        conn = Connection(kind="aws", name=name, region=body.region)
        db.add(conn)
        db.commit()
        db.refresh(conn)
    try:
        result: Optional[aws.SyncResult] = aws.sync_connection(db, conn, settings, session=aws.make_session(body.region))
    except aws.AwsError:
        result = None
    db.refresh(conn)
    return AwsConnectResponse(connection=_out(conn), sync=result)


@router.get("", response_model=list[ConnectionOut])
def list_connections(db: Session = Depends(get_session)) -> list[ConnectionOut]:
    """List all connections."""
    return [_out(c) for c in db.exec(select(Connection).order_by(Connection.id)).all()]


@router.post("/{connection_id}/sync", response_model=aws.SyncResult)
def sync_now(
    connection_id: int,
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> aws.SyncResult:
    """Sync one AWS connection now."""
    conn = db.get(Connection, connection_id)
    if conn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found.")
    if conn.kind != "aws":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Agent connections update by themselves; nothing to sync.")
    try:
        return aws.sync_connection(db, conn, settings)
    except aws.AwsError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


class RemoveResult(BaseModel):
    """What removing a connection took away."""

    removed_connection_id: int
    servers_removed: int


@router.delete("/{connection_id}", response_model=RemoveResult)
def remove_connection(connection_id: int, db: Session = Depends(get_session)) -> RemoveResult:
    """Stop reading an AWS account: drop the connection and its servers' metrics; keep the Activity history."""
    conn = db.get(Connection, connection_id)
    if conn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found.")
    if conn.kind != "aws":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "The agent connection can't be removed. Turn off its tokens instead."
        )
    others = db.exec(
        select(Connection).where(Connection.kind == "aws", Connection.region == conn.region, Connection.id != conn.id)
    ).first()
    servers = [] if others else db.exec(
        select(Server).where(Server.provider == "aws", Server.region == conn.region)
    ).all()
    ids = [s.id for s in servers if s.id is not None]
    groups = {s.group_id for s in servers if s.group_id is not None}
    if ids:
        db.exec(delete(MetricPoint).where(col(MetricPoint.server_id).in_(ids)))  # type: ignore[call-overload]
    for rec in db.exec(
        select(Recommendation).where(col(Recommendation.group_id).in_(groups), col(Recommendation.status).in_(("pending", "blocked")))
    ).all():
        rec.status = "expired"
        db.add(rec)
    for s in servers:
        db.delete(s)
    db.flush()
    for gid in groups:
        still_used = db.exec(select(Server).where(Server.group_id == gid)).first()
        referenced = db.exec(select(Recommendation).where(Recommendation.group_id == gid)).first()
        group = db.get(Group, gid)
        if group is not None and still_used is None and referenced is None:
            db.delete(group)
    db.delete(conn)
    db.commit()
    return RemoveResult(removed_connection_id=connection_id, servers_removed=len(ids))
