"""FastAPI application: routers, CORS and startup."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import auth
from app.api import actions, agent_tokens, connections, forecast, groups, ingest, recommendations, stats
from app.config import get_settings
from app.db import init_db
from app.jobs.scheduler import build_scheduler

VERSION = "2.0.0"


class HealthResponse(BaseModel):
    """Service health and mode flags."""

    status: str
    version: str
    live_mode: bool
    dry_run: bool


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Create tables and start the background jobs; stop them on shutdown."""
    init_db()
    scheduler = build_scheduler(get_settings()) if get_settings().scheduler_enabled else None
    if scheduler is not None:
        scheduler.start()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    """Build the FastAPI app with middleware and routers."""
    settings = get_settings()
    app = FastAPI(title="OptiServe", version=VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.get("/api/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        """Report that the API is up and which modes are on."""
        current = get_settings()
        return HealthResponse(status="ok", version=VERSION, live_mode=current.live_mode, dry_run=current.dry_run)

    app.include_router(auth.router)
    app.include_router(agent_tokens.router)
    app.include_router(ingest.router)
    app.include_router(connections.router)
    app.include_router(recommendations.router)
    app.include_router(actions.router)
    app.include_router(stats.router)
    app.include_router(groups.router)
    app.include_router(forecast.router)
    return app


app = create_app()
