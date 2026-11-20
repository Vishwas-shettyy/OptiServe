"""Overview page: KPI cards, fleet capacity overview and priority actions."""

import pandas as pd
import streamlit as st

from engine import config
from engine.pipeline import ScenarioResult
from ui import charts, components
from ui.components import money, money_short

SPARK_DAYS = 14
MAX_ACTIONS = 7


def fleet_series(result: ScenarioResult) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (last 7 days actual demand, next 7 days expected demand + current/planned capacity) for all services."""
    servers = result.scenario.servers
    actual, future = [], []
    for name, sr in result.services.items():
        if sr.plan.empty:
            continue
        cap = float(servers.loc[servers["service"] == name, "capacity_rps"].mean())
        hist = sr.history[sr.history["timestamp"] > sr.history["timestamp"].max() - pd.Timedelta(days=7)]
        actual.append(hist[["timestamp", "requests"]])
        future.append(pd.DataFrame({"timestamp": sr.plan["timestamp"].to_numpy(),
                                    "expected": sr.forecast["expected"].to_numpy(),
                                    "current_cap": sr.plan["current"].to_numpy() * cap,
                                    "planned_cap": sr.plan["planned"].to_numpy() * cap}))
    if not actual:
        return (pd.DataFrame(columns=["timestamp", "requests"]),
                pd.DataFrame(columns=["timestamp", "expected", "current_cap", "planned_cap"]))
    return (pd.concat(actual).groupby("timestamp", as_index=False).sum(),
            pd.concat(future).groupby("timestamp", as_index=False).sum())


def kpi_sparks(result: ScenarioResult) -> dict[str, list[float]]:
    """Return daily sparkline series: fleet demand, avg CPU, idle capacity % and planned saving per day."""
    sc, profile = result.scenario, result.profile
    active_ids = set(profile.loc[profile["status"] != "Zombie", "server_id"])
    metrics = sc.metrics[sc.metrics["server_id"].isin(active_ids)]
    recent = metrics[metrics["timestamp"] > metrics["timestamp"].max() - pd.Timedelta(days=SPARK_DAYS)]
    out: dict[str, list[float]] = {"demand": [], "cpu": [], "idle": [], "saving": []}
    if not recent.empty:
        out["demand"] = charts.daily(recent, "requests")
        out["cpu"] = charts.daily(recent, "cpu_pct", "mean")
    services = {n: sr for n, sr in result.services.items() if not sr.plan.empty}
    if not services:
        return out
    servers = sc.servers
    caps = {n: float(servers.loc[servers["service"] == n, "capacity_rps"].mean()) for n in services}
    costs = {n: float(servers.loc[servers["service"] == n, "monthly_cost"].mean()) for n in services}
    h = pd.concat([sr.history.assign(cap=int(sr.plan["current"].iloc[0]) * caps[n]) for n, sr in services.items()])
    h = h[h["timestamp"] > h["timestamp"].max() - pd.Timedelta(days=SPARK_DAYS)]
    day = h.set_index("timestamp")[["requests", "cap"]].resample("D").sum()
    out["idle"] = (100 - day["requests"] / day["cap"].where(day["cap"] > 0) * 100).clip(lower=0).fillna(0).tolist()
    plans = pd.concat([sr.plan.assign(saved=(sr.plan["current"] - sr.plan["planned"]) * costs[n]
                                      / config.HOURS_PER_MONTH) for n, sr in services.items()])
    out["saving"] = charts.daily(plans, "saved")
    return out


def render_kpis(result: ScenarioResult) -> None:
    """Draw the four headline KPI cards with icons, deltas and sparklines."""
    k, sparks = result.kpis, kpi_sparks(result)
    target = config.TARGET_CPU_FOR_WASTE
    gap = k["avg_util"] - target
    share = k["potential_savings"] / k["monthly_cost"] * 100 if k["monthly_cost"] else 0.0
    wasteful = k["waste_score"] > 10
    components.kpi_row([
        dict(label="Monthly cost", value=money_short(k["monthly_cost"]), tooltip=money(k["monthly_cost"]),
             tone="info", icon_name="wallet", spark=sparks["demand"],
             delta=f"{money_short(k['potential_savings'])} can be cut", delta_up=False, delta_good=True),
        dict(label="Avg CPU", value=f"{k['avg_util']:.1f}%", tone="info", icon_name="cpu", spark=sparks["cpu"],
             delta=f"{abs(gap):.0f} pts {'below' if gap < 0 else 'above'} {target:.0f}% target",
             delta_up=gap >= 0, delta_good=abs(gap) <= 10),
        dict(label="Waste score", value=f"{k['waste_score']:.1f}%", icon_name="gauge", spark=sparks["idle"],
             tone="warning" if wasteful else "success", delta=f"{k['zombies']} idle · {k['risky']} unhealthy",
             delta_up=wasteful, delta_good=not wasteful),
        dict(label="Potential savings", value=money_short(k["potential_savings"]),
             tooltip=money(k["potential_savings"]), tone="success", icon_name="sparkles", spark=sparks["saving"],
             delta=f"{share:.0f}% of monthly spend", delta_up=True, delta_good=True),
    ])


def priority_rows(result: ScenarioResult) -> list[dict]:
    """Build priority-action rows: unhealthy servers, idle servers, service plans, then oversized servers."""
    profile, rows = result.profile, []
    for _, r in profile[profile["status"] == "Risky"].iterrows():
        rows.append(dict(pill=components.status_pill("Risky"), name=r["name"],
                         detail=f"{r['service']} · unhealthy, fix before scaling down",
                         amount=f"{money(r['monthly_cost'])}/mo", tone="danger"))
    for service, grp in profile[profile["status"] == "Zombie"].groupby("service"):
        rows.append(dict(pill=components.status_pill("Zombie"), name=f"{len(grp)} idle server(s)",
                         detail=f"{service} · switch off", amount=f"{money(grp['monthly_cost'].sum())}/mo",
                         tone="success"))
    for name, sr in sorted(result.services.items(), key=lambda kv: -kv[1].recommendation["savings_monthly"]):
        rec = sr.recommendation
        saving = rec["savings_monthly"]
        if saving == 0:
            continue
        rows.append(dict(pill=components.action_badge(str(rec["action"])), name=name,
                         detail=f"{rec['current']} → {components.server_range(rec['planned_min'], rec['planned_max'])}"
                                f" servers", amount=f"{'+' if saving < 0 else ''}{money(abs(saving))}/mo",
                         tone="success" if saving > 0 else "warning"))
    for service, grp in profile[profile["status"] == "Wasteful"].groupby("service"):
        rows.append(dict(pill=components.status_pill("Wasteful"), name=f"{len(grp)} oversized server(s)",
                         detail=f"{service} · downsize or consolidate",
                         amount=f"{money(grp['wasted_monthly'].sum())}/mo", tone="warning"))
    return rows[:MAX_ACTIONS]


RESOURCE_METRICS = ["CPU", "Memory", "Requests"]


def fleet_usage(result: ScenarioResult) -> pd.DataFrame:
    """Return last-7-day hourly usage of non-zombie servers: mean cpu/mem %, requests and req_pct of capacity."""
    sc, profile = result.scenario, result.profile
    active_ids = set(profile.loc[profile["status"] != "Zombie", "server_id"])
    m = sc.metrics[sc.metrics["server_id"].isin(active_ids)]
    if m.empty:
        return pd.DataFrame(columns=["timestamp", "cpu", "mem", "req_pct", "requests"])
    m = m[m["timestamp"] > m["timestamp"].max() - pd.Timedelta(days=7)]
    capacity = float(sc.servers.loc[sc.servers["server_id"].isin(active_ids), "capacity_rps"].sum())
    hourly = m.groupby("timestamp", as_index=False).agg(cpu=("cpu_pct", "mean"), mem=("mem_pct", "mean"),
                                                        requests=("requests", "sum"))
    hourly["req_pct"] = hourly["requests"] / capacity * 100 if capacity else 0.0
    return hourly


def render_resources(result: ScenarioResult) -> None:
    """Draw the full-width resource-usage card: metric chips, combined % chart and three small charts."""
    usage = fleet_usage(result)
    with st.container(border=True, key="card_resources"):
        components.card_title("Fleet resource usage · last 7 days", "Hourly, non-idle servers. Requests shown as "
                              "% of fleet capacity.", "cpu")
        picked = st.pills("Metrics", RESOURCE_METRICS, selection_mode="multi", default=RESOURCE_METRICS,
                          key="res_metrics", label_visibility="collapsed") or []
        selected = [m for m in RESOURCE_METRICS if m in picked]
        cfg = {"scrollZoom": False, "displayModeBar": False}
        st.plotly_chart(charts.resource_chart(usage, selected), width="stretch", theme=None, config=cfg,
                        key="res_combined")
        if not selected:
            st.caption("Select at least one metric to plot.")
        minis = [("cpu", "CPU %", "CPU", True), ("mem", "Memory %", "Memory", True),
                 ("requests", "Requests per hour", "Requests", False)]
        for col, (field, title, name, pct) in zip(st.columns(3, gap="small"), minis):
            with col:
                st.plotly_chart(charts.mini_chart(usage, field, title, charts.RESOURCE_COLORS[name], pct),
                                width="stretch", theme=None, config=cfg, key=f"res_{field}")
        components.muted_note("Network and storage metrics: next step (real cloud metrics).")


def render(result: ScenarioResult) -> None:
    """Draw the overview page."""
    render_kpis(result)
    render_resources(result)
    left, right = st.columns([2, 1], gap="medium")
    with left:
        with st.container(border=True, key="card_fleet"):
            components.card_title("Fleet capacity overview", "Last 7 days of demand, then the next 7 days against "
                                  "current and planned capacity.", "chart-line",
                                  right=components.status_counts(result.profile["status"].value_counts().to_dict()))
            actual, future = fleet_series(result)
            st.plotly_chart(charts.fleet_capacity_chart(actual, future), width="stretch", theme=None,
                            config={"scrollZoom": False, "displayModeBar": False})
    with right:
        with st.container(border=True, key="card_coverage"):
            components.card_title("Problem statement coverage", "Each line of the brief and where it is solved.",
                                  "check-circle")
            components.problem_coverage(result.scenario.key)
        with st.container(border=True, key="card_actions"):
            components.card_title("Priority actions", "Most urgent first.", "shield-check")
            components.priority_actions(priority_rows(result))
