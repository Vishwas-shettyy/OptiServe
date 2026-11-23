"""The nine safety rules (CLAUDE.md §7). Each returns pass / adjusted / blocked and a plain message. Pure."""

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Callable, Optional

import pandas as pd

from app.engine.common import EngineParams, duration_words, utc
from app.engine.forecaster import ForecastResult, band_ratio
from app.engine.planner import REMOVAL_KINDS, GroupInfo, Proposal, needed_within

RULE_NAMES = {
    1: "Minimum servers", 2: "Maximum servers", 3: "Scale up early", 4: "Step limit", 5: "Cooldown",
    6: "Health", 7: "Low data", 8: "Low confidence", 9: "Managed tag",
}


@dataclass(frozen=True)
class GuardrailResult:
    """One rule's verdict."""

    number: int
    rule: str
    status: str  # pass | adjusted | blocked
    message: str


@dataclass(frozen=True)
class GuardContext:
    """Everything the rules need, already computed by the caller."""

    group: GroupInfo
    now: pd.Timestamp
    params: EngineParams
    target_util: float
    forecast: ForecastResult
    data_span: timedelta
    profiles: pd.DataFrame
    last_action_at: Optional[datetime] = None


@dataclass
class GuardOutcome:
    """The proposal after all rules, each rule's result and whether it may run."""

    proposal: Proposal
    results: list[GuardrailResult] = field(default_factory=list)
    blocked_reason: Optional[str] = None
    hold_rule: Optional[int] = None
    executable: bool = True

    @property
    def status(self) -> str:
        """Return 'blocked' when a rule (1–8) stopped a change, else 'pending'."""
        return "blocked" if self.blocked_reason and self.proposal.kind != "hold" else "pending"


Rule = Callable[[Proposal, GuardContext], tuple[Proposal, str, str]]


def _plural(n: int) -> str:
    """Return 'server' or 'servers'."""
    return "server" if n == 1 else "servers"


def _hold(p: Proposal) -> Proposal:
    """Return a no-change proposal."""
    return Proposal("hold", p.from_count, p.from_count)


def rule_min_servers(p: Proposal, ctx: GuardContext) -> tuple[Proposal, str, str]:
    """Rule 1: keep at least the group minimum and at least one server."""
    floor = max(int(ctx.group.min_size), 1)
    if p.to_count >= floor:
        return p, "pass", f"Keeps at least {floor} {_plural(floor)} running."
    if p.kind == "stop_idle":
        return p, "blocked", f"Stopping {p.server_name} would leave fewer than {floor} {_plural(floor)} in this group."
    if floor >= p.from_count:
        return _hold(p), "adjusted", f"Already at the minimum of {floor} {_plural(floor)}."
    return replace(p, to_count=floor), "adjusted", f"Keeping the minimum of {floor} {_plural(floor)}."


def rule_max_servers(p: Proposal, ctx: GuardContext) -> tuple[Proposal, str, str]:
    """Rule 2: never go above the group maximum."""
    cap = int(ctx.group.max_size)
    if p.to_count <= cap:
        return p, "pass", f"Stays within the maximum of {cap} {_plural(cap)}."
    if p.from_count >= cap:
        return p, "blocked", f"Needs {p.to_count} servers but this group's maximum is {cap}. Raise the maximum to stay safe."
    return replace(p, to_count=cap), "adjusted", f"Needs {p.to_count} servers; adding up to the maximum of {cap}."


def rule_scale_up_early(p: Proposal, ctx: GuardContext) -> tuple[Proposal, str, str]:
    """Rule 3: if more servers are needed within the lead time, add them now."""
    lead = duration_words(ctx.params.lead_time)
    need = needed_within(ctx.forecast, ctx.now + ctx.params.lead_time, ctx.target_util)
    if need == 0:
        return p, "pass", "No forecast yet, so nothing to prepare for."
    if need <= p.to_count:
        return p, "pass", f"Enough servers for the next {lead}."
    raised = Proposal("scale_up", p.from_count, need)
    return raised, "adjusted", f"{need} servers will be needed within {lead}, so add them now while there is time to start."


def rule_step_limit(p: Proposal, ctx: GuardContext) -> tuple[Proposal, str, str]:
    """Rule 4: remove at most one server per action."""
    step = ctx.params.max_step_down
    if p.from_count - p.to_count <= step:
        return p, "pass", f"Removes at most {step} {_plural(step)} at a time."
    to = p.from_count - step
    return replace(p, to_count=to), "adjusted", f"Removing {step} {_plural(step)} at a time: going from {p.from_count} to {to} now."


def rule_cooldown(p: Proposal, ctx: GuardContext) -> tuple[Proposal, str, str]:
    """Rule 5: wait after the last action on the group so it can settle."""
    if p.kind == "hold" or ctx.last_action_at is None:
        return p, "pass", "No recent change on this group."
    since = ctx.now - utc(ctx.last_action_at)
    if since >= ctx.params.cooldown:
        return p, "pass", f"Last change was {duration_words(since)} ago."
    wait = ctx.params.cooldown - since
    return p, "blocked", (f"The last change was {duration_words(since)} ago. "
                          f"Waiting {duration_words(wait + timedelta(seconds=59))} more so it can settle.")


def rule_health(p: Proposal, ctx: GuardContext) -> tuple[Proposal, str, str]:
    """Rule 6: no removals while any server is unhealthy."""
    sick = ctx.profiles[~ctx.profiles["healthy"].astype(bool)] if len(ctx.profiles) else ctx.profiles
    if not len(sick):
        return p, "pass", "All servers are healthy."
    first = sick.iloc[0]
    msg = f"{first['name']} {first['health_reason']}."
    if len(sick) > 1:
        msg = f"{msg[:-1]}, and {len(sick) - 1} more {_plural(len(sick) - 1)} need attention."
    if p.kind in REMOVAL_KINDS:
        return p, "blocked", f"{msg} Fix it before removing servers."
    return p, "pass", f"{msg} Adding or keeping servers is still allowed."


def rule_low_data(p: Proposal, ctx: GuardContext) -> tuple[Proposal, str, str]:
    """Rule 7: with too little history, hold."""
    need = ctx.params.min_data
    if ctx.data_span >= need:
        return p, "pass", f"{duration_words(ctx.data_span)} of data collected."
    return _hold(p), "blocked", (f"OptiServe is learning: {duration_words(ctx.data_span)} of data so far, "
                                 f"it needs {duration_words(need)} before suggesting changes.")


def rule_low_confidence(p: Proposal, ctx: GuardContext) -> tuple[Proposal, str, str]:
    """Rule 8: when the forecast band is wider than expected demand, do not remove capacity."""
    ratio = band_ratio(ctx.forecast)
    if ratio <= ctx.params.low_confidence_ratio:
        return p, "pass", f"Forecast is steady (range {ratio:.0%} of expected)."
    if p.kind == "scale_down":
        return _hold(p), "blocked", "Load is too unpredictable right now to remove servers safely."
    return p, "pass", "Forecast is uncertain, but this change does not remove capacity based on it."


def rule_managed(p: Proposal, ctx: GuardContext) -> tuple[Proposal, str, str]:
    """Rule 9: act only on AWS groups tagged optiserve:managed=true; otherwise recommendation only."""
    if p.kind == "hold":
        return p, "pass", "Nothing to change."
    if ctx.group.provider != "aws":
        return p, "blocked", "These servers report through the agent, so this is a recommendation only. Make the change yourself."
    if not ctx.group.managed:
        return p, "blocked", "This group is not tagged optiserve:managed=true, so this is a recommendation only."
    return p, "pass", "Group is tagged for OptiServe to manage."


ORDER: list[tuple[int, Rule]] = [
    (3, rule_scale_up_early), (2, rule_max_servers), (1, rule_min_servers), (4, rule_step_limit),
    (7, rule_low_data), (8, rule_low_confidence), (6, rule_health), (5, rule_cooldown), (9, rule_managed),
]


def _normalise(p: Proposal) -> Proposal:
    """Make the kind match the counts after adjustments."""
    if p.to_count > p.from_count:
        return replace(p, kind="scale_up", server_id=None, server_name=None)
    if p.to_count == p.from_count:
        return Proposal("hold", p.from_count, p.from_count)
    if p.kind == "stop_idle":
        return p
    return replace(p, kind="scale_down", server_id=None, server_name=None)


def apply_guardrails(proposal: Proposal, ctx: GuardContext) -> GuardOutcome:
    """Run all nine rules in safety order and return the final proposal with every rule's result."""
    out = GuardOutcome(proposal=proposal)
    p = proposal
    results: dict[int, GuardrailResult] = {}
    for number, rule in ORDER:
        before = p
        p, status, message = rule(p, ctx)
        p = _normalise(p) if p.kind != "hold" else p
        results[number] = GuardrailResult(number, RULE_NAMES[number], status, message)
        if status == "blocked":
            if number == 9:
                out.executable = False
            elif out.blocked_reason is None:
                out.blocked_reason = message
        if before.kind != "hold" and p.kind == "hold" and out.hold_rule is None:
            out.hold_rule = number
    out.proposal = p
    out.results = [results[n] for n in sorted(results)]
    if p.kind == "hold":
        out.executable = False
    return out
