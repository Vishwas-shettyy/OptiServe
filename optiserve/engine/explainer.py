"""Plain-language explanations of recommendations."""

from engine import config


def explain(service: str, rec: dict, guardrails: list[dict], risk: float) -> str:
    """Return a 2-4 sentence explanation of a recommendation."""
    savings = rec["savings_monthly"]
    if savings >= 0:
        money = f"Saves {config.CURRENCY}{savings:,.0f}/month ({rec['savings_pct']:.0f}%)."
    else:
        money = f"Costs {config.CURRENCY}{-savings:,.0f}/month more ({-rec['savings_pct']:.0f}%) to stay safe."
    sentences = [
        f"{service}: run {rec['planned_min']}–{rec['planned_max']} servers instead of a fixed {rec['current']}.",
        f"Busiest hour {rec['peak_time']:%a %d %b %H:%M} needs {rec['peak_servers']}.",
        money,
        f"Risk setting: {config.risk_label(risk)}.",
    ]
    for rule in guardrails:
        if rule["status"] in ("blocked", "adjusted"):
            sentences.append(f"{rule['rule']}: {rule['message']}")
    return " ".join(sentences)
