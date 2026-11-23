"""APScheduler jobs (CLAUDE.md §6), run inside the API process. Each job opens its own database session."""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session, select

from app.actions import executor
from app.config import Settings, get_settings
from app.connectors import aws
from app.db import get_engine
from app.jobs import engine_run
from app.models import Connection, utcnow

log = logging.getLogger(__name__)

# The running scheduler (set by build_scheduler) so a settings change can retime jobs.
SCHEDULER: Optional[BackgroundScheduler] = None

# Latest accuracy score, refreshed by score_accuracy and read by /api/stats.
ACCURACY: dict[str, Any] = {"accuracy_pct": None, "wape": None, "points": 0, "updated_at": None}


def sync_aws(settings: Optional[Settings] = None) -> int:
    """Sync every AWS connection; return how many succeeded."""
    settings = settings or get_settings()
    ok = 0
    with Session(get_engine()) as db:
        for conn in db.exec(select(Connection).where(Connection.kind == "aws")).all():
            try:
                aws.sync_connection(db, conn, settings)
                ok += 1
            except aws.AwsError as exc:
                log.warning("AWS sync failed for connection %s: %s", conn.id, exc)
    return ok


def run_engine(settings: Optional[Settings] = None, now: Optional[datetime] = None) -> int:
    """Run the engine for every group and upsert recommendations; return how many are open."""
    with Session(get_engine()) as db:
        return len(engine_run.run_engine(db, settings or get_settings(), now))


def plan_forecast(settings: Optional[Settings] = None, now: Optional[datetime] = None) -> dict[int, str]:
    """Store 7-day forecasts for groups with ≥ 7 days of history."""
    with Session(get_engine()) as db:
        return engine_run.run_plan_forecast(db, settings or get_settings(), now)


def verify_actions(settings: Optional[Settings] = None, now: Optional[datetime] = None) -> int:
    """Poll executing actions and refresh realized savings; return how many finished."""
    settings = settings or get_settings()
    with Session(get_engine()) as db:
        finished = executor.verify_actions(db, settings, now)
        executor.refresh_realized_savings(db, settings, now)
        return len(finished)


def score_accuracy(now: Optional[datetime] = None) -> dict[str, Any]:
    """Score the last 24 h of short forecasts against actual demand and cache the result."""
    with Session(get_engine()) as db:
        result = engine_run.compute_accuracy(db, now)
    ACCURACY.update(result, updated_at=now or utcnow())
    return dict(ACCURACY)


def downsample(now: Optional[datetime] = None) -> int:
    """Average raw metrics older than 14 days into 5-minute buckets."""
    with Session(get_engine()) as db:
        return engine_run.downsample(db, now)


def _safe(job: Callable[[], Any], name: str) -> Callable[[], None]:
    """Wrap a job so one failure is logged and never stops the scheduler."""

    def run() -> None:
        """Run the job and log any exception."""
        try:
            job()
        except Exception:  # noqa: BLE001 - a background job must not crash the process
            log.exception("job %s failed", name)

    return run


def job_intervals(settings: Settings) -> dict[str, timedelta]:
    """Return how often each job runs; AWS sync is every minute in live mode, else every 5 minutes."""
    return {
        "sync_aws": timedelta(minutes=1 if settings.live_mode else 5),
        "run_engine": timedelta(minutes=1),
        "plan_forecast": timedelta(hours=1),
        "verify_actions": timedelta(seconds=15),
        "score_accuracy": timedelta(minutes=5),
        "downsample": timedelta(days=1),
    }


def build_scheduler(settings: Settings) -> BackgroundScheduler:
    """Create (not start) the scheduler with all six jobs."""
    jobs: dict[str, Callable[[], Any]] = {
        "sync_aws": lambda: sync_aws(),
        "run_engine": lambda: run_engine(),
        "plan_forecast": lambda: plan_forecast(),
        "verify_actions": lambda: verify_actions(),
        "score_accuracy": lambda: score_accuracy(),
        "downsample": lambda: downsample(),
    }
    scheduler = BackgroundScheduler(timezone="UTC")
    start = datetime.now().astimezone()
    for name, every in job_intervals(settings).items():
        first = start + timedelta(seconds=5) if name in ("sync_aws", "run_engine", "score_accuracy") else None
        scheduler.add_job(
            _safe(jobs[name], name), "interval", seconds=int(every.total_seconds()), id=name, name=name,
            max_instances=1, coalesce=True, replace_existing=True, **({"next_run_time": first} if first else {}),
        )
    global SCHEDULER
    SCHEDULER = scheduler
    return scheduler


def retime(settings: Settings) -> bool:
    """Apply job intervals after live mode changes; return True when a running scheduler was updated."""
    if SCHEDULER is None or not SCHEDULER.running:
        return False
    for name, every in job_intervals(settings).items():
        if SCHEDULER.get_job(name) is not None:
            SCHEDULER.reschedule_job(name, trigger="interval", seconds=int(every.total_seconds()))
    return True
