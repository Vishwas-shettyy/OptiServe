"""Application settings, read from environment variables and backend/.env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """All runtime settings; see backend/.env.example for descriptions."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{BACKEND_DIR / 'optiserve.db'}"
    jwt_secret: str = ""
    jwt_expiry_hours: int = 12
    admin_email: str = ""
    admin_password_hash: str = ""
    aws_region: str = "ap-south-1"
    live_mode: bool = False
    dry_run: bool = True
    usd_inr: float = 83.0
    frontend_origin: str = "http://localhost:5173"

    @property
    def cookie_secure(self) -> bool:
        """Send the auth cookie over HTTPS only when the frontend is served over HTTPS."""
        return self.frontend_origin.startswith("https://")


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
