"""Simulated human-in-the-loop approval flow: per-card decisions, action log and pending count (UI state only)."""

from datetime import datetime

import streamlit as st

from engine.pipeline import ScenarioResult, ServiceResult
from ui import components
from ui.components import money, server_range
from ui.styles import ACCENT, TEXT_2, TONE_COLORS

DecisionKey = tuple[str, str, float]
STATES: dict[str, tuple[str, str]] = {
    "pending": ("Awaiting approval", TONE_COLORS["warning"]),
    "approved": ("Approved · plan scheduled", TONE_COLORS["success"]),
    "rejected": ("Rejected · keeping {current} servers", TEXT_2),
    "acknowledged": ("Acknowledged · holding capacity", ACCENT),
}
LOG_LABELS: dict[str, str] = {"approved": "Approved", "rejected": "Rejected", "acknowledged": "Acknowledged",
                              "pending": "Undone"}


def _decisions() -> dict[DecisionKey, str]:
    """Return the session's decision store keyed by (scenario, service, risk)."""
    return st.session_state.setdefault("decisions", {})


def _log() -> list[dict]:
    """Return the session's action log (oldest first)."""
    return st.session_state.setdefault("action_log", [])


def decision_key(result: ScenarioResult, service: str) -> DecisionKey:
    """Return the decision key for a service under the current scenario and risk."""
    return result.scenario.key, service, round(float(result.risk), 2)


def _decide(key: DecisionKey, state: str, impact: float) -> None:
    """Store a decision (or clear it when state is 'pending') and append it to the action log."""
    store = _decisions()
    if state == "pending":
        store.pop(key, None)
    else:
        store[key] = state
    _log().append(dict(time=datetime.now().strftime("%H:%M"), user="Operator", service=key[1],
                       decision=LOG_LABELS[state], impact=impact))


def blocked_rules(sr: ServiceResult) -> list[str]:
    """Return the names of blocked safety checks for a service."""
    return [str(g["rule"]) for g in sr.guardrails if g["status"] == "blocked"]


def approval_controls(result: ScenarioResult, sr: ServiceResult, page: str) -> None:
    """Render the decision pill, the approved/rejected note and Approve/Reject/Acknowledge/Undo buttons."""
    rec, key = sr.recommendation, decision_key(result, sr.service)
    state = _decisions().get(key, "pending")
    blocked = blocked_rules(sr)
    label, color = STATES[state]
    note = ""
    if state == "approved":
        start = sr.plan["timestamp"].min()
        note = (f"OptiServe will run {server_range(rec['planned_min'], rec['planned_max'])} servers on the hourly "
                f"schedule from {start:%a %d %b %H:%M}. Simulated — in production this calls the cloud autoscaler.")
    components.decision_status(label.format(current=rec["current"]), color, note)
    uid = f"{page}_{sr.service}"
    with st.container(key=f"appr_{uid}", horizontal=True, gap="small", vertical_alignment="center"):
        if state != "pending":
            st.button("Undo", key=f"undo_{uid}", type="tertiary", icon=":material/undo:",
                      on_click=_decide, args=(key, "pending", 0.0))
            return
        st.button("Approve", key=f"approve_{uid}", type="primary", icon=":material/check:", disabled=bool(blocked),
                  help=f"Blocked by safety check: {', '.join(blocked)}" if blocked else "Schedule this plan (simulated)",
                  on_click=_decide, args=(key, "approved", float(rec["savings_monthly"])))
        if blocked:
            st.button("Acknowledge", key=f"ack_{uid}", type="secondary", icon=":material/visibility:",
                      on_click=_decide, args=(key, "acknowledged", 0.0))
        else:
            st.button("Reject", key=f"reject_{uid}", type="secondary", icon=":material/close:",
                      on_click=_decide, args=(key, "rejected", 0.0))


def pending_count(result: ScenarioResult) -> int:
    """Return how many recommendations of the current scenario and risk still await a decision."""
    store = _decisions()
    return sum(decision_key(result, n) not in store for n, sr in result.services.items() if not sr.plan.empty)


def action_log() -> None:
    """Render the action log, newest first, or an empty state."""
    rows = [dict(r, impact_text=f"{'−' if r['impact'] < 0 else ''}{money(abs(r['impact']))}/mo")
            for r in reversed(_log())]
    components.action_log(rows)
