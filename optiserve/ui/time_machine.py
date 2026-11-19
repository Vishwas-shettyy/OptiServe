"""time_machine page."""

import plotly.graph_objects as go
import streamlit as st

from engine import config
from engine.pipeline import ScenarioResult


def render(result: ScenarioResult) -> None:
    """Draw the time_machine page."""
    raise NotImplementedError
