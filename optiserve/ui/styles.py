"""Global CSS for the dark theme, cards, KPI tiles, chips and alerts."""

import streamlit as st

STATUS_COLORS: dict[str, str] = {
    "Right-sized": "#22c55e",
    "Wasteful": "#f59e0b",
    "Zombie": "#a78bfa",
    "Hot": "#fb923c",
    "Risky": "#ef4444",
}
ACCENT = "#38bdf8"
SEVERITY_COLORS: dict[str, str] = {"critical": "#ef4444", "warning": "#f59e0b", "info": ACCENT}

CSS = f"""
<style>
.stApp {{ background: #0b1120; color: #e2e8f0; }}
section[data-testid="stSidebar"] {{ background: #0f172a; border-right: 1px solid #1e293b; }}
.os-logo {{ font-size: 1.6rem; font-weight: 800; color: {ACCENT}; letter-spacing: .02em; }}
.os-sub {{ color: #94a3b8; font-size: .85rem; margin-top: -.3rem; margin-bottom: 1rem; }}
.os-footer {{ color: #64748b; font-size: .75rem; margin-top: 2rem; }}
.os-card {{ background: #111827; border: 1px solid #1f2937; border-radius: 14px;
  padding: 1rem 1.2rem; margin-bottom: .8rem; }}
.os-card h4 {{ margin: 0 0 .4rem 0; color: #f1f5f9; font-size: 1rem; }}
.os-card p {{ margin: 0; color: #cbd5e1; line-height: 1.5; }}
.os-story {{ color: #94a3b8; font-size: .95rem; margin-bottom: 1.2rem; }}
.os-kpi {{ background: linear-gradient(160deg, #111827, #0f172a); border: 1px solid #1f2937;
  border-radius: 14px; padding: 1rem 1.2rem; height: 100%; }}
.os-kpi .label {{ color: #94a3b8; font-size: .78rem; text-transform: uppercase; letter-spacing: .06em; }}
.os-kpi .value {{ color: #f8fafc; font-size: 1.7rem; font-weight: 700; margin-top: .2rem; }}
.os-kpi .hint {{ color: #64748b; font-size: .75rem; margin-top: .2rem; }}
.os-chip {{ display: inline-block; padding: .1rem .6rem; border-radius: 999px; font-size: .72rem;
  font-weight: 600; border: 1px solid currentColor; margin-right: .3rem; }}
.os-alert {{ border-radius: 10px; padding: .6rem .9rem; margin-bottom: .5rem; background: #111827;
  border-left: 4px solid {ACCENT}; color: #e2e8f0; font-size: .9rem; }}
.os-alert .sev {{ font-weight: 700; text-transform: uppercase; font-size: .72rem; margin-right: .5rem; }}
.os-placeholder {{ text-align: center; padding: 4rem 1rem; color: #94a3b8; }}
</style>
"""


def inject_css() -> None:
    """Inject the global CSS (call once per run, before any page renders)."""
    st.markdown(CSS, unsafe_allow_html=True)


def chip(text: str, color: str) -> str:
    """Return HTML for a coloured status chip."""
    return f'<span class="os-chip" style="color:{color}">{text}</span>'
