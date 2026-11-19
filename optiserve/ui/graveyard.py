"""Server Graveyard page (placeholder)."""

import streamlit as st

from engine.pipeline import ScenarioResult


def render(result: ScenarioResult) -> None:
    """Draw a 'coming next' placeholder for the Server Graveyard page."""
    st.title("Server Graveyard")
    st.markdown('<div class="os-card os-placeholder"><h4>Coming next</h4>'
                '<p>This page is under construction.</p></div>', unsafe_allow_html=True)
