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
.os-sky {{ background: radial-gradient(ellipse at top, #1e1b4b 0%, #0b1120 55%, #020617 100%);
  border-radius: 18px; padding: 1.4rem; border: 1px solid #1e293b; position: relative; overflow: hidden; }}
.os-sky::before {{ content: ""; position: absolute; inset: 0; pointer-events: none; opacity: .7;
  background-image: radial-gradient(1px 1px at 12% 18%, #fff, transparent), radial-gradient(1px 1px at 34% 8%, #cbd5e1, transparent),
  radial-gradient(1.5px 1.5px at 58% 22%, #fff, transparent), radial-gradient(1px 1px at 76% 12%, #e2e8f0, transparent),
  radial-gradient(1px 1px at 90% 30%, #fff, transparent), radial-gradient(1px 1px at 22% 40%, #94a3b8, transparent),
  radial-gradient(1.5px 1.5px at 66% 45%, #e2e8f0, transparent), radial-gradient(1px 1px at 45% 35%, #fff, transparent); }}
.os-moon {{ position: absolute; top: 1rem; right: 1.5rem; width: 46px; height: 46px; border-radius: 50%;
  background: #fef9c3; box-shadow: 0 0 30px 8px rgba(254,249,195,.25); }}
.os-banner {{ position: relative; color: #e2e8f0; margin-bottom: 1.2rem; }}
.os-banner .big {{ font-size: 2rem; font-weight: 800; color: #f8fafc; }}
.os-banner .small {{ color: #94a3b8; font-size: .9rem; }}
.os-yard {{ position: relative; display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 1.2rem;
  padding-bottom: .8rem; border-bottom: 6px solid #14532d; }}
.os-stone {{ background: linear-gradient(180deg, #475569, #334155 70%, #1e293b); border-radius: 90px 90px 10px 10px;
  padding: 1.6rem .9rem 1rem; text-align: center; color: #e2e8f0; border: 1px solid #64748b;
  box-shadow: 0 8px 18px rgba(0,0,0,.45); transition: transform .15s; cursor: help; }}
.os-stone:hover {{ transform: translateY(-4px); }}
.os-stone .epitaph {{ font-family: Georgia, serif; font-size: 1.05rem; font-weight: 700; letter-spacing: .08em; color: #f1f5f9; }}
.os-stone .name {{ font-weight: 700; margin: .45rem 0 .15rem; word-break: break-word; }}
.os-stone .meta {{ color: #cbd5e1; font-size: .78rem; line-height: 1.5; }}
.os-stone .cost {{ font-size: 1.1rem; font-weight: 700; color: #fde68a; margin: .35rem 0; }}
.os-tile {{ background: #111827; border: 1px solid #1f2937; border-radius: 14px; padding: .9rem 1.1rem; height: 100%; }}
.os-tile .label {{ color: #94a3b8; font-size: .75rem; text-transform: uppercase; letter-spacing: .06em; }}
.os-tile .row {{ display: flex; justify-content: space-between; gap: .5rem; margin-top: .35rem; font-size: .9rem; color: #cbd5e1; }}
.os-tile .row b {{ color: #f8fafc; font-size: 1.15rem; }}
.os-tile .big {{ color: #22c55e; font-size: 2rem; font-weight: 800; margin-top: .2rem; }}
</style>
"""


def inject_css() -> None:
    """Inject the global CSS (call once per run, before any page renders)."""
    st.markdown(CSS, unsafe_allow_html=True)


def chip(text: str, color: str) -> str:
    """Return HTML for a coloured status chip."""
    return f'<span class="os-chip" style="color:{color}">{text}</span>'
