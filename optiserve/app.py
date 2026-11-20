"""OptiServe Streamlit entry: glass top header, controls and page router."""

from datetime import datetime

import pandas as pd
import streamlit as st

from engine import config
from engine.data_gen import list_scenarios
from engine.pipeline import ScenarioResult, run_scenario
from ui import approvals, charts, components, forecast_plan, graveyard, overview, styles, time_machine  # noqa: F401  (charts registers the Plotly template)

PAGES = [
    ("Overview", "overview", ":material/dashboard:", overview.render),
    ("Forecast & Plan", "forecast", ":material/show_chart:", forecast_plan.render),
    ("Server Graveyard", "graveyard", ":material/inventory_2:", graveyard.render),
    ("Time Machine", "time-machine", ":material/history:", time_machine.render),
]


@st.cache_data(show_spinner="Running scenario…")
def cached_run(key: str, risk: float) -> ScenarioResult:
    """Cached wrapper around run_scenario."""
    return run_scenario(key, risk)


def plan_csv(result: ScenarioResult) -> bytes:
    """Return the hourly server plan of every service as a readable CSV."""
    frames = [sr.plan.assign(service=name) for name, sr in result.services.items() if not sr.plan.empty]
    if not frames:
        return b"service,hour,current servers,planned servers\n"
    df = pd.concat(frames)[["service", "timestamp", "current", "planned", "needed_raw"]]
    df = df.rename(columns={"timestamp": "hour", "current": "current servers", "planned": "planned servers",
                            "needed_raw": "servers needed before safety checks"})
    return df.to_csv(index=False).encode("utf-8")


def header(result: ScenarioResult, pages: list, current: object) -> None:
    """Draw the sticky glass header (brand, scenario, export, date/time, centred nav) and the alert ticker."""
    now = datetime.now()
    with st.container(key="os_header"):
        with st.container(key="os_top", horizontal=True, vertical_alignment="center", gap="small"):
            with st.container(key="os_brand", width="stretch"):
                components.brand_block()
            with st.container(key="os_right", horizontal=True, vertical_alignment="center", width="content"):
                components.scenario_chip(result.scenario.title)
                st.download_button("Export report", plan_csv(result), file_name=f"optiserve_plan_{result.scenario.key}.csv",
                                   mime="text/csv", icon=":material/download:", key="export_report")
                components.datetime_block(f"{now:%a %d %b}", f"{now:%H:%M}")
        with st.container(key="os_nav", horizontal=True, horizontal_alignment="center", gap="small"):
            for page in pages:
                active = page.title == current.title
                with st.container(key="nav_active" if active else f"nav_{page.url_path or 'home'}", width="content"):
                    st.page_link(page)
            with st.container(key="os_pending", width="content"):
                components.pending_badge(approvals.pending_count(result))
    components.alert_ticker(result.alerts)


def controls(titles: dict[str, str], scenario_key: str) -> None:
    """Draw the glass control panel: dataset selector, risk slider and mode, then the problem-statement note."""
    with st.container(key="os_controls"):
        scen, risk, label = st.columns([3.4, 3, 1], vertical_alignment="center")
        with scen:
            components.dataset_label(len(titles))
            st.selectbox("Dataset", list(titles), format_func=lambda k: titles[k], key="scenario",
                         label_visibility="collapsed")
        with risk:
            st.slider("Cost focus ⟷ Safety focus", 0.0, 1.0, step=0.05, key="risk")
        with label:
            components.risk_pill(config.risk_label(st.session_state["risk"]))
        components.problem_strip(scenario_key)


def main() -> None:
    """Render header, controls and the selected page."""
    st.set_page_config(page_title="OptiServe · Capacity Command Center", page_icon="◆", layout="wide",
                       initial_sidebar_state="collapsed")
    styles.inject_css()
    titles = dict(list_scenarios())
    st.session_state.setdefault("scenario", "office_hours" if "office_hours" in titles else next(iter(titles)))
    st.session_state.setdefault("risk", config.DEFAULT_RISK)
    result = cached_run(st.session_state["scenario"], round(float(st.session_state["risk"]), 2))
    pages = [st.Page(lambda fn=fn: fn(result), title=title, url_path=path, icon=icon, default=i == 0)
             for i, (title, path, icon, fn) in enumerate(PAGES)]
    current = st.navigation(pages, position="hidden")
    header(result, pages, current)
    controls(titles, result.scenario.key)
    current.run()


if __name__ == "__main__":
    main()
