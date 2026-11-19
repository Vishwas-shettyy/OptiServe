"""OptiServe Streamlit entry: sidebar + page router."""

import streamlit as st

from engine import config
from engine.pipeline import ScenarioResult, run_scenario
from ui import forecast_plan, graveyard, overview, styles, time_machine


@st.cache_data
def cached_run(key: str, risk: float) -> ScenarioResult:
    """Cached wrapper around run_scenario."""
    return run_scenario(key, risk)


def main() -> None:
    """Render sidebar and route to the selected page."""
    raise NotImplementedError


if __name__ == "__main__":
    main()
