"""Database engine and session handling (SQLite by default, Postgres via DATABASE_URL)."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create (once) the SQLAlchemy engine for the configured database."""
    url = get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


def init_db() -> None:
    """Create all tables that do not exist yet."""
    from app import models  # noqa: F401  (registers tables on the metadata)

    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a database session."""
    with Session(get_engine()) as session:
        yield session
