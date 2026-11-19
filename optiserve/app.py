"""OptiServe Streamlit entry: sidebar + page router."""

import html

import streamlit as st

from engine import config
from engine.data_gen import list_scenarios
from engine.pipeline import ScenarioResult, run_scenario
from ui import charts, forecast_plan, graveyard, overview, styles, time_machine  # noqa: F401  (charts registers the Plotly template)

PAGES = {
    "Overview": overview.render,
    "Forecast & Plan": forecast_plan.render,
    "Server Graveyard": graveyard.render,
    "Time Machine": time_machine.render,
}


@st.cache_data(show_spinner="Running scenario…")
def cached_run(key: str, risk: float) -> ScenarioResult:
    """Cached wrapper around run_scenario."""
    return run_scenario(key, risk)


def sidebar() -> tuple[str, float, str]:
    """Draw the sidebar and return (scenario key, risk, page name)."""
    scenarios = dict(list_scenarios())
    with st.sidebar:
        st.markdown('<div class="os-logo"><span class="mark">O</span>OptiServe</div>'
                    '<div class="os-sub">Capacity-planning copilot</div>',
                    unsafe_allow_html=True)
        key = st.selectbox("Scenario", list(scenarios), format_func=lambda k: scenarios[k])
        risk = st.slider("Risk setting", 0.0, 1.0, config.DEFAULT_RISK, 0.05)
        st.caption(f"Mode: **{html.escape(config.risk_label(risk))}**")
        page = st.radio("Page", list(PAGES))
        st.markdown('<div class="os-footer">Synthetic data modelled on public cluster-trace patterns</div>',
                    unsafe_allow_html=True)
    return key, float(risk), page


def main() -> None:
    """Render sidebar and route to the selected page."""
    st.set_page_config(page_title="OptiServe", layout="wide", initial_sidebar_state="expanded")
    styles.inject_css()
    key, risk, page = sidebar()
    PAGES[page](cached_run(key, round(risk, 2)))


if __name__ == "__main__":
    main()
