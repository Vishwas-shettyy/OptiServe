"""POST /api/ingest: metrics from the OptiServe agent, authenticated by a Bearer agent token."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.config import get_settings
from app.connectors.agent import IngestRequest, IngestResponse, RateLimiter, find_active_token, ingest
from app.db import get_session
from app.models import AgentToken, utcnow

router = APIRouter(prefix="/api", tags=["ingest"])
_bearer = HTTPBearer(auto_error=False)


def _limiter(request: Request) -> RateLimiter:
    """Return the app-wide ingest rate limiter, creating it on first use."""
    limiter = getattr(request.app.state, "ingest_limiter", None)
    if limiter is None:
        limiter = RateLimiter(get_settings().ingest_rate_limit_per_min)
        request.app.state.ingest_limiter = limiter
    return limiter


def require_agent_token(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> AgentToken:
    """Dependency: return the active agent token from the Bearer header, enforcing the per-token rate limit."""
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Invalid or revoked agent token.", headers={"WWW-Authenticate": "Bearer"}
    )
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise unauthorized
    token = find_active_token(session, creds.credentials)
    if token is None or token.id is None:
        raise unauthorized
    retry_after = _limiter(request).hit(token.id)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many requests for this agent token.",
            headers={"Retry-After": str(retry_after)},
        )
    return token


@router.post("/ingest", response_model=IngestResponse)
def post_ingest(
    body: IngestRequest,
    token: AgentToken = Depends(require_agent_token),
    session: Session = Depends(get_session),
) -> IngestResponse:
    """Upsert the reporting server, store its samples and note which server the token last reported from."""
    result = ingest(session, body)
    token.last_used_at = utcnow()
    token.last_server_id = result.server_id
    session.add(token)
    session.commit()
    return result
