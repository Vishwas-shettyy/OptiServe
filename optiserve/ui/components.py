"""Reusable HTML components for the design system. All text is escaped with html.escape."""

import html
from collections.abc import Sequence

import streamlit as st

from ui.styles import ACCENT, MUTED, SEVERITY_COLORS, STATUS_COLORS, TEXT_2, TONE_COLORS, tint

ACTION_LABELS: dict[str, str] = {
    "scale_down": "Reduce servers", "scale_up": "Add servers", "schedule": "Smart schedule", "hold": "Keep as is",
}
ACTION_TONES: dict[str, str] = {"scale_down": "success", "scale_up": "warning", "schedule": "info", "hold": "neutral"}
TONE_ICONS: dict[str, str] = {"info": "💡", "success": "✅", "warning": "⚠️", "danger": "⛔", "neutral": "ℹ️"}
SEVERITY_ICONS: dict[str, str] = {"critical": "⛔", "warning": "⚠️", "info": "ℹ️"}


def _e(text: object) -> str:
    """Escape any value for safe HTML output."""
    return html.escape(str(text))


def _md(markup: str) -> None:
    """Render raw HTML markup."""
    st.markdown(markup, unsafe_allow_html=True)


def _tone(tone: str) -> str:
    """Return the colour for a tone name, defaulting to info."""
    return TONE_COLORS.get(tone, ACCENT)


def pill(text: str, color: str) -> str:
    """Return HTML for a tinted pill with a dot in the given colour."""
    return (f'<span class="os-pill" style="color:{color};background:{tint(color)}">'
            f'<span class="dot"></span>{_e(text)}</span>')


def status_pill(status: str) -> str:
    """Return HTML for a server-status pill in its status colour."""
    return pill(status, STATUS_COLORS.get(status, TEXT_2))


def action_badge(action: str) -> str:
    """Return HTML for an action badge with its plain-language label."""
    label = ACTION_LABELS.get(action, action.replace("_", " ").capitalize())
    return pill(label, _tone(ACTION_TONES.get(action, "neutral")))


def glossary_tip(term: str, text: str) -> str:
    """Return HTML for a term with a dotted underline and a hover explanation."""
    return f'<span class="os-tip" title="{_e(text)}">{_e(term)}</span>'


def page_header(title: str, subtitle: str = "", chip: str = "") -> None:
    """Render the page title, one-line subtitle and a scenario chip on the right."""
    sub = f'<div class="subtitle">{_e(subtitle)}</div>' if subtitle else ""
    right = pill(chip, ACCENT) if chip else ""
    _md(f'<div class="os-header"><div><div class="title">{_e(title)}</div>{sub}</div><div>{right}</div></div>')


def insight_banner(text: str, tone: str = "info") -> None:
    """Render a one-sentence insight banner in the given tone (info, success, warning, danger, neutral)."""
    color = _tone(tone)
    _md(f'<div class="os-banner-insight" style="background:{tint(color, .07)};border-color:{tint(color, .28)}">'
        f'<span class="icon">{TONE_ICONS.get(tone, "💡")}</span><span>{_e(text)}</span></div>')


def kpi_html(label: str, value: str, hint: str = "", tone: str = "neutral", tooltip: str = "") -> str:
    """Return HTML for one KPI card; tooltip shows on hover over the value."""
    tip = f' title="{_e(tooltip)}"' if tooltip else ""
    top = _tone(tone) if tone != "neutral" else "#E6E8EF"
    return (f'<div class="os-kpi" style="--tone:{top}"><div class="label">{_e(label)}</div>'
            f'<div class="value"{tip}>{_e(value)}</div><div class="hint">{_e(hint)}</div></div>')


def kpi_card(label: str, value: str, hint: str = "", tone: str = "neutral", tooltip: str = "") -> None:
    """Render one KPI card."""
    _md(kpi_html(label, value, hint, tone, tooltip))


def kpi_row(items: Sequence[dict | Sequence]) -> None:
    """Render KPI cards in a responsive row; each item is a dict or (label, value, hint, tone, tooltip) tuple."""
    cards = [kpi_html(**it) if isinstance(it, dict) else kpi_html(*it) for it in items]
    _md(f'<div class="os-kpi-row">{"".join(cards)}</div>')


def alert_row(severity: str, service: str, message: str) -> None:
    """Render one alert row coloured and iconed by severity."""
    color = SEVERITY_COLORS.get(severity, MUTED)
    _md(f'<div class="os-alert os-alert-row" style="border-left-color:{color}">'
        f'<span class="icon">{SEVERITY_ICONS.get(severity, "•")}</span><div>'
        f'<span class="sev" style="color:{color}">{_e(severity)}</span>'
        f'<b>{_e(service)}</b> — {_e(message)}</div></div>')


def section(title: str, help: str = "") -> None:
    """Render a section title with an optional one-line help text."""
    sub = f'<div class="help">{_e(help)}</div>' if help else ""
    _md(f'<div class="os-section"><div class="title">{_e(title)}</div>{sub}</div>')
