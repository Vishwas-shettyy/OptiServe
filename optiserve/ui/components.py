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


# ---- formatting -------------------------------------------------------------

CURRENCY = "₹"
CHECK_ICONS: dict[str, str] = {"pass": "✅", "adjusted": "🟡", "blocked": "⛔"}
CHECK_LABELS: dict[str, str] = {"pass": "Passed", "adjusted": "Adjusted", "blocked": "Blocked"}
CHECK_TONES: dict[str, str] = {"pass": "success", "adjusted": "warning", "blocked": "danger"}
RISK_PILL_COLORS: dict[str, str] = {"Cheapest": "#FBBF24", "Balanced": "#60A5FA", "Safest": "#4ADE80"}


def money(value: float) -> str:
    """Format a rupee amount like ₹12,345."""
    sign = "-" if value < 0 else ""
    return f"{sign}{CURRENCY}{abs(value):,.0f}"


def money_short(value: float) -> str:
    """Format a rupee amount compactly, like ₹46.5K or ₹1.2M."""
    for size, suffix in ((1e6, "M"), (1e3, "K")):
        if abs(value) >= size:
            sign = "-" if value < 0 else ""
            return f"{sign}{CURRENCY}{abs(value) / size:.1f}{suffix}"
    return money(value)


def server_range(lo: int, hi: int) -> str:
    """Format a server range, collapsing it when min equals max."""
    return str(lo) if lo == hi else f"{lo}–{hi}"


# ---- sidebar ----------------------------------------------------------------

def sidebar_brand() -> None:
    """Render the logo mark, product name and subtitle."""
    _md('<div class="os-logo"><span class="mark">O</span>OptiServe</div>'
        '<div class="os-sub">Capacity-planning copilot</div>')


def sidebar_label(text: str) -> None:
    """Render a small uppercase label in the sidebar."""
    _md(f'<div class="os-side-label">{_e(text)}</div>')


def risk_pill(label: str) -> None:
    """Render the live risk-mode label as a pill under the slider."""
    color = RISK_PILL_COLORS.get(label, "#60A5FA")
    _md(f'<div class="os-risk">Mode <span class="os-pill" style="color:{color};background:{tint(color, .16)}">'
        f'<span class="dot"></span>{_e(label)}</span></div>')


def sidebar_footer(text: str) -> None:
    """Render the muted footer note."""
    _md(f'<div class="os-footer">{_e(text)}</div>')


# ---- cards ------------------------------------------------------------------

def _saving_html(savings: float, pct: float) -> tuple[str, str, str]:
    """Return (label, value, colour) describing a monthly saving or extra cost."""
    if savings > 0:
        return "Saving / month", f"{money(savings)} ({pct:.0f}%)", TONE_COLORS["success"]
    if savings < 0:
        return "Extra cost / month", f"{money(-savings)} ({abs(pct):.0f}%)", TONE_COLORS["warning"]
    return "Saving / month", f"{CURRENCY}0", TEXT_2


def recommendation_card(service: str, action: str, current: int, planned_min: int, planned_max: int,
                        savings: float, savings_pct: float, explanation: str = "", title: str = "") -> None:
    """Render a recommendation card: name, action badge, current → planned servers, ₹ saving, explanation."""
    label, value, color = _saving_html(savings, savings_pct)
    head = _e(title or service)
    why = f'<p>{_e(explanation)}</p>' if explanation else ""
    _md(f'<div class="os-card os-rec"><div class="head"><span class="name">{head}</span>{action_badge(action)}</div>'
        f'<div class="stats"><div class="stat"><div class="label">Servers</div>'
        f'<div class="value">{current} → {_e(server_range(planned_min, planned_max))}</div></div>'
        f'<div class="stat"><div class="label">{_e(label)}</div>'
        f'<div class="value" style="color:{color}">{_e(value)}</div></div></div>{why}</div>')


def text_card(title: str, text: str) -> None:
    """Render a white card with a title and one paragraph."""
    _md(f'<div class="os-card"><h4>{_e(title)}</h4><p>{_e(text)}</p></div>')


def checklist(title: str, items: Sequence[dict]) -> None:
    """Render safety checks as a vertical checklist; each item has rule, status and message."""
    rows = "".join(
        f'<div class="os-check"><span class="icon">{CHECK_ICONS.get(it["status"], "•")}</span><div>'
        f'<div class="rule">{_e(it["rule"])}<span class="state" '
        f'style="color:{_tone(CHECK_TONES.get(it["status"], "neutral"))}">'
        f'{_e(CHECK_LABELS.get(it["status"], it["status"]))}</span></div>'
        f'<div class="msg">{_e(it["message"])}</div></div></div>'
        for it in items
    )
    _md(f'<div class="os-card"><h4>{_e(title)}</h4>{rows}</div>')


def alerts_feed(alerts: Sequence[dict]) -> None:
    """Render alerts critical → info, or a calm empty state."""
    order = {"critical": 0, "warning": 1, "info": 2}
    if not alerts:
        _md('<div class="os-alert os-alert-row" style="border-left-color:#16A34A"><span class="icon">✅</span>'
            '<div>No alerts — the fleet looks healthy.</div></div>')
        return
    for a in sorted(alerts, key=lambda a: order.get(a["severity"], 9)):
        alert_row(a["severity"], a["service"], a["message"])


# ---- Server Graveyard ----------------------------------------------------------

EPITAPHS: dict[str, str] = {"Zombie": "R.I.P.", "Wasteful": "On notice", "Risky": "Do not bury"}
STATUS_PILL_ON_DARK: dict[str, str] = {"Zombie": "#C4B5FD", "Wasteful": "#FCD34D", "Risky": "#FCA5A5",
                                       "Hot": "#FDBA74", "Right-sized": "#86EFAC"}


def tombstone(name: str, instance_type: str, service: str, status: str, cost: float, idle_since: str,
              reason: str) -> str:
    """Return HTML for one tombstone; hovering shows the reason."""
    color = STATUS_COLORS.get(status, TEXT_2)
    return (f'<div class="os-stone" title="{_e(reason)}" style="border-top:3px solid {color}">'
            f'<div class="epitaph">{_e(EPITAPHS.get(status, status))}</div>'
            f'<div class="name">{_e(name)}</div>'
            f'<div class="meta">{_e(instance_type)} · {_e(service)}</div>'
            f'<div class="cost">{_e(money(cost))}/mo</div>'
            f'<div class="meta">{_e(idle_since)}</div>'
            f'<div class="pill-wrap">{pill(status, STATUS_PILL_ON_DARK.get(status, color))}</div></div>')


def night_scene(total_wasted: float, counts: dict[str, int], stones: Sequence[str]) -> None:
    """Render the dark night-scene panel with its waste banner and a grid of tombstones."""
    parts = " · ".join(f"{n} {EPITAPHS.get(s, s).lower()}" for s, n in counts.items())
    body = "".join(stones) or '<div class="os-empty-yard">The yard is empty — every server is earning its keep.</div>'
    _md(f'<div class="os-sky"><div class="os-moon"></div><div class="os-banner">'
        f'<div class="small">Wasted every month</div><div class="big">{_e(money(total_wasted))}</div>'
        f'<div class="small">{len(stones)} server(s) in the yard — {_e(parts)}</div></div>'
        f'<div class="os-yard">{body}</div><div class="os-hint">Hover a stone to see why it is here.</div></div>')


def table_card(title: str, headers: Sequence[str], rows: Sequence[Sequence[str]], numeric: Sequence[int] = ()) -> None:
    """Render a white table card; cells are pre-built HTML, `numeric` column indexes align right."""
    def cls(i: int) -> str:
        """Return the CSS class for column i."""
        return ' class="num"' if i in numeric else ""
    head = "".join(f"<th{cls(i)}>{_e(h)}</th>" for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(f"<td{cls(i)}>{c}</td>" for i, c in enumerate(r)) + "</tr>" for r in rows)
    _md(f'<div class="os-card os-table-card"><h4>{_e(title)}</h4><div class="os-table-wrap">'
        f'<table class="os-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></div>')


def esc(text: object) -> str:
    """Escape text for use as a table cell."""
    return _e(text)


# ---- Time Machine -----------------------------------------------------------------

def _delta(fixed: float, plan: float, fmt: str) -> str:
    """Return a green (better) or red (worse) delta chip; lower is better."""
    diff = plan - fixed
    if abs(diff) < 1e-9:
        return f'<span class="delta" style="color:{TEXT_2}">no change</span>'
    color = TONE_COLORS["success"] if diff < 0 else TONE_COLORS["danger"]
    arrow = "▼" if diff < 0 else "▲"
    value = money(abs(diff)) if fmt == "money" else f"{abs(diff):,.0f} h"
    return f'<span class="delta" style="color:{color};background:{tint(color)}">{arrow} {_e(value)}</span>'


def before_after(metrics: Sequence[tuple[str, float, float, str]]) -> None:
    """Render the Before vs After split card; each metric is (label, fixed, optiserve, 'money'|'hours')."""
    def fmt(v: float, kind: str) -> str:
        """Format one metric value."""
        return money(v) if kind == "money" else f"{v:,.0f}"
    left = "".join(f'<div class="m"><div class="label">{_e(l)}</div><div class="value">{_e(fmt(f, k))}</div></div>'
                   for l, f, _, k in metrics)
    right = "".join(f'<div class="m"><div class="label">{_e(l)}</div><div class="value">{_e(fmt(p, k))}'
                    f'{_delta(f, p, k)}</div></div>' for l, f, p, k in metrics)
    _md(f'<div class="os-card os-split"><div class="side"><div class="tag">Before · Fixed setup</div>{left}</div>'
        f'<div class="side after"><div class="tag">After · OptiServe</div>{right}</div></div>')


def compare_bars(title: str, rows: Sequence[tuple[str, float, str]], note: str) -> None:
    """Render a card of horizontal percentage bars; rows are (label, percent, colour), lower is better."""
    top = max([v for _, v, _ in rows] + [1e-9])
    bars = "".join(f'<div class="os-bar-row"><div class="lbl"><span>{_e(l)}</span><b>{v:.1f}%</b></div>'
                   f'<div class="track"><div class="fill" style="width:{v / top * 100:.0f}%;background:{c}"></div>'
                   f'</div></div>' for l, v, c in rows)
    _md(f'<div class="os-card"><h4>{_e(title)}</h4>{bars}<p class="os-note">{_e(note)}</p></div>')
