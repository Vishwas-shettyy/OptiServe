"""Server Graveyard page: tombstones for wasteful servers plus a formal table."""

import pandas as pd
import streamlit as st

from engine.pipeline import ScenarioResult
from ui import components
from ui.components import money, money_short

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
    components.table_card("All servers", ["Server", "Status", "Avg CPU", "Peak CPU", "Cost / month",
                                          "Wasted / month", "Action"], rows, numeric=(2, 3, 4, 5))
    st.download_button("Download as CSV", csv_table(profile).to_csv(index=False).encode("utf-8"),
                       file_name=f"optiserve_servers_{key}.csv", mime="text/csv", icon=":material/download:")


def render(result: ScenarioResult) -> None:
    """Draw the Server Graveyard page."""
    sc, profile = result.scenario, result.profile
    components.page_header("Server Graveyard", "Servers that cost money without earning it, and what to do.",
                           sc.title)
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
    counts = _counts(profile)
    components.kpi_row([
        dict(label="Wasted / month", value=money_short(wasted), hint="Idle + oversized capacity",
             tone="warning" if wasted else "success", tooltip=money(wasted)),
        dict(label="R.I.P. (idle)", value=str(counts.get("Zombie", 0)), hint="Safe to switch off",
             tone="neutral"),
        dict(label="On notice", value=str(counts.get("Wasteful", 0)), hint="Oversized for their load"),
        dict(label="Do not bury", value=str(counts.get("Risky", 0)), hint="Unhealthy: fix first",
             tone="danger" if counts.get("Risky") else "neutral"),
    ])
    view = st.segmented_control("View", VIEWS, default=VIEWS[0], required=True, label_visibility="collapsed",
                                key="graveyard_view")
    if view == "Formal view":
        formal_view(profile, sc.key)
    else:
        graveyard_view(profile)
