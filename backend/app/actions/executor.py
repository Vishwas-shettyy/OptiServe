"""Runs approved recommendations: re-check guardrails, call AWS (or dry-run), verify by polling, track savings."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import boto3
from sqlmodel import Session, col, select

from app.actions import aws_actions
from app.config import Settings
from app.connectors.aws import AwsError, make_session
from app.engine.common import HOURS_PER_MONTH, params_for
from app.engine.pipeline import prepare, recheck
from app.engine.planner import Proposal
from app.engine.pricing import hourly_usd, usd_to_inr
from app.jobs.engine_run import load_inputs
from app.models import ActionLog, Group, Recommendation, Server, as_utc, utcnow

log = logging.getLogger(__name__)

VERIFY_TIMEOUT = timedelta(minutes=10)
REMOVALS = ("scale_down", "stop_idle")


class Refused(Exception):
    """The recommendation cannot be approved; the message is safe to show."""


def _details(action: ActionLog) -> dict[str, Any]:
    """Return the action's details as a dict."""
    try:
        return json.loads(action.details_json or "{}")
    except json.JSONDecodeError:
        return {}


def _set_details(action: ActionLog, **values: Any) -> None:
    """Merge values into the action's details."""
    action.details_json = json.dumps(_details(action) | values, default=str)


def refusal(db: Session, rec: Recommendation) -> Optional[str]:
    """Return why this recommendation can only be a recommendation, or None if OptiServe may act on it."""
    if rec.kind == "hold":
        return "Nothing to approve: this is a no-change update."
    group = db.get(Group, rec.group_id)
    if group is None:
        return "This group no longer exists."
    if group.provider != "aws":
        return "These servers report through the agent, so this is a recommendation only. Make the change yourself."
    if not group.managed:
        return "This group is not tagged optiserve:managed=true, so this is a recommendation only."
    if rec.kind == "stop_idle":
        server = db.get(Server, rec.server_id) if rec.server_id else None
        if server is None or server.provider != "aws":
            return "This server is not an AWS instance, so this is a recommendation only."
    elif not group.asg_name:
        return "This server is not in an Auto Scaling group, so OptiServe cannot add or remove servers for it."
    return None


def _session(db: Session, group: Group, settings: Settings) -> boto3.Session:
    """Return a boto3 session in the group's region."""
    server = db.exec(select(Server).where(Server.group_id == group.id, col(Server.region).is_not(None))).first()
    return make_session((server.region if server else None) or settings.aws_region)


def _plan_call(db: Session, rec: Recommendation, group: Group) -> dict[str, Any]:
    """Describe the AWS call this recommendation needs."""
    if rec.kind == "stop_idle":
        server = db.get(Server, rec.server_id)
        assert server is not None
        return {"call": "ec2:StopInstances", "instance_id": server.external_id, "server": server.name,
                "asg_name": group.asg_name}
    return {"call": "autoscaling:SetDesiredCapacity", "asg_name": group.asg_name,
            "from": rec.from_count, "to": rec.to_count}


def _recheck_message(db: Session, rec: Recommendation, group: Group, settings: Settings, now: datetime) -> Optional[str]:
    """Re-run the guardrails on the approved change; return a plain reason if it must not run now."""
    params = params_for(settings.live_mode)
    inputs = load_inputs(db, group, now, params)
    if inputs.info.current != rec.from_count:
        return (f"The group now has {inputs.info.current} servers (it had {rec.from_count} when this was suggested). "
                "Wait for a fresh suggestion.")
    server_name = None
    if rec.server_id is not None:
        server = db.get(Server, rec.server_id)
        server_name = server.name if server else None
    prepared = prepare(inputs.info, inputs.servers, inputs.metrics, now, params, settings.risk, inputs.last_action_at)
    outcome = recheck(prepared, Proposal(rec.kind, rec.from_count, rec.to_count, rec.server_id, server_name))
    if outcome.status == "blocked" and outcome.blocked_reason:
        return outcome.blocked_reason
    final = outcome.proposal
    same_direction = final.kind == rec.kind
    if rec.kind == "scale_up" and same_direction and final.to_count >= rec.to_count:
        return None  # still needed (maybe even more); run exactly what was approved
    if same_direction and final.to_count == rec.to_count:
        return None
    changed = next((r.message for r in outcome.results if r.status != "pass"), None)
    return changed or "The situation has changed since this was suggested. Wait for a fresh suggestion."


def approve(
    db: Session, rec: Recommendation, approver: str, settings: Settings,
    now: Optional[datetime] = None, session: Optional[boto3.Session] = None,
) -> ActionLog:
    """Record the approval and run the change; raise Refused if it cannot be approved."""
    now = now or utcnow()
    if rec.status != "pending":
        raise Refused(f"This suggestion is {rec.status}, so it cannot be approved.")
    reason = refusal(db, rec)
    if reason:
        raise Refused(reason)
    assert rec.id is not None
    rec.status = "approved"
    action = ActionLog(recommendation_id=rec.id, approved_by=approver, approved_at=now)
    db.add(rec)
    db.add(action)
    db.commit()
    db.refresh(action)
    return execute(db, rec, action, settings, now, session)


def _finish(db: Session, rec: Recommendation, action: ActionLog, status: str, result: Optional[str], now: datetime) -> ActionLog:
    """Close an action and its recommendation."""
    rec.status = status
    action.result = result
    action.finished_at = now
    db.add(rec)
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def execute(
    db: Session, rec: Recommendation, action: ActionLog, settings: Settings,
    now: Optional[datetime] = None, session: Optional[boto3.Session] = None,
) -> ActionLog:
    """Run one approved recommendation: guardrails again, then dry-run or the real AWS call."""
    now = now or utcnow()
    if rec.status != "approved":
        raise Refused("Only approved suggestions run.")
    group = db.get(Group, rec.group_id)
    reason = refusal(db, rec)
    if group is None or reason:
        _set_details(action, outcome="refused", message=reason or "This group no longer exists.")
        rec.blocked_reason = reason
        return _finish(db, rec, action, "blocked", None, now)
    blocked = _recheck_message(db, rec, group, settings, now)
    if blocked:
        rec.blocked_reason = blocked
        _set_details(action, outcome="blocked", message=blocked)
        return _finish(db, rec, action, "blocked", None, now)
    plan = _plan_call(db, rec, group)
    if settings.dry_run:
        _set_details(action, outcome="dry_run", would_call=plan,
                     message="Dry run is on, so nothing was changed. This is what would have happened.")
        action.executed_at = now
        return _finish(db, rec, action, "done", "dry_run", now)
    session = session or _session(db, group, settings)
    try:
        if plan["call"] == "ec2:StopInstances":
            aws_actions.stop_instance(session, plan["instance_id"], plan["asg_name"])
        else:
            aws_actions.set_desired_capacity(session, plan["asg_name"], rec.to_count)
    except AwsError as exc:
        _set_details(action, outcome="failed", called=plan, message=str(exc))
        action.executed_at = now
        return _finish(db, rec, action, "failed", "failed", now)
    action.executed_at = now
    _set_details(action, outcome="executing", called=plan)
    rec.status = "executing"
    db.add(rec)
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def _check_done(db: Session, rec: Recommendation, group: Group, session: boto3.Session) -> tuple[bool, dict[str, Any]]:
    """Ask AWS whether the change has finished; return (done, what was seen)."""
    if rec.kind == "stop_idle":
        server = db.get(Server, rec.server_id)
        assert server is not None
        state, _ = aws_actions.instance_state(session, server.external_id)
        return state == "stopped", {"instance_state": state}
    assert group.asg_name is not None
    st = aws_actions.capacity_status(session, group.asg_name)
    return st.desired == rec.to_count and st.in_service == rec.to_count, {"desired": st.desired, "in_service": st.in_service}


def verify_actions(
    db: Session, settings: Settings, now: Optional[datetime] = None, session: Optional[boto3.Session] = None,
) -> list[ActionLog]:
    """Poll every executing action until AWS shows it finished, or fail it after 10 minutes."""
    now = now or utcnow()
    finished: list[ActionLog] = []
    for rec in db.exec(select(Recommendation).where(Recommendation.status == "executing")).all():
        action = db.exec(
            select(ActionLog).where(ActionLog.recommendation_id == rec.id).order_by(col(ActionLog.id).desc())
        ).first()
        group = db.get(Group, rec.group_id)
        if action is None or group is None:
            continue
        try:
            done, seen = _check_done(db, rec, group, session or _session(db, group, settings))
        except AwsError as exc:
            done, seen = False, {"error": str(exc)}
        _set_details(action, last_check=now.isoformat(), seen=seen)
        if done:
            if rec.kind == "stop_idle":
                server = db.get(Server, rec.server_id)
                if server is not None:
                    server.state = "stopped"
                    db.add(server)
                if group.asg_name:
                    group.desired = max(0, group.desired - 1)
            else:
                group.desired = rec.to_count
            db.add(group)
            _set_details(action, outcome="done")
            finished.append(_finish(db, rec, action, "done", "done", now))
        elif now - as_utc(action.executed_at or now) > VERIFY_TIMEOUT:
            _set_details(action, outcome="failed", message="AWS did not finish the change within 10 minutes.")
            finished.append(_finish(db, rec, action, "failed", "failed", now))
        else:
            db.add(action)
            db.commit()
    return finished


def _price(server: Server) -> float:
    """Return a server's hourly USD price (override, table, else 0)."""
    return hourly_usd(server.instance_type, server.hourly_cost_usd) or 0.0


def refresh_realized_savings(db: Session, settings: Settings, now: Optional[datetime] = None) -> float:
    """Update realized savings for finished removals: servers removed × hours since × hourly price; return the total."""
    now = now or utcnow()
    total = 0.0
    rows = db.exec(
        select(ActionLog, Recommendation)
        .join(Recommendation, col(Recommendation.id) == ActionLog.recommendation_id)
        .where(ActionLog.result == "done", col(Recommendation.kind).in_(REMOVALS))
    ).all()
    for action, rec in rows:
        start = as_utc(action.finished_at)
        if start is None:
            continue
        servers = db.exec(select(Server).where(Server.group_id == rec.group_id)).all()
        if rec.kind == "stop_idle":
            stopped = db.get(Server, rec.server_id) if rec.server_id else None
            if stopped is None or stopped.state == "running":
                total += action.realized_savings_inr  # started again: keep what was saved, stop counting
                continue
            price = _price(stopped)
        else:
            price = sum(_price(s) for s in servers) / len(servers) if servers else 0.0
        later_up = db.exec(
            select(ActionLog.finished_at)
            .join(Recommendation, col(Recommendation.id) == ActionLog.recommendation_id)
            .where(Recommendation.group_id == rec.group_id, Recommendation.kind == "scale_up",
                   ActionLog.result == "done", ActionLog.finished_at > start)
            .order_by(col(ActionLog.finished_at))
        ).first()
        end = min(now, as_utc(later_up) or now)
        hours = max(0.0, (end - start).total_seconds() / 3600.0)
        removed = rec.from_count - rec.to_count
        action.realized_savings_inr = round(usd_to_inr(price, settings.usd_inr) * removed * hours, 2)
        db.add(action)
        total += action.realized_savings_inr
    db.commit()
    return round(total, 2)


def monthly_cost_inr(servers: list[Server], usd_inr: float) -> float:
    """Return the monthly INR cost of running servers at their hourly price."""
    return round(sum(usd_to_inr(_price(s), usd_inr) * HOURS_PER_MONTH for s in servers if s.state == "running"), 2)
