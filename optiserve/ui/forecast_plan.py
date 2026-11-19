"""Forecast & Plan page (placeholder)."""

import streamlit as st

from engine.pipeline import ScenarioResult


def render(result: ScenarioResult) -> None:
    """Draw a 'coming next' placeholder for the Forecast & Plan page."""
    st.title("Forecast & Plan")
    st.markdown('<div class="os-card os-placeholder"><h4>Coming next</h4>'
                '<p>This page is under construction.</p></div>', unsafe_allow_html=True)
