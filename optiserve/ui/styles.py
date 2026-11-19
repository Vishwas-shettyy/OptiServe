"""Design system: tokens and global CSS (UI_UPGRADE.md §1)."""

import streamlit as st

# Design tokens
FONT = "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
BG = "#F6F7FB"
SURFACE = "#FFFFFF"
BORDER = "#E6E8EF"
SHADOW = "0 1px 2px rgba(16,24,40,.06)"
RADIUS = "14px"
SIDEBAR_BG = "#0B1220"
SIDEBAR_TEXT = "#E2E8F0"
SIDEBAR_MUTED = "#94A3B8"
TEXT = "#0F172A"
TEXT_2 = "#475569"
MUTED = "#94A3B8"
ACCENT = "#2563EB"
ACCENT_TINT = "#EFF4FF"
GRID = "#EEF0F5"

STATUS_COLORS: dict[str, str] = {
    "Right-sized": "#16A34A",
    "Wasteful": "#D97706",
    "Zombie": "#7C3AED",
    "Hot": "#EA580C",
    "Risky": "#DC2626",
}
TONE_COLORS: dict[str, str] = {
    "info": ACCENT, "success": "#16A34A", "warning": "#D97706", "danger": "#DC2626", "neutral": TEXT_2,
}
SEVERITY_COLORS: dict[str, str] = {"critical": "#DC2626", "warning": "#D97706", "info": ACCENT}


def tint(color: str, alpha: float = 0.10) -> str:
    """Return an rgba() tint of a hex colour (default 10%)."""
    h = color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* ---- base ---- */
html, body, .stApp, [class*="st-"], button, input, select, textarea {{ font-family: {FONT}; }}
.stApp {{ background: {BG}; color: {TEXT}; font-size: 14px; }}
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"],
.stDeployButton, [data-testid="stAppDeployButton"] {{ display: none !important; }}
header[data-testid="stHeader"] {{ background: transparent; height: 2.5rem; }}
.block-container, [data-testid="stMainBlockContainer"] {{ max-width: 1440px; padding-top: 1.5rem; padding-bottom: 2rem; }}
h1 {{ font-size: 28px !important; font-weight: 700 !important; color: {TEXT}; letter-spacing: -.01em; }}
h2, h3 {{ font-size: 18px !important; font-weight: 600 !important; color: {TEXT}; }}

/* ---- sidebar ---- */
section[data-testid="stSidebar"] {{ background: {SIDEBAR_BG}; border-right: 1px solid #1E293B; }}
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] [role="radiogroup"] label p {{ color: {SIDEBAR_TEXT}; }}
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{ color: {SIDEBAR_MUTED}; }}
section[data-testid="stSidebar"] [data-testid="stSliderTickBarMin"],
section[data-testid="stSidebar"] [data-testid="stSliderTickBarMax"] {{ color: {SIDEBAR_MUTED}; }}
.os-logo {{ display: flex; align-items: center; gap: 10px; font-size: 20px; font-weight: 800; color: #FFFFFF; }}
.os-logo .mark {{ width: 32px; height: 32px; border-radius: 9px; background: {ACCENT}; color: #fff;
  display: grid; place-items: center; font-size: 17px; font-weight: 800; }}
.os-sub {{ color: {SIDEBAR_MUTED}; font-size: 13px; margin: 2px 0 16px 0; }}
.os-footer {{ color: {SIDEBAR_MUTED}; font-size: 12px; margin-top: 32px; line-height: 1.5; }}

/* ---- motion ---- */
@keyframes os-rise {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: none; }} }}
.os-card, .os-kpi, .os-tile, .os-banner-insight, .os-alert {{ animation: os-rise .25s ease-out both; }}
.os-card, .os-kpi, .os-tile {{ transition: transform .15s ease, box-shadow .15s ease; }}
.os-card:hover, .os-kpi:hover, .os-tile:hover {{ transform: translateY(-2px); box-shadow: 0 6px 16px rgba(16,24,40,.08); }}

/* ---- cards ---- */
.os-card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS}; box-shadow: {SHADOW};
  padding: 16px 24px; margin-bottom: 16px; }}
.os-card h4 {{ margin: 0 0 8px 0; color: {TEXT}; font-size: 16px; font-weight: 600; }}
.os-card p {{ margin: 0; color: {TEXT_2}; line-height: 1.55; }}
.os-placeholder {{ text-align: center; padding: 64px 16px; color: {TEXT_2}; }}
.os-story {{ color: {TEXT_2}; font-size: 14px; margin-bottom: 16px; }}

/* ---- page header & section ---- */
.os-header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap;
  margin-bottom: 16px; }}
.os-header .title {{ font-size: 28px; font-weight: 700; color: {TEXT}; line-height: 1.2; letter-spacing: -.01em; }}
.os-header .subtitle {{ color: {TEXT_2}; font-size: 14px; margin-top: 4px; }}
.os-section {{ margin: 24px 0 8px 0; }}
.os-section .title {{ font-size: 18px; font-weight: 600; color: {TEXT}; }}
.os-section .help {{ color: {TEXT_2}; font-size: 13px; margin-top: 2px; }}

/* ---- pills, badges, chips ---- */
.os-pill {{ display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 999px;
  font-size: 12px; font-weight: 600; line-height: 20px; white-space: nowrap; }}
.os-pill .dot {{ width: 6px; height: 6px; border-radius: 50%; background: currentColor; }}
.os-chip {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
  border: 1px solid currentColor; margin-right: 6px; white-space: nowrap; }}
.os-tip {{ border-bottom: 1px dotted {MUTED}; cursor: help; }}

/* ---- insight banner ---- */
.os-banner-insight {{ display: flex; gap: 12px; align-items: flex-start; border-radius: 12px; padding: 14px 18px;
  margin-bottom: 16px; font-size: 15px; font-weight: 500; color: {TEXT}; border: 1px solid; }}
.os-banner-insight .icon {{ font-size: 18px; line-height: 1.3; }}

/* ---- KPI cards ---- */
.os-kpi-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 16px; }}
.os-kpi {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS}; box-shadow: {SHADOW};
  padding: 16px 20px; height: 100%; min-width: 0; border-top: 3px solid var(--tone, {BORDER}); }}
.os-kpi .label, .os-kpi .value, .os-kpi .hint {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.os-kpi .label {{ color: {TEXT_2}; font-size: 12px; font-weight: 500; text-transform: uppercase; letter-spacing: .04em; }}
.os-kpi .value {{ color: {TEXT}; font-size: clamp(22px, 2.1vw, 30px); font-weight: 700; margin-top: 4px;
  font-variant-numeric: tabular-nums; line-height: 1.2; }}
.os-kpi .hint {{ color: {MUTED}; font-size: 12px; margin-top: 4px; }}

/* ---- alert rows ---- */
.os-alert {{ display: block; background: {SURFACE}; border: 1px solid {BORDER};
  border-left: 4px solid {ACCENT}; border-radius: 10px; padding: 10px 14px; margin-bottom: 8px; color: {TEXT};
  font-size: 14px; line-height: 1.45; box-shadow: {SHADOW}; }}
.os-alert.os-alert-row {{ display: flex; gap: 10px; align-items: flex-start; }}
.os-alert .icon {{ font-size: 16px; line-height: 1.4; }}
.os-alert .sev {{ font-weight: 700; text-transform: uppercase; font-size: 11px; letter-spacing: .04em; margin-right: 8px; }}

/* ---- comparison tiles (Time Machine, until U3) ---- */
.os-tile {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS}; box-shadow: {SHADOW};
  padding: 16px 20px; height: 100%; }}
.os-tile .label {{ color: {TEXT_2}; font-size: 12px; font-weight: 500; text-transform: uppercase; letter-spacing: .04em; }}
.os-tile .row {{ display: flex; justify-content: space-between; gap: 8px; margin-top: 6px; font-size: 14px; color: {TEXT_2}; }}
.os-tile .row b {{ color: {TEXT}; font-size: 18px; font-variant-numeric: tabular-nums; }}
.os-tile .big {{ color: #16A34A; font-size: 30px; font-weight: 700; margin-top: 4px; }}

/* ---- Graveyard night scene (stays dark inside the light app) ---- */
.os-sky {{ background: radial-gradient(ellipse at top, #1e1b4b 0%, #0b1120 55%, #020617 100%);
  border-radius: 18px; padding: 24px; border: 1px solid #1e293b; position: relative; overflow: hidden;
  box-shadow: 0 8px 24px rgba(15,23,42,.18); }}
.os-sky::before {{ content: ""; position: absolute; inset: 0; pointer-events: none; opacity: .7;
  background-image: radial-gradient(1px 1px at 12% 18%, #fff, transparent), radial-gradient(1px 1px at 34% 8%, #cbd5e1, transparent),
  radial-gradient(1.5px 1.5px at 58% 22%, #fff, transparent), radial-gradient(1px 1px at 76% 12%, #e2e8f0, transparent),
  radial-gradient(1px 1px at 90% 30%, #fff, transparent), radial-gradient(1px 1px at 22% 40%, #94a3b8, transparent),
  radial-gradient(1.5px 1.5px at 66% 45%, #e2e8f0, transparent), radial-gradient(1px 1px at 45% 35%, #fff, transparent); }}
.os-moon {{ position: absolute; top: 16px; right: 24px; width: 46px; height: 46px; border-radius: 50%;
  background: #fef9c3; box-shadow: 0 0 30px 8px rgba(254,249,195,.25); }}
.os-banner {{ position: relative; color: #e2e8f0; margin-bottom: 20px; }}
.os-banner .big {{ font-size: 32px; font-weight: 800; color: #f8fafc; font-variant-numeric: tabular-nums; }}
.os-banner .small {{ color: #94a3b8; font-size: 14px; }}
.os-yard {{ position: relative; display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 20px;
  padding-bottom: 12px; border-bottom: 6px solid #14532d; }}
.os-stone {{ background: linear-gradient(180deg, #475569, #334155 70%, #1e293b); border-radius: 90px 90px 10px 10px;
  padding: 26px 14px 16px; text-align: center; color: #e2e8f0; border: 1px solid #64748b;
  box-shadow: 0 8px 18px rgba(0,0,0,.45); transition: transform .15s; cursor: help; }}
.os-stone:hover {{ transform: translateY(-2px); }}
.os-stone .epitaph {{ font-family: Georgia, serif; font-size: 17px; font-weight: 700; letter-spacing: .08em; color: #f1f5f9; }}
.os-stone .name {{ font-weight: 700; margin: 8px 0 2px; word-break: break-word; }}
.os-stone .meta {{ color: #cbd5e1; font-size: 12px; line-height: 1.5; }}
.os-stone .cost {{ font-size: 18px; font-weight: 700; color: #fde68a; margin: 6px 0; }}
</style>
"""


def inject_css() -> None:
    """Inject the global CSS (call once per run, before any page renders)."""
    st.markdown(CSS, unsafe_allow_html=True)


def chip(text: str, color: str) -> str:
    """Return HTML for a coloured outline chip (legacy pages; new code uses components.status_pill)."""
    return f'<span class="os-chip" style="color:{color}">{text}</span>'
