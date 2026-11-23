"""Admin API to create, list and revoke agent tokens."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.auth import require_admin
from app.connectors.agent import generate_token, hash_token
from app.db import get_session
from app.models import AgentToken

router = APIRouter(prefix="/api/agent-tokens", tags=["agent-tokens"], dependencies=[Depends(require_admin)])


class AgentTokenCreate(BaseModel):
    """Body for creating a token."""

    label: str = Field(min_length=1, max_length=100)


class AgentTokenOut(BaseModel):
    """A token as listed (the secret itself is never returned again)."""

    id: int
    label: str
    created_at: datetime
    revoked: bool


class AgentTokenCreated(AgentTokenOut):
    """A newly created token, including the secret shown exactly once."""

    token: str


def _out(row: AgentToken) -> AgentTokenOut:
    """Convert a table row to the public response model."""
    assert row.id is not None
    return AgentTokenOut(id=row.id, label=row.label, created_at=row.created_at, revoked=row.revoked)


@router.post("", response_model=AgentTokenCreated, status_code=status.HTTP_201_CREATED)
def create_token(body: AgentTokenCreate, session: Session = Depends(get_session)) -> AgentTokenCreated:
    """Create a token; store only its hash and return the plaintext once."""
    token = generate_token()
    row = AgentToken(token_hash=hash_token(token), label=body.label.strip())
    session.add(row)
    session.commit()
    session.refresh(row)
    return AgentTokenCreated(**_out(row).model_dump(), token=token)


@router.get("", response_model=list[AgentTokenOut])
def list_tokens(session: Session = Depends(get_session)) -> list[AgentTokenOut]:
    """List all tokens, newest first."""
    rows = session.exec(select(AgentToken).order_by(AgentToken.created_at.desc())).all()  # type: ignore[attr-defined]
    return [_out(r) for r in rows]


@router.delete("/{token_id}", response_model=AgentTokenOut)
def revoke_token(token_id: int, session: Session = Depends(get_session)) -> AgentTokenOut:
    """Revoke a token so agents using it are rejected."""
    row = session.get(AgentToken, token_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found.")
    row.revoked = True
    session.add(row)
    session.commit()
    session.refresh(row)
    return _out(row)
