"""Shared test setup: isolated settings, a temporary SQLite database and a test client."""

from collections.abc import Iterator
from pathlib import Path

import bcrypt
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import get_engine

ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "correct-horse-battery"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Return a TestClient backed by a fresh database and known admin credentials."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("JWT_SECRET", "test-secret-with-enough-length-for-hs256")
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt(4)).decode())
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:5173")
    get_settings.cache_clear()
    get_engine.cache_clear()
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
    get_engine().dispose()
    get_settings.cache_clear()
    get_engine.cache_clear()
