"""FastAPI application: routers, CORS and startup."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import auth
from app.api import agent_tokens, ingest
from app.config import get_settings
from app.db import init_db

VERSION = "2.0.0"


class HealthResponse(BaseModel):
    """Service health and mode flags."""

    status: str
    version: str
    live_mode: bool
    dry_run: bool


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Create tables on startup."""
    init_db()
    yield


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
    return app


app = create_app()
