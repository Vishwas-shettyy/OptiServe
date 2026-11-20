"""Reusable HTML components for the design system. All text is escaped with html.escape."""

import html
from collections.abc import Sequence

import streamlit as st

from ui.icons import icon
from ui.styles import ACCENT, MUTED, SEVERITY_COLORS, STATUS_COLORS, TEXT_2, TONE_COLORS, tint

ACTION_LABELS: dict[str, str] = {
    "scale_down": "Reduce servers", "scale_up": "Add servers", "schedule": "Smart schedule", "hold": "Keep as is",
}
ACTION_TONES: dict[str, str] = {"scale_down": "success", "scale_up": "warning", "schedule": "info", "hold": "neutral"}
TONE_ICONS: dict[str, str] = {"info": "sparkles", "success": "check-circle", "warning": "alert-triangle",
                              "danger": "octagon-x", "neutral": "info"}
SEVERITY_ICONS: dict[str, str] = {"critical": "octagon-x", "warning": "alert-triangle", "info": "info"}
CURRENCY = "₹"
CHECK_ICONS: dict[str, str] = {"pass": "check-circle", "adjusted": "alert-circle", "blocked": "octagon-x"}
CHECK_LABELS: dict[str, str] = {"pass": "Passed", "adjusted": "Adjusted", "blocked": "Blocked"}
CHECK_TONES: dict[str, str] = {"pass": "success", "adjusted": "warning", "blocked": "danger"}
RISK_TONES: dict[str, str] = {"Cheapest": "warning", "Balanced": "info", "Safest": "success"}


def _e(text: object) -> str:
    """Escape any value for safe HTML output."""
    return html.escape(str(text))


def _md(markup: str) -> None:
    """Render raw HTML markup."""
    st.markdown(markup, unsafe_allow_html=True)


def _tone(tone: str) -> str:
    """Return the colour for a tone name (or a #hex colour), defaulting to info."""
    return tone if tone.startswith("#") else TONE_COLORS.get(tone, ACCENT)


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


def page_header(title: str, subtitle: str = "", chip: str = "", icon_name: str = "") -> None:
    """Render the page title with an optional icon tile, a one-line subtitle and an optional chip on the right."""
    sub = f'<div class="subtitle">{_e(subtitle)}</div>' if subtitle else ""
    tile = f'<span class="tile">{icon(icon_name, 22)}</span>' if icon_name else ""
    right = f"<div>{pill(chip, ACCENT)}</div>" if chip else ""
    _md(f'<div class="os-header"><div class="lead">{tile}<div><div class="title">{_e(title)}</div>{sub}</div></div>'
        f'{right}</div>')


def insight_banner(text: str, tone: str = "info") -> None:
    """Render a one-sentence insight banner in the given tone (info, success, warning, danger, neutral)."""
    color = _tone(tone)
    _md(f'<div class="os-banner-insight" style="background:{tint(color, .07)};border-color:{tint(color, .28)}">'
        f'<span class="icon" style="color:{color}">{icon(TONE_ICONS.get(tone, "info"))}</span>'
        f'<span>{_e(text)}</span></div>')


# ---- KPI cards ----------------------------------------------------------------

def sparkline(values: Sequence[float], color: str, width: int = 72, height: int = 28) -> str:
    """Return a small inline SVG sparkline (line + soft area) for a series of numbers."""
    vals = [float(v) for v in values if v == v]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    pts = [(i * width / (len(vals) - 1), height - 3 - (v - lo) / span * (height - 6)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"0,{height} {line} {width},{height}"
    return (f'<svg class="os-spark" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="none" aria-hidden="true"><polygon points="{area}" fill="{tint(color, .12)}"/>'
            f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="1.75" '
            f'stroke-linejoin="round" stroke-linecap="round"/></svg>')


def kpi_html(label: str, value: str, hint: str = "", tone: str = "neutral", tooltip: str = "", icon_name: str = "",
             delta: str = "", delta_up: bool = True, delta_good: bool | None = True,
             spark: Sequence[float] = ()) -> str:
    """Return HTML for one KPI card: icon tile, label, value, delta line (good/bad/None=caution), sparkline."""
    color = _tone(tone) if tone != "neutral" else TEXT_2
    tip = f' title="{_e(tooltip)}"' if tooltip else ""
    tile = (f'<div class="tile" style="color:{color};background:{tint(color, .10)}">{icon(icon_name, 22)}</div>'
            if icon_name else "")
    if delta:
        dcol = TONE_COLORS["warning" if delta_good is None else ("success" if delta_good else "danger")]
        foot = (f'<div class="delta"><span class="arr" style="color:{dcol}">'
                f'{icon("arrow-up" if delta_up else "arrow-down", 14)}</span><span>{_e(delta)}</span></div>')
    else:
        foot = f'<div class="hint">{_e(hint)}</div>'
    spark_svg = sparkline(spark, color) if len(spark) else ""
    return (f'<div class="os-kpi">{tile}<div class="body"><div class="label">{_e(label)}</div>'
            f'<div class="vrow"><div class="value"{tip}>{_e(value)}</div>{spark_svg}</div>{foot}</div></div>')


def kpi_card(label: str, value: str, hint: str = "", tone: str = "neutral", tooltip: str = "", **extra: object) -> None:
    """Render one KPI card (extra: icon_name, delta, delta_up, delta_good, spark)."""
    _md(kpi_html(label, value, hint, tone, tooltip, **extra))


def kpi_row(items: Sequence[dict | Sequence]) -> None:
    """Render KPI cards in a responsive row; each item is a dict or (label, value, hint, tone, tooltip) tuple."""
    cards = [kpi_html(**it) if isinstance(it, dict) else kpi_html(*it) for it in items]
    _md(f'<div class="os-kpi-row">{"".join(cards)}</div>')


def alert_row(severity: str, service: str, message: str) -> None:
    """Render one alert row coloured and iconed by severity."""
    color = SEVERITY_COLORS.get(severity, MUTED)
    _md(f'<div class="os-alert os-alert-row" style="border-left-color:{color}">'
        f'<span class="icon" style="color:{color}">{icon(SEVERITY_ICONS.get(severity, "info"), 18)}</span><div>'
        f'<span class="sev" style="color:{color}">{_e(severity)}</span>'
        f'<b>{_e(service)}</b> — {_e(message)}</div></div>')


def section(title: str, help: str = "") -> None:
    """Render a section title with an optional one-line help text."""
    sub = f'<div class="help">{_e(help)}</div>' if help else ""
    _md(f'<div class="os-section"><div class="title">{_e(title)}</div>{sub}</div>')


# ---- formatting -------------------------------------------------------------

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


# ---- glass header & controls --------------------------------------------------

def brand_block() -> None:
    """Render the logo, product name, divider, tagline and engine status."""
    _md('<div class="os-brand"><span class="mark">O</span><span class="word">OPTISERVE</span>'
        '<span class="divider"></span><div class="tag"><div class="name">Capacity Planning Command Center</div>'
        '<div class="status"><span class="live"></span>Engine online · Analysis ready</div></div></div>')


def scenario_chip(title: str) -> None:
    """Render the current scenario as an amber pill sized to match the Export button."""
    st.markdown(f'<div class="os-scenario-pill" title="Scenario: {_e(title)}">{icon("server", 18)}'
                f'<span class="txt">{_e(title)}</span></div>', unsafe_allow_html=True, width="content")


def datetime_block(date_text: str, time_text: str) -> None:
    """Render the date and time with small calendar and clock icons."""
    st.markdown(f'<div class="os-datetime"><span>{icon("calendar", 16)}{_e(date_text)}</span>'
                f'<span>{icon("clock", 16)}{_e(time_text)}</span></div>', unsafe_allow_html=True, width="content")


TICKER_STYLES: dict[str, tuple[str, str]] = {
    "critical": ("Critical", "octagon-x"), "warning": ("Warning", "alert-triangle"), "ok": ("All clear", "check-circle"),
}


def alert_ticker(alerts: Sequence[dict]) -> None:
    """Render a slim ticker with the highest-severity alert (critical > warning), or a green all-clear."""
    order = {"critical": 0, "warning": 1}
    top = sorted((a for a in alerts if a.get("severity") in order), key=lambda a: order[a["severity"]])
    if top:
        level, text = top[0]["severity"], f'{top[0]["service"]} — {top[0]["message"]}'
    else:
        level, text = "ok", "All systems within capacity"
    label, ic = TICKER_STYLES[level]
    _md(f'<div class="os-ticker {level}" role="status" aria-label="{_e(label)}: {_e(text)}">'
        f'<span class="lead"><span class="pulse"></span>{icon(ic, 16)}<span class="lab">{_e(label)}</span></span>'
        f'<div class="msg" aria-hidden="true"><div class="track"><span>{_e(text)}</span></div></div></div>')


# ---- problem-statement mapping (display text only) ------------------------------

BRIEF_LABEL = "From the problem statement"
_FRACTION = "…most servers run at a fraction of their capacity for most of the day."
PROBLEM_QUOTES: dict[str, tuple[str, str, str]] = {
    "office_hours": (BRIEF_LABEL, "Teams size their infrastructure by guesswork and then leave it alone. To be safe, "
                                  "they provision for the worst case.", "Smart schedule"),
    "flash_sale": (BRIEF_LABEL, "…while the occasional busy hour still catches them short.", "Forecast + pre-warm"),
    "forgotten_servers": (BRIEF_LABEL, _FRACTION, "Server Graveyard"),
    "sick_server": ("Beyond the brief", "Cutting capacity blindly is risky — OptiServe checks server health before it "
                                        "saves money.", "Safety checks"),
    "growth_startup": (BRIEF_LABEL, "Usage data … is rarely used to decide how much capacity is needed next week or "
                                    "next month.", "Next-month outlook"),
    "night_batch": (BRIEF_LABEL, _FRACTION, "Time-aware schedule"),
}
PROBLEM_COVERAGE: list[tuple[str, str, tuple[str, ...]]] = [
    ("Sized by guesswork, left alone", "Office-hours portal", ("office_hours",)),
    ("Provisioned for the worst case", "Office-hours portal", ("office_hours",)),
    ("Servers at a fraction of capacity", "Forgotten servers · Nightly batch", ("forgotten_servers", "night_batch")),
    ("Busy hour catches them short", "Flash sale", ("flash_sale",)),
    ("Capacity for next week", "Forecast & Plan (7-day hourly)", ()),
    ("Capacity for next month", "Growing startup", ("growth_startup",)),
]


def problem_strip(scenario_key: str) -> None:
    """Render the slim quote strip linking the scenario to the problem statement; unknown keys render nothing."""
    if scenario_key not in PROBLEM_QUOTES:
        return
    label, quote, solved = PROBLEM_QUOTES[scenario_key]
    _md(f'<div class="os-quote" role="note"><span class="qi">{icon("quote", 20)}</span>'
        f'<div class="body"><div class="lab">{_e(label)}</div><div class="q">“{_e(quote)}”</div></div>'
        f'<span class="tag">{icon("check-circle", 14)}Solved by: {_e(solved)}</span></div>')


def problem_coverage(scenario_key: str) -> None:
    """Render one row per problem-statement line with the scenario/page that covers it; current ones highlighted."""
    rows = "".join(
        f'<div class="os-cov{" on" if scenario_key in keys else ""}"><span class="ck">{icon("check-circle", 16)}</span>'
        f'<span class="ln">{_e(line)}</span><span class="by">{_e(by)}</span></div>'
        for line, by, keys in PROBLEM_COVERAGE
    )
    _md(f'<div class="os-covlist">{rows}</div>')


def muted_note(text: str) -> None:
    """Render a small muted footnote line."""
    _md(f'<div class="os-muted">{icon("info", 14)}{_e(text)}</div>')


def risk_pill(label: str) -> None:
    """Render the live risk-mode label as a pill."""
    color = _tone(RISK_TONES.get(label, "info"))
    _md(f'<div class="os-risk"><span class="cap">Mode</span>{pill(label, color)}</div>')


def card_title(title: str, help: str = "", icon_name: str = "", right: str = "") -> None:
    """Render a title row inside a bordered card container; `right` is pre-built HTML."""
    ic = f'<span class="ic">{icon(icon_name, 18)}</span>' if icon_name else ""
    sub = f'<div class="help">{_e(help)}</div>' if help else ""
    _md(f'<div class="os-card-title"><div><div class="title">{ic}{_e(title)}</div>{sub}</div>'
        f'<div class="right">{right}</div></div>')


def status_counts(counts: dict[str, int]) -> str:
    """Return HTML pills with the server count per status, in status order."""
    return "".join(pill(f"{s} · {int(counts[s])}", c) for s, c in STATUS_COLORS.items() if counts.get(s))


def priority_actions(rows: Sequence[dict]) -> None:
    """Render priority action rows; each has pill (HTML), name, detail, amount and tone."""
    if not rows:
        _md(f'<div class="os-actions"><div class="os-action empty">{icon("check-circle", 18)}'
            f'Nothing urgent — the fleet looks healthy.</div></div>')
        return
    items = "".join(
        f'<div class="os-action"><div class="what"><div class="pillcol">{r["pill"]}</div><div class="name">{_e(r["name"])}</div>'
        f'<div class="detail">{_e(r["detail"])}</div></div>'
        f'<div class="amt" style="color:{_tone(r.get("tone", "neutral"))}">{_e(r["amount"])}</div>'
        f'<span class="chev">{icon("chevron-right", 18)}</span></div>'
        for r in rows
    )
    _md(f'<div class="os-actions">{items}</div>')


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
        f'<div class="os-check"><span class="icon" style="color:{_tone(CHECK_TONES.get(it["status"], "neutral"))}">'
        f'{icon(CHECK_ICONS.get(it["status"], "info"), 18)}</span><div>'
        f'<div class="rule">{_e(it["rule"])}<span class="state" '
        f'style="color:{_tone(CHECK_TONES.get(it["status"], "neutral"))}">'
        f'{_e(CHECK_LABELS.get(it["status"], it["status"]))}</span></div>'
        f'<div class="msg">{_e(it["message"])}</div></div></div>'
        for it in items
    )
    head = f"<h4>{_e(title)}</h4>" if title else ""
    _md(f'<div class="os-card">{head}{rows}</div>')


def alerts_feed(alerts: Sequence[dict]) -> None:
    """Render alerts critical → info, or a calm empty state."""
    order = {"critical": 0, "warning": 1, "info": 2}
    if not alerts:
        _md(f'<div class="os-alert os-alert-row" style="border-left-color:#16A34A"><span class="icon" '
            f'style="color:#16A34A">{icon("check-circle", 18)}</span><div>No alerts — the fleet looks healthy.</div></div>')
        return
    for a in sorted(alerts, key=lambda a: order.get(a["severity"], 9)):
        alert_row(a["severity"], a["service"], a["message"])


# ---- Server Graveyard ----------------------------------------------------------

EPITAPHS: dict[str, str] = {"Zombie": "R.I.P.", "Wasteful": "On notice", "Risky": "Do not bury"}
STONE_ICONS: dict[str, str] = {"Zombie": "gravestone", "Wasteful": "alert-triangle", "Risky": "heart-pulse"}
STATUS_PILL_ON_DARK: dict[str, str] = {"Zombie": "#C4B5FD", "Wasteful": "#FCD34D", "Risky": "#FCA5A5",
                                       "Hot": "#FDBA74", "Right-sized": "#86EFAC"}


def tombstone(name: str, instance_type: str, service: str, status: str, cost: float, idle_since: str,
              reason: str) -> str:
    """Return HTML for one tombstone; hovering shows the reason."""
    color = STATUS_COLORS.get(status, TEXT_2)
    return (f'<div class="os-stone" title="{_e(reason)}" style="border-top:3px solid {color}">'
            f'<div class="ic" style="color:{STATUS_PILL_ON_DARK.get(status, color)}">'
            f'{icon(STONE_ICONS.get(status, "server"), 22)}</div>'
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
        f'<div class="small">{icon("flame", 16)} Wasted every month</div><div class="big">{_e(money(total_wasted))}</div>'
        f'<div class="small">{len(stones)} server(s) in the yard — {_e(parts)}</div></div>'
        f'<div class="os-yard">{body}</div><div class="os-hint">{icon("info", 14)} Hover a stone to see why it is here.'
        f'</div></div>')


def table_card(title: str, headers: Sequence[str], rows: Sequence[Sequence[str]], numeric: Sequence[int] = ()) -> None:
    """Render a white table card; cells are pre-built HTML, `numeric` column indexes align right."""
    def cls(i: int) -> str:
        """Return the CSS class for column i."""
        return ' class="num"' if i in numeric else ""
    head = "".join(f"<th{cls(i)}>{_e(h)}</th>" for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(f"<td{cls(i)}>{c}</td>" for i, c in enumerate(r)) + "</tr>" for r in rows)
    head = f"<h4>{_e(title)}</h4>" if title else ""
    _md(f'<div class="os-card os-table-card">{head}<div class="os-table-wrap">'
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
    arrow = icon("arrow-down" if diff < 0 else "arrow-up", 12)
    value = money(abs(diff)) if fmt == "money" else f"{abs(diff):,.0f} h"
    return f'<span class="delta" style="color:{color};background:{tint(color)}">{arrow}{_e(value)}</span>'


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
