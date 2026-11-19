"""Glue: run a full scenario end to end."""

from dataclasses import dataclass, field

import pandas as pd

from engine import backtest, config, data_gen, explainer, forecaster, guardrails, planner, profiler
from engine.data_gen import Scenario


@dataclass
class ServiceResult:
    """All outputs for one service."""

    service: str
    history: pd.DataFrame
    forecast: pd.DataFrame
    plan: pd.DataFrame
    guardrails: list[dict] = field(default_factory=list)
    recommendation: dict = field(default_factory=dict)
    explanation: str = ""
    backtest: dict = field(default_factory=dict)
    anomalies: list[dict] = field(default_factory=list)


@dataclass
class ScenarioResult:
    """All outputs for one scenario run."""

    scenario: Scenario
    risk: float
    profile: pd.DataFrame
    services: dict[str, ServiceResult] = field(default_factory=dict)
    alerts: list[dict] = field(default_factory=list)
    kpis: dict = field(default_factory=dict)


def run_scenario(key: str, risk: float = config.DEFAULT_RISK) -> ScenarioResult:
    """Run the full pipeline for one scenario."""
    raise NotImplementedError


def main() -> None:
    """Print one summary block per scenario."""
    raise NotImplementedError


if __name__ == "__main__":
    main()
