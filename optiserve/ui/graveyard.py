"""Server Graveyard page: tombstones for wasteful servers plus a formal table."""

import pandas as pd
import streamlit as st

from engine.pipeline import ScenarioResult
from ui import charts, components
from ui.components import money, money_short
from ui.styles import STATUS_COLORS

SPARK_DAYS = 14

BURIED = ["Zombie", "Wasteful", "Risky"]
VIEWS = ["Graveyard view", "Formal view"]
ACTIONS = {
    "Zombie": "Switch off",
    "Wasteful": "Downsize or consolidate",
    "Risky": "Fix health — do not remove",
    "Hot": "Add capacity",
    "Right-sized": "Keep",
}
CSV_COLUMNS = {
    "name": "Server", "service": "Service", "instance_type": "Instance type", "status": "Status",
    "avg_cpu": "Avg CPU %", "p95_cpu": "Peak CPU %", "monthly_cost": "Cost per month (₹)",
    "wasted_monthly": "Wasted per month (₹)", "action": "Recommended action", "reason": "Reason",
}


def _since(value: pd.Timestamp) -> str:
    """Describe when the server went idle."""
    return f"Idle since {value:%d %b %Y}" if pd.notna(value) else "Still serving traffic"


def _counts(profile: pd.DataFrame) -> dict[str, int]:
    """Return the number of buried servers per status, skipping empty statuses."""
    return {s: int((profile["status"] == s).sum()) for s in BURIED if (profile["status"] == s).any()}


def graveyard_view(profile: pd.DataFrame) -> None:
    """Draw the night-scene graveyard of Zombie, Wasteful and Risky servers."""
    stones = profile[profile["status"].isin(BURIED)].sort_values("wasted_monthly", ascending=False)
    cards = [components.tombstone(r["name"], r["instance_type"], r["service"], r["status"],
                                  float(r["monthly_cost"]), _since(r["idle_since"]), r["reason"])
             for _, r in stones.iterrows()]
    components.night_scene(float(stones["wasted_monthly"].sum()), _counts(profile), cards)


def csv_table(profile: pd.DataFrame) -> pd.DataFrame:
    """Return the readable server table used for the CSV download."""
    df = profile.assign(action=profile["status"].map(ACTIONS)).sort_values("wasted_monthly", ascending=False)
    df = df[list(CSV_COLUMNS)].rename(columns=CSV_COLUMNS)
    for col in ("Avg CPU %", "Peak CPU %", "Cost per month (₹)", "Wasted per month (₹)"):
        df[col] = df[col].round(1)
    return df.reset_index(drop=True)


def formal_view(profile: pd.DataFrame, key: str) -> None:
    """Draw the formal table of all servers with a CSV download."""
    df = profile.sort_values("wasted_monthly", ascending=False)
    rows = [[f"<b>{components.esc(r['name'])}</b><div class=\"sub\">{components.esc(r['service'])} · "
             f"{components.esc(r['instance_type'])}</div>", components.status_pill(r["status"]), f"{r['avg_cpu']:.1f}%", f"{r['p95_cpu']:.1f}%",
             components.esc(money(r["monthly_cost"])), components.esc(money(r["wasted_monthly"])),
             components.esc(ACTIONS.get(r["status"], "Keep"))] for _, r in df.iterrows()]
    components.card_title("All servers", "Every server with its load, cost and recommended action.", "server")
    components.table_card("", ["Server", "Status", "Avg CPU", "Peak CPU", "Cost / month",
                                          "Wasted / month", "Action"], rows, numeric=(2, 3, 4, 5))
    st.download_button("Download as CSV", csv_table(profile).to_csv(index=False).encode("utf-8"),
                       file_name=f"optiserve_servers_{key}.csv", mime="text/csv", icon=":material/download:")


def status_sparks(result: ScenarioResult) -> dict[str, list[float]]:
    """Return daily sparklines: CPU of all buried servers and per status, error rate % of unhealthy ones."""
    profile, metrics = result.profile, result.scenario.metrics
    recent = metrics[metrics["timestamp"] > metrics["timestamp"].max() - pd.Timedelta(days=SPARK_DAYS)]
    recent = recent.assign(err_pct=recent["error_rate"] * 100)

    def of(statuses: list[str], col: str = "cpu_pct") -> list[float]:
        """Daily mean of `col` for servers with the given statuses."""
        ids = set(profile.loc[profile["status"].isin(statuses), "server_id"])
        return charts.daily(recent[recent["server_id"].isin(ids)], col, "mean")
    return {"all": of(BURIED), "Zombie": of(["Zombie"]), "Wasteful": of(["Wasteful"]),
            "Risky": of(["Risky"], "err_pct")}


def render_kpis(result: ScenarioResult) -> None:
    """Draw wasted money and the three tombstone counts with icons, deltas and sparklines."""
    profile, sparks = result.profile, status_sparks(result)
    counts = _counts(profile)
    wasted = float(profile.loc[profile["status"].isin(BURIED), "wasted_monthly"].sum())
    fleet = float(profile["monthly_cost"].sum())
    zombie_cost = float(profile.loc[profile["status"] == "Zombie", "monthly_cost"].sum())
    oversized = float(profile.loc[profile["status"] == "Wasteful", "wasted_monthly"].sum())
    risky = profile[profile["status"] == "Risky"]
    n_z, n_w, n_r = counts.get("Zombie", 0), counts.get("Wasteful", 0), counts.get("Risky", 0)
    components.kpi_row([
        dict(label="Wasted / month", value=money_short(wasted), tooltip=money(wasted), icon_name="flame",
             tone="warning" if wasted else "success", spark=sparks["all"],
             delta=f"{wasted / fleet * 100:.0f}% of fleet spend" if wasted and fleet else "Nothing wasted",
             delta_up=wasted > 0, delta_good=not wasted),
        dict(label="R.I.P. (idle)", value=str(n_z), icon_name="gravestone", tone=STATUS_COLORS["Zombie"],
             spark=sparks["Zombie"], delta=f"{money_short(zombie_cost)}/mo if switched off" if n_z else "No idle servers",
             delta_up=False, delta_good=True),
        dict(label="On notice", value=str(n_w), icon_name="alert-triangle", tone=STATUS_COLORS["Wasteful"],
             spark=sparks["Wasteful"], delta=f"{money_short(oversized)}/mo oversized" if n_w else "None oversized",
             delta_up=bool(n_w), delta_good=None if n_w else True),
        dict(label="Do not bury", value=str(n_r), icon_name="heart-pulse",
             tone=STATUS_COLORS["Risky"] if n_r else "success", spark=sparks["Risky"],
             delta=f"{risky['err_24h'].max() * 100:.1f}% errors · fix first" if n_r else "All servers healthy",
             delta_up=bool(n_r), delta_good=not n_r),
    ])


def render(result: ScenarioResult) -> None:
    """Draw the Server Graveyard page."""
    sc, profile = result.scenario, result.profile
    components.page_header("Server Graveyard", "Servers that cost money without earning it, and what to do.",
                           icon_name="gravestone")
    buried = profile[profile["status"].isin(BURIED)]
    wasted = float(buried["wasted_monthly"].sum())
    risky = buried.loc[buried["status"] == "Risky", "name"].tolist()
    if buried.empty:
        components.insight_banner("No idle, oversized or unhealthy servers: the yard is empty.", "success")
    elif wasted <= 0:
        components.insight_banner(f"No money wasted, but {', '.join(risky)} is unhealthy: fix it, do not remove it.",
                                  "danger")
    else:
        tail = f" Never remove {', '.join(risky)}: it is unhealthy." if risky else " Switch off the R.I.P. ones first."
        components.insight_banner(f"{len(buried)} server(s) waste {money(wasted)}/month.{tail}",
                                  "danger" if risky else "warning")
    render_kpis(result)
    view = st.segmented_control("View", VIEWS, default=VIEWS[0], required=True, label_visibility="collapsed",
                                key="graveyard_view")
    if view == "Formal view":
        with st.container(border=True, key="card_formal"):
            formal_view(profile, sc.key)
    else:
        with st.container(border=True, key="card_yard"):
            components.card_title("The yard", "Idle, oversized and unhealthy servers, most wasteful first.",
                                  "gravestone", right=components.status_counts(_counts(profile)))
            graveyard_view(profile)
