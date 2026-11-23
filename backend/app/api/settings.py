"""Settings changed from the UI: risk (Save more ⟷ Stay safe), live mode and dry run. Stored in AppSetting."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.auth import require_admin
from app.config import Settings, get_settings
from app.db import get_session
from app.engine.common import risk_params
from app.jobs import scheduler
from app.models import AppSetting, utcnow

router = APIRouter(prefix="/api/settings", tags=["settings"])

EDITABLE = ("risk", "live_mode", "dry_run")


class SettingsOut(BaseModel):
    """The editable settings plus what the risk setting means in numbers."""

    risk: float
    live_mode: bool
    dry_run: bool
    target_util_pct: int  # servers are planned to run up to this busy
    updated_at: Optional[datetime]
    updated_by: Optional[str]


class SettingsUpdate(BaseModel):
    """Any subset of the editable settings."""

    risk: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    live_mode: Optional[bool] = None
    dry_run: Optional[bool] = None


def _parse(key: str, raw: str) -> float | bool:
    """Turn a stored string back into its setting value."""
    return float(raw) if key == "risk" else raw == "true"


def apply_stored(db: Session, settings: Settings) -> None:
    """Copy settings saved from the UI onto the in-process settings (called at startup)."""
    for row in db.exec(select(AppSetting)).all():
        if row.key in EDITABLE:
            setattr(settings, row.key, _parse(row.key, row.value))


def _out(db: Session, settings: Settings) -> SettingsOut:
    """Build the response from the live settings and the newest change."""
    rows = [r for r in db.exec(select(AppSetting)).all() if r.key in EDITABLE]
    last = max(rows, key=lambda r: r.updated_at) if rows else None
    target, _ = risk_params(settings.risk)
    return SettingsOut(
        risk=settings.risk,
        live_mode=settings.live_mode,
        dry_run=settings.dry_run,
        target_util_pct=round(target * 100),
        updated_at=last.updated_at if last else None,
        updated_by=last.updated_by if last else None,
    )


@router.get("", response_model=SettingsOut)
def read_settings(
    _: str = Depends(require_admin), db: Session = Depends(get_session), settings: Settings = Depends(get_settings)
) -> SettingsOut:
    """Return the current editable settings."""
    return _out(db, settings)


@router.put("", response_model=SettingsOut)
def update_settings(
    body: SettingsUpdate,
    admin: str = Depends(require_admin),
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SettingsOut:
    """Change settings now (every job reads them on its next run) and keep them across restarts."""
    changes = body.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(settings, key, value)
        raw = ("true" if value else "false") if isinstance(value, bool) else str(round(float(value), 3))
        row = db.get(AppSetting, key) or AppSetting(key=key, value=raw)
        row.value, row.updated_at, row.updated_by = raw, utcnow(), admin
        db.add(row)
    db.commit()
    if "live_mode" in changes:
        scheduler.retime(settings)
    return _out(db, settings)
