"""Plain-language explanations of recommendations."""

from engine import config


def explain(service: str, rec: dict, guardrails: list[dict], risk: float) -> str:
    """Return a 2-4 sentence explanation of a recommendation."""
    raise NotImplementedError
