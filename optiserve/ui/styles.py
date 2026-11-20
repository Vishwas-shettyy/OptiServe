"""Design system: tokens and global CSS (UI_UPGRADE.md §1)."""

import streamlit as st

# Design tokens
FONT = 'Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
FONT_HEAD = '"Outfit", Inter, system-ui, -apple-system, "Segoe UI", sans-serif'
FONT_MONO = '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'
BG = "#F6F7FB"
SURFACE = "#FFFFFF"
BORDER = "rgba(148,163,184,0.25)"
SHADOW = "0 4px 20px rgba(15,23,42,0.04)"
RADIUS = "14px"
GLASS_BG = "rgba(255,255,255,0.65)"
GLASS_BORDER = "rgba(255,255,255,0.7)"
GLASS_SHADOW = "0 8px 32px rgba(15,23,42,0.08)"
HOVER_SHADOW = "0 12px 28px rgba(15,23,42,.12)"
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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

/* ---- base: light page with soft blurred colour washes so the glass reads ---- */
html, body, .stApp, [class*="st-"], button, input, select, textarea {{ font-family: {FONT}; }}
[data-testid="stIconMaterial"], .material-symbols-rounded {{ font-family: "Material Symbols Rounded" !important; }}
.stApp {{ color: {TEXT}; font-size: 14px; background:
  radial-gradient(640px 480px at 8% -4%, rgba(37,99,235,.10), transparent 70%),
  radial-gradient(560px 420px at 92% 6%, rgba(124,58,237,.08), transparent 70%),
  radial-gradient(720px 520px at 55% 105%, rgba(56,189,248,.08), transparent 70%), {BG};
  background-attachment: fixed; }}
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"],
.stDeployButton, [data-testid="stAppDeployButton"], header[data-testid="stHeader"],
section[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"]
{{ display: none !important; }}
.block-container, [data-testid="stMainBlockContainer"] {{ max-width: 1440px; padding-top: 12px; padding-bottom: 2rem; }}
h1 {{ font-size: 28px !important; font-weight: 800 !important; color: {TEXT}; letter-spacing: -.01em; }}
h2, h3 {{ font-size: 18px !important; font-weight: 700 !important; color: {TEXT}; }}

/* ---- typography: Outfit headings, Inter body, JetBrains Mono numbers ---- */
h1, h2, h3, h4, .os-header .title, .os-section .title, .os-card-title .title, .os-card h4, .os-rec .name,
.os-brand .word, .os-brand .name {{ font-family: {FONT_HEAD} !important; }}
.os-header .title {{ font-weight: 800; }}
.os-section .title, .os-card-title .title, .os-card h4, .os-rec .name, .os-brand .name {{ font-weight: 700; }}
.os-kpi .value, .os-rec .stat .value, .os-split .m .value, .os-split .delta, .os-table .num, .os-datetime,
.os-action .amt, .os-banner .big, .os-stone .cost, .os-bar-row .lbl b {{ font-family: {FONT_MONO};
  font-variant-numeric: tabular-nums; letter-spacing: -.02em; }}

/* ---- scrollbars: slim, transparent track, stable gutter ---- */
html, [data-testid="stMain"] {{ scrollbar-gutter: stable; }}
::-webkit-scrollbar {{ width: 8px; height: 8px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: rgba(148,163,184,0.4); border-radius: 999px; }}
::-webkit-scrollbar-thumb:hover {{ background: rgba(148,163,184,0.7); }}
@supports not selector(::-webkit-scrollbar) {{
  * {{ scrollbar-width: thin; scrollbar-color: rgba(148,163,184,0.4) transparent; }}
}}

/* ---- glass header (sticky, always elevated) ---- */
[data-testid="stLayoutWrapper"]:has(> .st-key-os_header) {{ position: sticky; top: 12px; z-index: 1000; }}
.st-key-os_header {{ background: {GLASS_BG};
  -webkit-backdrop-filter: blur(16px) saturate(160%); backdrop-filter: blur(16px) saturate(160%);
  border: 1px solid {GLASS_BORDER}; border-radius: 20px; box-shadow: {GLASS_SHADOW}; padding: 12px 20px 8px; }}
.st-key-os_top {{ flex-wrap: nowrap !important; }}
.st-key-os_brand {{ flex: 1 1 0 !important; min-width: 0 !important; }}
.st-key-os_right {{ flex: 0 0 auto !important; flex-wrap: nowrap !important; gap: 12px !important; align-items: center !important; }}
.st-key-os_right [data-testid="stElementContainer"], .st-key-os_right [data-testid="stMarkdownContainer"],
.st-key-os_right [data-testid="stMarkdown"] {{ margin: 0 !important; display: flex; align-items: center; }}
.os-brand {{ display: flex; align-items: center; gap: 12px; min-width: 0; }}
.os-brand .mark {{ width: 36px; height: 36px; border-radius: 10px; background: {ACCENT}; color: #fff; flex: none;
  display: grid; place-items: center; font-size: 18px; font-weight: 800; box-shadow: 0 4px 12px rgba(37,99,235,.35); }}
.os-brand .word {{ font-size: 18px; font-weight: 800; letter-spacing: .08em; color: {TEXT}; }}
.os-brand .divider {{ width: 1px; height: 30px; background: {BORDER}; flex: none; }}
.os-brand .tag {{ min-width: 0; }}
.os-brand .name {{ font-size: 14px; color: {TEXT}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
@media (max-width: 1440px) {{ .os-brand .name {{ font-size: 13px; line-height: 1.2; white-space: normal; }} .os-brand .word {{ letter-spacing: .06em; }} }}
.os-brand .status {{ display: flex; align-items: center; gap: 6px; font-size: 12px; color: #16A34A; font-weight: 500; white-space: nowrap; }}
.os-brand .live {{ width: 7px; height: 7px; border-radius: 50%; background: #16A34A; box-shadow: 0 0 0 3px rgba(22,163,74,.18); }}
.os-icon {{ flex: none; vertical-align: -3px; }}

/* scenario pill + Export report: one shared shape (40px, 0 18px, 999px, 14px/600, 18px icon) */
.os-scenario-pill, .st-key-os_header .stDownloadButton button {{ box-sizing: border-box; height: 40px; min-height: 40px;
  min-width: 220px; padding: 0 18px; border-radius: 999px; font-size: 14px; font-weight: 600; line-height: 1;
  display: inline-flex; align-items: center; justify-content: center; gap: 8px; white-space: nowrap;
  transition: transform .2s ease, box-shadow .2s ease; }}
.os-scenario-pill {{ max-width: 320px; background: #FFF4E0; border: 1px solid #F59E0B; color: #B45309; cursor: default; }}
.os-scenario-pill .txt {{ display: block; min-width: 0; overflow: hidden; text-overflow: ellipsis; }}
.os-scenario-pill .os-icon {{ vertical-align: 0; }}
.os-scenario-pill:hover {{ transform: translateY(-2px); box-shadow: 0 6px 16px rgba(245,158,11,.22); }}
.st-key-os_header .stDownloadButton button, .st-key-os_header .stDownloadButton button:focus,
.st-key-os_header .stDownloadButton button:active {{ background: #FFFFFF; border: 1px solid {ACCENT}; color: {ACCENT}; box-shadow: none; }}
.st-key-os_header .stDownloadButton button p {{ font-size: 14px; font-weight: 600; line-height: 1; color: inherit; }}
.st-key-os_header .stDownloadButton button [data-testid="stIconMaterial"] {{ font-size: 18px; color: inherit; }}
.st-key-os_header .stDownloadButton button > div {{ gap: 8px; }}
.st-key-os_header .stDownloadButton button:hover {{ background: #FFFFFF; color: {ACCENT}; border-color: {ACCENT};
  transform: translateY(-2px); box-shadow: 0 6px 16px rgba(37,99,235,.18); }}
.os-datetime {{ display: flex; align-items: center; gap: 12px; height: 40px; margin-left: 4px; color: {TEXT_2};
  font-size: 13px; font-weight: 500; }}
.os-datetime span {{ display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }}

/* ---- nav pills: centred row, only the active page is highlighted ---- */
.st-key-os_nav {{ border-top: 1px solid rgba(15,23,42,.06); padding-top: 8px; margin-top: 2px;
  justify-content: center !important; gap: 8px !important; }}
.st-key-os_nav [data-testid="stPageLink"] a {{ border-radius: 999px; padding: 6px 14px; color: {TEXT_2};
  background: transparent; transition: background .2s ease, color .2s ease; }}
.st-key-os_nav [data-testid="stPageLink"] a:hover {{ background: rgba(15,23,42,.05); color: {TEXT}; }}
.st-key-os_nav [data-testid="stPageLink"] a:focus:not(:hover) {{ background: transparent; }}
.st-key-os_nav [data-testid="stPageLink"] a:focus-visible {{ outline: 2px solid rgba(37,99,235,.45); outline-offset: 2px; }}
.st-key-os_nav [data-testid="stPageLink"] a p, .st-key-os_nav [data-testid="stPageLink"] a span {{ font-weight: 500;
  font-size: 14px; color: inherit; background: transparent; }}
.st-key-os_nav [data-testid="stPageLink"] a [data-testid="stIconMaterial"] {{ color: inherit; }}
.st-key-nav_active [data-testid="stPageLink"] a, .st-key-nav_active [data-testid="stPageLink"] a:hover,
.st-key-nav_active [data-testid="stPageLink"] a:focus:not(:hover) {{ background: {ACCENT_TINT}; color: {ACCENT}; }}
.st-key-nav_active [data-testid="stPageLink"] a p, .st-key-nav_active [data-testid="stPageLink"] a span {{ font-weight: 600; }}

/* ---- alert ticker (directly under the header) ---- */
@keyframes os-marquee {{ from {{ transform: translateX(0); }} to {{ transform: translateX(-100%); }} }}
@keyframes os-pulse {{ from {{ transform: scale(1); opacity: .55; }} to {{ transform: scale(2.8); opacity: 0; }} }}
.os-ticker {{ display: flex; align-items: center; gap: 12px; height: 38px; padding: 0 16px; margin: 0 0 2px;
  border-radius: 12px; border: 1px solid; font-size: 13px; font-weight: 500; overflow: hidden; }}
.os-ticker.critical {{ background: {tint("#DC2626", .08)}; border-color: {tint("#DC2626", .30)}; color: #B91C1C; }}
.os-ticker.warning {{ background: #FFF4E0; border-color: {tint("#F59E0B", .45)}; color: #B45309; }}
.os-ticker.ok {{ background: {tint("#16A34A", .07)}; border-color: {tint("#16A34A", .28)}; color: #15803D; }}
.os-ticker .lead {{ display: inline-flex; align-items: center; gap: 8px; flex: none; padding-right: 12px;
  border-right: 1px solid rgba(15,23,42,.10); font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }}
.os-ticker .pulse {{ position: relative; width: 8px; height: 8px; border-radius: 50%; background: currentColor; flex: none; }}
.os-ticker .pulse::after {{ content: ""; position: absolute; inset: 0; border-radius: 50%; background: currentColor;
  animation: os-pulse 1.6s ease-out infinite; }}
.os-ticker .msg {{ flex: 1; min-width: 0; overflow: hidden; white-space: nowrap;
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 24px, #000 calc(100% - 24px), transparent);
  mask-image: linear-gradient(90deg, transparent, #000 24px, #000 calc(100% - 24px), transparent); }}
.os-ticker .track {{ display: inline-block; padding-left: 100%; animation: os-marquee 36s linear -9s infinite; }}
.os-ticker:hover .track {{ animation-play-state: paused; }}
@media (prefers-reduced-motion: reduce) {{
  .os-ticker .track {{ display: block; padding-left: 0; transform: none !important; overflow: hidden; text-overflow: ellipsis; }}
  .os-ticker .msg {{ -webkit-mask-image: none; mask-image: none; }}
  .os-ticker .pulse::after {{ display: none; }}
}}

/* ---- glass controls row ---- */
.st-key-os_controls {{ background: {GLASS_BG}; -webkit-backdrop-filter: blur(16px) saturate(160%);
  backdrop-filter: blur(16px) saturate(160%); border: 1px solid {GLASS_BORDER}; border-radius: 20px;
  box-shadow: {GLASS_SHADOW}; padding: 10px 20px 4px; margin: 4px 0 8px; }}
.os-risk {{ display: flex; align-items: center; gap: 8px; justify-content: flex-end; padding-top: 18px; }}

/* ---- problem-statement quote strip (under the controls row) ---- */
.os-quote {{ display: flex; align-items: center; gap: 14px; padding: 10px 16px 10px 14px; margin: -8px 0 0;
  background: {GLASS_BG}; -webkit-backdrop-filter: blur(16px) saturate(160%); backdrop-filter: blur(16px) saturate(160%);
  border: 1px solid {GLASS_BORDER}; border-left: 3px solid {ACCENT}; border-radius: 14px; box-shadow: {GLASS_SHADOW}; }}
.os-quote .qi {{ display: inline-flex; flex: none; width: 36px; height: 36px; align-items: center; justify-content: center;
  border-radius: 10px; color: {ACCENT}; background: {ACCENT_TINT}; }}
.os-quote .body {{ flex: 1; min-width: 0; }}
.os-quote .lab {{ font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; color: {ACCENT}; }}
.os-quote .q {{ font-size: 15px; font-style: italic; font-weight: 500; color: {TEXT}; line-height: 1.4; }}
.os-quote .tag {{ flex: none; display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 999px;
  font-size: 12.5px; font-weight: 600; white-space: nowrap; color: #15803D; background: {tint("#16A34A", .09)};
  border: 1px solid {tint("#16A34A", .28)}; }}
@media (max-width: 900px) {{ .os-quote {{ flex-wrap: wrap; }} .os-quote .tag {{ margin-left: 50px; }} }}

/* ---- problem coverage list & muted note ---- */
.os-covlist {{ display: flex; flex-direction: column; gap: 4px; margin-top: 8px; }}
.os-cov {{ display: grid; grid-template-columns: auto 1fr; column-gap: 10px; padding: 7px 10px; border-radius: 10px;
  border: 1px solid transparent; }}
.os-cov .ck {{ grid-row: span 2; display: inline-flex; padding-top: 1px; color: #16A34A; }}
.os-cov .ln {{ font-size: 13.5px; font-weight: 600; color: {TEXT}; }}
.os-cov .by {{ font-size: 12px; color: {TEXT_2}; }}
.os-cov.on {{ background: {ACCENT_TINT}; border-color: {tint(ACCENT, .25)}; }}
.os-cov.on .ck, .os-cov.on .by {{ color: {ACCENT}; }}
.os-muted {{ display: flex; align-items: center; gap: 6px; color: {MUTED}; font-size: 12px; margin: 4px 0 0; }}
.os-risk .cap {{ color: {TEXT_2}; font-size: 12px; font-weight: 500; text-transform: uppercase; letter-spacing: .04em; }}

/* ---- motion: lift on hover, press on tap, respect reduced motion ---- */
@keyframes os-rise {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: none; }} }}
.os-card, .os-kpi, .os-banner-insight, .os-alert, .os-action {{ animation: os-rise .25s ease-out both; }}
.os-card, .os-kpi, .os-alert, .os-action, .os-stone, .os-banner-insight, [data-testid="stVerticalBlockBorderWrapper"],
[class*="st-key-card_"] {{ transition: transform .2s ease, box-shadow .2s ease; }}
.os-card:hover, .os-kpi:hover, .os-alert:hover, .os-stone:hover, .os-banner-insight:hover, [data-testid="stVerticalBlockBorderWrapper"]:hover,
[class*="st-key-card_"]:hover {{ transform: translateY(-4px); box-shadow: {HOVER_SHADOW}; }}
.os-action:hover {{ transform: translateY(-2px); box-shadow: {HOVER_SHADOW}; }}
.os-card:active, .os-kpi:active, .os-alert:active, .os-action:active, .os-stone:active,
[data-testid="stVerticalBlockBorderWrapper"]:active, [class*="st-key-card_"]:active {{ transform: scale(.98); }}
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{ animation: none !important; transition: none !important; }}
  .os-card:hover, .os-kpi:hover, .os-alert:hover, .os-action:hover, .os-stone:hover, .os-banner-insight:hover,
  [data-testid="stVerticalBlockBorderWrapper"]:hover, [class*="st-key-card_"]:hover,
  .os-card:active, .os-kpi:active, .os-alert:active, .os-action:active, .os-stone:active,
  [class*="st-key-card_"]:active {{ transform: none !important; }}
}}

/* ---- bordered Streamlit containers as cards ---- */
[class*="st-key-card_"] {{ background: {SURFACE}; border: 1px solid {BORDER} !important; border-radius: 16px;
  box-shadow: {SHADOW}; padding: 18px 20px; }}
[class*="st-key-card_"] [data-testid="stPlotlyChart"] {{ border: 0; box-shadow: none; padding: 0; margin: 0; background: transparent; }}
.os-card-title {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; }}
.os-card-title .title {{ display: flex; align-items: center; gap: 8px; font-size: 16px; font-weight: 600; color: {TEXT}; }}
.os-card-title .ic {{ color: {ACCENT}; display: inline-flex; }}
.os-card-title .help {{ color: {TEXT_2}; font-size: 13px; margin-top: 2px; }}
.os-card-title .right {{ display: flex; gap: 6px; flex-wrap: wrap; }}
/* HTML cards nested in a card container drop their own chrome so cards never stack */
[class*="st-key-card_"] .os-card {{ background: transparent; border: 0; box-shadow: none; padding: 0;
  margin: 12px 0 4px; animation: none; }}
[class*="st-key-card_"] .os-card:hover, [class*="st-key-card_"] .os-card:active {{ transform: none; box-shadow: none; }}
[class*="st-key-card_"] .os-table-card {{ margin: 8px -20px 0; }}
[class*="st-key-card_"] .os-table th:first-child, [class*="st-key-card_"] .os-table td:first-child {{ padding-left: 20px; }}
[class*="st-key-card_"] .os-table th:last-child, [class*="st-key-card_"] .os-table td:last-child {{ padding-right: 20px; }}
[class*="st-key-card_"] [data-testid="stExpander"] details {{ border-radius: 12px; border-color: {BORDER}; }}
[class*="st-key-card_"] .os-sky {{ margin-top: 12px; border-radius: 14px; }}

/* ---- priority actions ---- */
.os-actions {{ display: grid; gap: 8px; }}
.os-action {{ display: grid; grid-template-columns: 1fr auto auto; align-items: center; gap: 12px;
  border: 1px solid {BORDER}; border-radius: 12px; padding: 10px 12px; background: {SURFACE}; cursor: pointer; }}
.os-action .what {{ min-width: 0; }}
.os-action .pillcol {{ margin-bottom: 4px; }}
.os-action .name {{ font-weight: 600; font-size: 14px; color: {TEXT}; overflow-wrap: anywhere; }}
.os-action .detail {{ color: {TEXT_2}; font-size: 12px; line-height: 1.4; overflow-wrap: anywhere; }}
.os-action .amt {{ font-weight: 700; font-size: 14px; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.os-action .chev {{ color: {MUTED}; display: inline-flex; }}
.os-action:hover .chev {{ color: {ACCENT}; }}
.os-action.empty {{ display: flex; gap: 8px; color: #16A34A; font-weight: 500; cursor: default; }}

/* ---- cards ---- */
.os-card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS}; box-shadow: {SHADOW};
  padding: 16px 24px; margin-bottom: 16px; }}
.os-card h4 {{ margin: 0 0 8px 0; color: {TEXT}; font-size: 16px; font-weight: 600; }}
.os-card p {{ margin: 0; color: {TEXT_2}; line-height: 1.55; font-size: 14px; }}
[data-testid="stPlotlyChart"] {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS};
  box-shadow: {SHADOW}; padding: 8px 12px; margin-bottom: 8px; overflow: hidden; }}
.os-rec .head {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;
  margin-bottom: 12px; }}
.os-rec .name {{ font-size: 16px; font-weight: 600; color: {TEXT}; }}
.os-rec .stats {{ display: flex; gap: 32px; flex-wrap: wrap; margin-bottom: 12px; }}
.os-rec .stat .label {{ color: {TEXT_2}; font-size: 12px; font-weight: 500; text-transform: uppercase; letter-spacing: .04em; }}
.os-rec .stat .value {{ color: {TEXT}; font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; margin-top: 2px; }}
.os-check {{ display: flex; gap: 10px; align-items: flex-start; padding: 10px 0; border-bottom: 1px solid {BORDER}; }}
.os-check:last-child {{ border-bottom: 0; padding-bottom: 0; }}
.os-check .icon {{ display: inline-flex; padding-top: 2px; }}
.os-check .rule {{ font-weight: 600; color: {TEXT}; font-size: 14px; }}
.os-check .state {{ font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; margin-left: 8px; }}
.os-check .msg {{ color: {TEXT_2}; font-size: 13px; line-height: 1.45; margin-top: 2px; }}

/* ---- page header & section ---- */
.os-header {{ display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap;
  margin: 8px 0 12px; }}
.os-header .lead {{ display: flex; align-items: center; gap: 14px; min-width: 0; }}
.os-header .tile {{ width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center; flex: none;
  color: {ACCENT}; background: {ACCENT_TINT}; box-shadow: inset 0 0 0 1px rgba(37,99,235,.12); }}
.os-header .title {{ font-size: 28px; font-weight: 700; color: {TEXT}; line-height: 1.2; letter-spacing: -.01em; }}
.os-header .subtitle {{ color: {TEXT_2}; font-size: 14px; margin-top: 4px; }}
.os-section {{ margin: 24px 0 8px 0; }}
.os-section .title {{ font-size: 18px; font-weight: 600; color: {TEXT}; }}
.os-section .help {{ color: {TEXT_2}; font-size: 13px; margin-top: 2px; }}

/* ---- pills, badges, chips ---- */
.os-pill {{ display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 999px;
  font-size: 12px; font-weight: 600; line-height: 20px; white-space: nowrap; }}
.os-pill .dot {{ width: 6px; height: 6px; border-radius: 50%; background: currentColor; }}
.os-tip {{ border-bottom: 1px dotted {MUTED}; cursor: help; }}

/* ---- insight banner ---- */
.os-banner-insight {{ display: flex; gap: 12px; align-items: flex-start; border-radius: 12px; padding: 14px 18px;
  margin-bottom: 16px; font-size: 15px; font-weight: 500; color: {TEXT}; border: 1px solid; }}
.os-banner-insight .icon {{ display: inline-flex; padding-top: 1px; }}

/* ---- KPI cards ---- */
.os-kpi-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin: 8px 0 16px; }}
.os-kpi {{ display: flex; gap: 14px; align-items: flex-start; background: {SURFACE}; border: 1px solid {BORDER};
  border-radius: 16px; box-shadow: {SHADOW}; padding: 16px 18px; height: 100%; min-width: 0; }}
.os-kpi .tile {{ width: 48px; height: 48px; border-radius: 12px; display: grid; place-items: center; flex: none; }}
.os-kpi .body {{ flex: 1; min-width: 0; }}
.os-kpi .vrow {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; }}
.os-kpi .vrow .value {{ flex: 0 0 auto; }}
.os-kpi .os-spark {{ flex: 0 1 72px; min-width: 0; width: 72px; height: 28px; }}
.os-kpi .value {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.os-kpi .label {{ color: {TEXT_2}; font-size: 12px; font-weight: 500; text-transform: uppercase; letter-spacing: .04em; }}
.os-kpi .value {{ color: {TEXT}; font-size: clamp(22px, 2vw, 28px); font-weight: 700; margin-top: 2px;
  font-variant-numeric: tabular-nums; line-height: 1.2; }}
.os-kpi .hint, .os-kpi .delta {{ color: {TEXT_2}; font-size: 12px; margin-top: 4px; line-height: 1.4; }}
.os-kpi .delta {{ display: flex; align-items: flex-start; gap: 4px; }}
.os-kpi .delta .arr {{ display: inline-flex; flex: none; padding-top: 1px; }}

/* ---- alert rows ---- */
.os-alert {{ display: block; background: {SURFACE}; border: 1px solid {BORDER};
  border-left: 4px solid {ACCENT}; border-radius: 10px; padding: 10px 14px; margin-bottom: 8px; color: {TEXT};
  font-size: 14px; line-height: 1.45; box-shadow: {SHADOW}; }}
.os-alert.os-alert-row {{ display: flex; gap: 10px; align-items: flex-start; }}
.os-alert .icon {{ display: inline-flex; padding-top: 1px; }}
.os-alert .sev {{ font-weight: 700; text-transform: uppercase; font-size: 11px; letter-spacing: .04em; margin-right: 8px; }}

/* ---- tables ---- */
.os-table-card {{ padding: 16px 0 8px; }}
.os-table-card h4 {{ padding: 0 24px; }}
.os-table-wrap {{ overflow-x: auto; }}
.os-table {{ width: 100%; border-collapse: collapse; margin: 0; display: table; font-size: 14px; color: {TEXT}; }}
.os-table th, .os-table td {{ border: 0; }}
.os-table th {{ text-align: left; color: {TEXT_2}; font-size: 12px; font-weight: 500; text-transform: uppercase;
  letter-spacing: .04em; padding: 10px 12px; border-bottom: 1px solid {BORDER}; white-space: nowrap; background: #FAFBFD; }}
.os-table td {{ padding: 10px 12px; border-bottom: 1px solid {BORDER}; vertical-align: middle; }}
.os-table td.num, .os-table td:first-child {{ white-space: nowrap; }}
.os-table tr:last-child td {{ border-bottom: 0; }}
.os-table tbody tr:hover td {{ background: {ACCENT_TINT}; }}
.os-table .sub {{ color: {MUTED}; font-size: 12px; font-weight: 400; margin-top: 2px; }}
.os-table .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.stDownloadButton button {{ border-radius: 10px; border: 1px solid {BORDER}; background: {SURFACE}; color: {TEXT};
  font-weight: 600; box-shadow: {SHADOW}; }}
.stDownloadButton button:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}

/* ---- segmented control & tabs ---- */
[data-testid="stButtonGroup"] {{ margin-bottom: 8px; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 8px; border-bottom: 1px solid {BORDER}; }}
.stTabs [data-baseweb="tab"] p {{ font-weight: 600; font-size: 14px; }}

/* ---- Before vs After split card ---- */
.os-split {{ display: grid; grid-template-columns: 1fr 1fr; padding: 0; overflow: hidden; }}
.os-split .side {{ padding: 20px 24px; display: grid; gap: 14px; align-content: start; }}
.os-split .side.after {{ background: {tint("#16A34A", .05)}; border-left: 1px solid {BORDER}; }}
.os-split .tag {{ font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: {TEXT_2}; }}
.os-split .after .tag {{ color: #16A34A; }}
.os-split .m .label {{ color: {TEXT_2}; font-size: 12px; font-weight: 500; text-transform: uppercase; letter-spacing: .04em; }}
.os-split .m .value {{ font-size: 24px; font-weight: 700; color: {TEXT}; font-variant-numeric: tabular-nums;
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
.os-split .delta {{ display: inline-flex; align-items: center; gap: 3px; font-size: 12px; font-weight: 700;
  padding: 2px 8px; border-radius: 999px; }}
@media (max-width: 720px) {{ .os-split {{ grid-template-columns: 1fr; }} .os-split .side.after {{ border-left: 0;
  border-top: 1px solid {BORDER}; }} }}

/* ---- comparison bars ---- */
.os-bar-row {{ margin: 12px 0; }}
.os-bar-row .lbl {{ display: flex; justify-content: space-between; gap: 8px; font-size: 13px; color: {TEXT_2}; }}
.os-bar-row .lbl b {{ color: {TEXT}; font-variant-numeric: tabular-nums; }}
.os-bar-row .track {{ background: {GRID}; border-radius: 6px; height: 10px; margin-top: 6px; }}
.os-bar-row .fill {{ height: 10px; border-radius: 6px; }}
.os-card p.os-note {{ color: {TEXT_2}; font-size: 13px; margin-top: 8px; }}

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
  background: radial-gradient(circle at 35% 35%, #fefce8, #fde68a); box-shadow: 0 0 40px 12px rgba(254,249,195,.18); opacity: .9; }}
.os-banner {{ position: relative; color: #e2e8f0; margin-bottom: 20px; }}
.os-banner .big {{ font-size: 32px; font-weight: 800; color: #f8fafc; font-variant-numeric: tabular-nums; }}
.os-banner .small {{ color: #94a3b8; font-size: 14px; }}
.os-yard {{ position: relative; display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 20px;
  padding-bottom: 12px; border-bottom: 6px solid #14532d; }}
.os-stone {{ background: linear-gradient(180deg, #475569, #334155 70%, #1e293b); border-radius: 90px 90px 10px 10px;
  padding: 26px 14px 16px; text-align: center; color: #e2e8f0; border: 1px solid #64748b;
  box-shadow: 0 8px 18px rgba(0,0,0,.45); cursor: help; }}
.os-stone:hover {{ box-shadow: 0 14px 26px rgba(0,0,0,.55) !important; }}
.os-stone .pill-wrap {{ margin-top: 10px; }}
.os-stone .ic {{ display: flex; justify-content: center; margin-bottom: 6px; opacity: .9; }}
.os-banner .small, .os-hint {{ display: flex; align-items: center; gap: 6px; }}
.os-hint {{ position: relative; color: #94a3b8; font-size: 12px; margin-top: 12px; }}
.os-empty-yard {{ color: #cbd5e1; padding: 24px 0; }}
.os-stone .epitaph {{ font-family: Georgia, serif; font-size: 17px; font-weight: 700; letter-spacing: .08em; color: #f1f5f9; }}
.os-stone .name {{ font-weight: 700; margin: 8px 0 2px; word-break: break-word; }}
.os-stone .meta {{ color: #cbd5e1; font-size: 12px; line-height: 1.5; }}
.os-stone .cost {{ font-size: 18px; font-weight: 700; color: #fde68a; margin: 6px 0; }}
</style>
"""


def inject_css() -> None:
    """Inject the global CSS (call once per run, before any page renders)."""
    st.markdown(CSS, unsafe_allow_html=True)

