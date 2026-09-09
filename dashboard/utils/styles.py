"""
utils/styles.py
---------------
Centralised CSS + render helpers for the UAV Engine Twin dashboard.
Call inject_global_styles() and render_sidebar_nav(active) at the top of every page.

Design system: deep navy mission-control, green/amber/red status palette,
Inter font, glassmorphism cards, pulsing LIVE badge.
"""

import datetime
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL CSS
# ─────────────────────────────────────────────────────────────────────────────

GLOBAL_CSS = """
<style>
/* ── Google Fonts ──────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ── CSS Custom Properties ─────────────────────────────────────────────── */
:root {
    --bg-base:        #0a0e1a;
    --bg-secondary:   #0d1220;
    --bg-card:        #131a2b;
    --bg-card-hover:  #182236;
    --bg-sidebar:     #0c1221;
    --bg-header:      #0e1628;

    --accent-blue:    #3b82f6;
    --accent-blue-dim:#1d4ed8;
    --accent-cyan:    #06b6d4;
    --accent-green:   #10b981;
    --accent-amber:   #f59e0b;
    --accent-red:     #ef4444;
    --accent-purple:  #a78bfa;

    --text-primary:   #f1f5f9;
    --text-secondary: #94a3b8;
    --text-muted:     #4b5e7a;
    --text-label:     #64748b;

    --border:         rgba(59,130,246,0.12);
    --border-hover:   rgba(59,130,246,0.35);
    --border-card:    rgba(255,255,255,0.05);

    --glow-blue:      0 0 24px rgba(59,130,246,0.25);
    --glow-green:     0 0 16px rgba(16,185,129,0.30);
    --glow-red:       0 0 16px rgba(239,68,68,0.30);
    --glow-amber:     0 0 16px rgba(245,158,11,0.30);

    --radius-sm:  6px;
    --radius-md:  10px;
    --radius-lg:  14px;
    --radius-xl:  18px;

    --font-main:  'Inter', sans-serif;
    --font-mono:  'JetBrains Mono', monospace;
}

/* ── Global reset ──────────────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: var(--font-main) !important;
    background-color: var(--bg-base) !important;
    color: var(--text-primary) !important;
}

.stApp {
    background: linear-gradient(160deg,
        #0a0e1a 0%, #0c1220 40%, #0a1228 70%, #08101e 100%) !important;
}

/* ── Hide default Streamlit chrome ─────────────────────────────────────── */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }
[data-testid="stSidebarNav"] { display: none !important; }

/* ── Main content area ─────────────────────────────────────────────────── */
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 3rem !important;
    max-width: 1440px !important;
}

/* ── Sidebar ───────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: var(--bg-sidebar) !important;
    border-right: 1px solid var(--border) !important;
    width: 220px !important;
}

[data-testid="stSidebar"] * {
    color: var(--text-primary) !important;
}

[data-testid="stSidebar"] > div:first-child {
    padding: 0 !important;
}

/* ── Sidebar logo block ────────────────────────────────────────────────── */
.sidebar-logo {
    padding: 22px 20px 18px 20px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 8px;
}

.sidebar-logo .logo-icon {
    font-size: 1.6rem;
    margin-bottom: 4px;
    display: block;
}

.sidebar-logo .logo-name {
    font-size: 0.9rem;
    font-weight: 800;
    letter-spacing: 0.04em;
    background: linear-gradient(135deg, #60a5fa, #06b6d4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1.2;
}

.sidebar-logo .logo-tagline {
    font-size: 0.58rem;
    color: var(--text-muted);
    letter-spacing: 0.15em;
    text-transform: uppercase;
    margin-top: 4px;
    font-weight: 600;
}

/* ── Sidebar nav group label ───────────────────────────────────────────── */
.nav-group-label {
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-muted);
    padding: 16px 20px 6px 20px;
}

/* ── Sidebar nav item ──────────────────────────────────────────────────── */
.nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 16px;
    margin: 2px 10px;
    border-radius: var(--radius-md);
    text-decoration: none;
    font-size: 0.82rem;
    font-weight: 500;
    color: var(--text-secondary);
    transition: all 0.2s ease;
    cursor: pointer;
    border: 1px solid transparent;
}

.nav-item:hover {
    background: rgba(59,130,246,0.08);
    color: var(--text-primary);
    border-color: var(--border);
}

.nav-item.active {
    background: rgba(59,130,246,0.18);
    color: #93c5fd;
    border-color: rgba(59,130,246,0.3);
    font-weight: 600;
}

.nav-item .nav-icon {
    font-size: 1rem;
    width: 20px;
    text-align: center;
    flex-shrink: 0;
}

/* ── Sidebar footer ────────────────────────────────────────────────────── */
.sidebar-footer {
    position: absolute;
    bottom: 0;
    left: 0; right: 0;
    padding: 14px 20px;
    border-top: 1px solid var(--border);
    background: var(--bg-sidebar);
}

.sidebar-footer .footer-org {
    font-size: 0.68rem;
    font-weight: 700;
    color: var(--text-muted);
    letter-spacing: 0.1em;
    text-transform: uppercase;
}

.sidebar-footer .footer-sub {
    font-size: 0.62rem;
    color: #2d3e55;
    margin-top: 2px;
    letter-spacing: 0.05em;
}

/* ── Top mission header ────────────────────────────────────────────────── */
.mission-header {
    background: linear-gradient(135deg, #0e1628 0%, #142038 50%, #0e1628 100%);
    border: 1px solid rgba(59,130,246,0.2);
    border-radius: var(--radius-lg);
    padding: 14px 24px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    box-shadow: var(--glow-blue), inset 0 1px 0 rgba(255,255,255,0.04);
    position: relative;
    overflow: hidden;
}

.mission-header::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg,
        transparent 0%, #3b82f6 30%, #06b6d4 70%, transparent 100%);
}

.mission-header .header-left {
    display: flex;
    align-items: center;
    gap: 14px;
}

.mission-header .header-logo-text {
    font-size: 1.05rem;
    font-weight: 800;
    background: linear-gradient(135deg, #60a5fa, #06b6d4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: 0.03em;
}

.mission-header .header-tagline {
    font-size: 0.62rem;
    color: var(--text-muted);
    letter-spacing: 0.16em;
    text-transform: uppercase;
    font-weight: 600;
    margin-top: 2px;
}

.mission-header .header-right {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
}

/* Mission ID badge */
.mission-id-badge {
    background: rgba(59,130,246,0.12);
    border: 1px solid rgba(59,130,246,0.3);
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 0.72rem;
    font-weight: 700;
    color: #93c5fd;
    letter-spacing: 0.1em;
    font-family: var(--font-mono);
}

/* LIVE pill */
.live-pill {
    display: flex;
    align-items: center;
    gap: 6px;
    background: rgba(16,185,129,0.12);
    border: 1px solid rgba(16,185,129,0.35);
    border-radius: 20px;
    padding: 5px 12px;
    font-size: 0.72rem;
    font-weight: 700;
    color: #34d399;
    letter-spacing: 0.06em;
    box-shadow: var(--glow-green);
}

.live-dot {
    width: 7px;
    height: 7px;
    background: #10b981;
    border-radius: 50%;
    animation: live-pulse 1.8s ease-in-out infinite;
    flex-shrink: 0;
}

@keyframes live-pulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(16,185,129,0.6); }
    50% { opacity: 0.7; box-shadow: 0 0 0 4px rgba(16,185,129,0); }
}

/* Replay pill */
.replay-pill {
    display: flex;
    align-items: center;
    gap: 6px;
    background: rgba(245,158,11,0.12);
    border: 1px solid rgba(245,158,11,0.35);
    border-radius: 20px;
    padding: 5px 12px;
    font-size: 0.72rem;
    font-weight: 700;
    color: #fbbf24;
    letter-spacing: 0.06em;
}

/* UTC clock */
.utc-clock {
    font-family: var(--font-mono);
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text-secondary);
    letter-spacing: 0.08em;
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 5px 10px;
}

/* Bell + avatar */
.header-bell {
    font-size: 1.1rem;
    position: relative;
    cursor: pointer;
    color: var(--text-secondary);
}

.header-bell .notif-dot {
    position: absolute;
    top: -2px; right: -3px;
    width: 7px; height: 7px;
    background: var(--accent-red);
    border-radius: 50%;
    border: 1.5px solid var(--bg-base);
}

.header-avatar {
    width: 30px; height: 30px;
    border-radius: 50%;
    background: linear-gradient(135deg, #3b82f6, #06b6d4);
    display: flex; align-items: center; justify-content: center;
    font-size: 0.75rem;
    font-weight: 700;
    color: white;
    flex-shrink: 0;
    border: 1.5px solid rgba(59,130,246,0.4);
}

/* ── Page subtitle ─────────────────────────────────────────────────────── */
.page-subtitle {
    font-size: 0.82rem;
    color: var(--text-muted);
    margin-bottom: 22px;
    letter-spacing: 0.02em;
}

.page-title {
    font-size: 1.4rem;
    font-weight: 800;
    color: var(--text-primary);
    letter-spacing: 0.01em;
    margin-bottom: 4px;
    line-height: 1.2;
}

/* ── Cards ─────────────────────────────────────────────────────────────── */
.dt-card {
    background: var(--bg-card);
    border: 1px solid var(--border-card);
    border-radius: var(--radius-lg);
    padding: 20px;
    position: relative;
    overflow: hidden;
    transition: all 0.25s ease;
}

.dt-card:hover {
    border-color: var(--border);
    box-shadow: var(--glow-blue);
    transform: translateY(-1px);
}

.dt-card::after {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, #3b82f6, #06b6d4);
    opacity: 0;
    transition: opacity 0.25s ease;
}

.dt-card:hover::after { opacity: 1; }

.dt-card.card-green { border-top: 2px solid var(--accent-green); }
.dt-card.card-amber { border-top: 2px solid var(--accent-amber); }
.dt-card.card-red   { border-top: 2px solid var(--accent-red);   }
.dt-card.card-blue  { border-top: 2px solid var(--accent-blue);  }

/* ── Card header ───────────────────────────────────────────────────────── */
.card-label {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 10px;
}

/* ── Hero metric (big number) ──────────────────────────────────────────── */
.hero-metric {
    font-size: 3rem;
    font-weight: 800;
    line-height: 1;
    font-family: var(--font-mono);
    letter-spacing: -0.02em;
}

.hero-metric.green  { color: var(--accent-green); }
.hero-metric.amber  { color: var(--accent-amber); }
.hero-metric.red    { color: var(--accent-red);   }
.hero-metric.blue   { color: #93c5fd; }

.hero-unit {
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--text-muted);
    margin-top: 2px;
    letter-spacing: 0.06em;
}

/* ── Status pills ──────────────────────────────────────────────────────── */
.pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.pill-green  { background: rgba(16,185,129,0.15); border: 1px solid rgba(16,185,129,0.4); color: #34d399; }
.pill-amber  { background: rgba(245,158,11,0.15); border: 1px solid rgba(245,158,11,0.4); color: #fbbf24; }
.pill-red    { background: rgba(239,68,68,0.15);  border: 1px solid rgba(239,68,68,0.4);  color: #f87171; }
.pill-blue   { background: rgba(59,130,246,0.15); border: 1px solid rgba(59,130,246,0.4); color: #93c5fd; }
.pill-purple { background: rgba(167,139,250,0.15);border: 1px solid rgba(167,139,250,0.4);color: #c4b5fd; }

/* ── Parameter mini-card ───────────────────────────────────────────────── */
.param-card {
    background: var(--bg-card);
    border: 1px solid var(--border-card);
    border-radius: var(--radius-md);
    padding: 14px 16px;
    position: relative;
    overflow: hidden;
    transition: all 0.2s ease;
}

.param-card:hover {
    border-color: var(--border);
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
}

.param-label {
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 6px;
}

.param-value {
    font-size: 1.5rem;
    font-weight: 700;
    line-height: 1;
    font-family: var(--font-mono);
}

.param-unit {
    font-size: 0.7rem;
    color: var(--text-muted);
    margin-left: 3px;
    font-weight: 400;
}

/* ── Fault alert banner ────────────────────────────────────────────────── */
.fault-banner {
    background: rgba(239,68,68,0.08);
    border: 1px solid rgba(239,68,68,0.35);
    border-left: 4px solid var(--accent-red);
    border-radius: var(--radius-md);
    padding: 16px 20px;
    margin-bottom: 24px;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    box-shadow: var(--glow-red);
    position: relative;
    overflow: hidden;
}

.fault-banner::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(239,68,68,0.6), transparent);
}

.fault-banner-title {
    font-size: 1rem;
    font-weight: 800;
    color: #fca5a5;
    letter-spacing: 0.04em;
    margin-bottom: 4px;
}

.fault-banner-desc {
    font-size: 0.8rem;
    color: var(--text-secondary);
    line-height: 1.5;
}

.fault-banner-badges {
    display: flex;
    flex-direction: column;
    gap: 6px;
    align-items: flex-end;
    flex-shrink: 0;
}

/* Clean / no-fault state */
.clean-banner {
    background: rgba(16,185,129,0.06);
    border: 1px solid rgba(16,185,129,0.2);
    border-left: 4px solid var(--accent-green);
    border-radius: var(--radius-md);
    padding: 14px 20px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 12px;
    color: #6ee7b7;
    font-size: 0.9rem;
    font-weight: 600;
}

/* ── Section header ─────────────────────────────────────────────────────── */
.section-header {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--accent-cyan);
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 14px;
}

/* ── Horizontal progress bar ───────────────────────────────────────────── */
.progress-bar-outer {
    background: rgba(255,255,255,0.06);
    border-radius: 4px;
    height: 6px;
    overflow: hidden;
    margin: 10px 0;
}

.progress-bar-inner {
    height: 100%;
    border-radius: 4px;
    transition: width 0.5s ease;
}

/* ── Evidence bar (for diagnostics dominant channels) ─────────────────── */
.evidence-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 7px 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}

.evidence-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text-secondary);
    width: 160px;
    flex-shrink: 0;
}

.evidence-bar-outer {
    flex: 1;
    background: rgba(255,255,255,0.05);
    border-radius: 3px;
    height: 8px;
    overflow: hidden;
}

.evidence-bar-inner {
    height: 100%;
    border-radius: 3px;
}

.evidence-delta {
    font-size: 0.72rem;
    font-family: var(--font-mono);
    font-weight: 600;
    width: 60px;
    text-align: right;
    flex-shrink: 0;
}

/* ── Status checklist ──────────────────────────────────────────────────── */
.check-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    font-size: 0.82rem;
    color: var(--text-secondary);
}

.check-row:last-child { border-bottom: none; }

.check-icon { font-size: 0.9rem; flex-shrink: 0; }

/* ── Tab bar ───────────────────────────────────────────────────────────── */
.tab-bar {
    display: flex;
    gap: 4px;
    background: rgba(0,0,0,0.3);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 4px;
    margin-bottom: 20px;
    width: fit-content;
}

.tab-btn {
    padding: 7px 18px;
    border-radius: 7px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    color: var(--text-muted);
    border: none;
    background: transparent;
    cursor: pointer;
    transition: all 0.2s ease;
}

.tab-btn:hover {
    color: var(--text-secondary);
    background: rgba(255,255,255,0.04);
}

.tab-btn.active {
    background: var(--accent-blue);
    color: white;
    box-shadow: 0 2px 8px rgba(59,130,246,0.4);
}

/* ── Plotly overrides ──────────────────────────────────────────────────── */
.js-plotly-plot .plotly .main-svg { background: transparent !important; }

/* ── Streamlit widget overrides ────────────────────────────────────────── */
div[data-testid="stSelectbox"] label,
div[data-testid="stTextInput"] label,
div[data-testid="stSlider"] label,
div[data-testid="stRadio"] label {
    color: var(--text-secondary) !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.04em !important;
}

.stTextInput input, .stSelectbox select {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-primary) !important;
    border-radius: var(--radius-sm) !important;
    font-family: var(--font-main) !important;
}

.stRadio > div { gap: 6px !important; }

.stRadio label {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    padding: 6px 14px !important;
    transition: all 0.2s ease !important;
    color: var(--text-secondary) !important;
    font-size: 0.8rem !important;
}

.stRadio label:hover {
    border-color: var(--accent-blue) !important;
    color: var(--text-primary) !important;
}

/* Buttons */
.stButton > button {
    background: rgba(59,130,246,0.12) !important;
    border: 1px solid rgba(59,130,246,0.3) !important;
    color: #93c5fd !important;
    border-radius: var(--radius-sm) !important;
    font-family: var(--font-main) !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
    letter-spacing: 0.04em !important;
    transition: all 0.2s ease !important;
}

.stButton > button:hover {
    background: rgba(59,130,246,0.22) !important;
    border-color: rgba(59,130,246,0.5) !important;
    color: #bfdbfe !important;
    box-shadow: var(--glow-blue) !important;
}

.stButton > button[kind="primary"] {
    background: var(--accent-blue) !important;
    border-color: var(--accent-blue) !important;
    color: white !important;
}

/* Dividers */
hr {
    border-color: var(--border) !important;
    margin: 20px 0 !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--bg-base); }
::-webkit-scrollbar-thumb { background: rgba(59,130,246,0.3); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--accent-blue); }

/* ── Metric sparkline container ────────────────────────────────────────── */
.sparkline-container {
    margin-top: 8px;
    opacity: 0.7;
}

/* ── Component health badge (Digital Twin page) ────────────────────────── */
.component-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.65rem;
    font-weight: 700;
    font-family: var(--font-mono);
}

/* ── Engine schematic ──────────────────────────────────────────────────── */
.engine-schematic {
    background: rgba(0,0,0,0.3);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 24px;
    text-align: center;
    position: relative;
    min-height: 380px;
    display: flex;
    align-items: center;
    justify-content: center;
}

/* ── Quick stat chip ───────────────────────────────────────────────────── */
.stat-chip {
    display: inline-flex;
    flex-direction: column;
    align-items: center;
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 8px 14px;
    min-width: 80px;
}

.stat-chip-val {
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--text-primary);
    font-family: var(--font-mono);
}

.stat-chip-label {
    font-size: 0.6rem;
    color: var(--text-muted);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-top: 2px;
    font-weight: 600;
}

/* ── In-mission pill ───────────────────────────────────────────────────── */
.in-mission-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(59,130,246,0.15);
    border: 1px solid rgba(59,130,246,0.4);
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 0.72rem;
    font-weight: 700;
    color: #93c5fd;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    animation: blink-border 2.5s ease-in-out infinite;
}

@keyframes blink-border {
    0%, 100% { border-color: rgba(59,130,246,0.4); }
    50%       { border-color: rgba(59,130,246,0.8); box-shadow: 0 0 10px rgba(59,130,246,0.3); }
}

/* ── Time range toolbar ────────────────────────────────────────────────── */
.time-pill {
    display: inline-flex;
    align-items: center;
    padding: 5px 14px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
    border: 1px solid var(--border);
    color: var(--text-muted);
    background: transparent;
}

.time-pill.active {
    background: rgba(59,130,246,0.2);
    border-color: rgba(59,130,246,0.5);
    color: #93c5fd;
}

/* ── Recommended action list ───────────────────────────────────────────── */
.action-row {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 10px 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    font-size: 0.82rem;
    color: var(--text-secondary);
    line-height: 1.5;
}

.action-row:last-child { border-bottom: none; }
.action-icon { flex-shrink: 0; font-size: 1rem; margin-top: 1px; }

/* ── Generate report button ────────────────────────────────────────────── */
.report-btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: var(--accent-blue);
    border: none;
    border-radius: var(--radius-md);
    padding: 12px 24px;
    font-size: 0.88rem;
    font-weight: 700;
    color: white;
    cursor: pointer;
    letter-spacing: 0.04em;
    transition: all 0.2s ease;
    box-shadow: 0 4px 16px rgba(59,130,246,0.4);
}

.report-btn:hover {
    background: #2563eb;
    box-shadow: 0 6px 24px rgba(59,130,246,0.55);
    transform: translateY(-1px);
}

/* ── UAV hero card ─────────────────────────────────────────────────────── */
.uav-hero-card {
    background: linear-gradient(135deg, var(--bg-card) 0%, #172040 100%);
    border: 1px solid rgba(59,130,246,0.2);
    border-radius: var(--radius-lg);
    padding: 24px;
    position: relative;
    overflow: hidden;
}

.uav-hero-card::before {
    content: '';
    position: absolute;
    top: 0; right: 0;
    width: 200px; height: 200px;
    background: radial-gradient(circle, rgba(59,130,246,0.06) 0%, transparent 70%);
    border-radius: 50%;
}

/* ── Animated scan line (decorative) ──────────────────────────────────── */
.scan-line {
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, rgba(6,182,212,0.6), transparent);
    animation: scan 3s linear infinite;
}

@keyframes scan {
    0%   { top: 0; }
    100% { top: 100%; }
}

/* ── Sidebar section label ─────────────────────────────────────────────── */
.sidebar-section {
    font-size: 0.63rem;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin: 16px 0 6px 0;
    padding: 0 4px;
}
</style>
"""


import textwrap

# ─────────────────────────────────────────────────────────────────────────────
#  PYTHON HELPERS
# ─────────────────────────────────────────────────────────────────────────────

# Nav items: (icon, label, page_file, display_key)
_NAV_ITEMS = [
    ("🏠", "Overview",         "app.py",                        "overview"),
    ("🔷", "Digital Twin",     "pages/1_operator_view.py",      "digital_twin"),
    ("📡", "Telemetry",        "pages/2_maintenance_view.py",   "telemetry"),
    ("🩺", "Diagnostics",      "pages/3_history_view.py",       "diagnostics"),
    ("🔬", "Simulation Lab",   "pages/4_simulation_lab.py",     "simulation"),
    ("📋", "Reports",          "pages/5_reports.py",            "reports"),
    ("⚙️", "Settings",         "pages/6_settings.py",           "settings"),
]


def inject_global_styles():
    """Inject the shared CSS design system. Call on every page."""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def render_sidebar_nav(active: str = "overview"):
    """
    Render the styled mission-control sidebar nav.
    """
    st.markdown(textwrap.dedent("""
<div class="sidebar-logo">
    <span class="logo-icon">✈️</span>
    <div class="logo-name">UAV ENGINE TWIN</div>
    <div class="logo-tagline">PREDICT · PREVENT · KEEP FLYING</div>
</div>
<div class="nav-group-label">Navigation</div>
"""), unsafe_allow_html=True)

    for icon, label, page_file, key in _NAV_ITEMS:
        try:
            st.page_link(page_file, label=f"{icon}  {label}")
        except Exception:
            pass

    st.markdown(textwrap.dedent("""
<div style="margin-top:24px; padding: 12px 10px 0 10px; border-top: 1px solid rgba(59,130,246,0.12);">
    <div style="font-size:0.65rem; font-weight:700; color:#4b5e7a; letter-spacing:0.12em; text-transform:uppercase;">
        DRDO | SIH26054
    </div>
    <div style="font-size:0.6rem; color:#2d3e55; margin-top:3px; letter-spacing:0.05em;">
        UAV Engine Health Monitoring
    </div>
</div>
"""), unsafe_allow_html=True)


def render_mission_header(mode: str = "Live", mission_id: str = "ISR-042",
                          has_alerts: bool = False):
    """
    Render the top mission-control header bar.
    Shows: logo/tagline | mission badge | LIVE pill | UTC clock | bell | avatar
    """
    now_utc = datetime.datetime.utcnow().strftime("%H:%M:%S UTC")
    mission_id_safe = mission_id.upper().replace(" ", "-")

    if mode == "Live":
        mode_html = '<div class="live-pill"><div class="live-dot"></div>LIVE</div>'
    else:
        mode_html = '<div class="replay-pill">⏵ REPLAY</div>'

    notif_dot = '<div class="notif-dot"></div>' if has_alerts else ""

    header_html = f"""<div class="mission-header">
    <div class="header-left">
        <span style="font-size:1.6rem;">✈️</span>
        <div>
            <div class="header-logo-text">UAV ENGINE TWIN</div>
            <div class="header-tagline">PREDICT &nbsp;|&nbsp; PREVENT &nbsp;|&nbsp; KEEP FLYING</div>
        </div>
    </div>
    <div class="header-right">
        <div class="mission-id-badge">MISSION: {mission_id_safe}</div>
        {mode_html}
        <div class="utc-clock">🕐 {now_utc}</div>
        <div class="header-bell">🔔{notif_dot}</div>
        <div class="header-avatar">MC</div>
    </div>
</div>"""

    st.markdown(textwrap.dedent(header_html), unsafe_allow_html=True)


def render_page_title(title: str, subtitle: str = ""):
    """Render the page title + subtitle."""
    sub_html = f'<div class="page-subtitle">{subtitle}</div>' if subtitle else ""
    html = f"""<div style="margin-bottom: 20px;">
    <div class="page-title">{title}</div>
    {sub_html}
</div>"""
    st.markdown(textwrap.dedent(html), unsafe_allow_html=True)


def section_title(text: str):
    """Render a section divider heading."""
    st.markdown(f'<div class="section-header">{text}</div>', unsafe_allow_html=True)


def health_color(pct: float) -> str:
    """Return CSS color string based on health percentage (0–100)."""
    if pct >= 75:
        return "#10b981"   # green
    elif pct >= 45:
        return "#f59e0b"   # amber
    else:
        return "#ef4444"   # red


def health_pill(pct: float) -> str:
    """Return the health status label and pill class."""
    if pct >= 75:
        return "Healthy", "pill pill-green"
    elif pct >= 45:
        return "Warning", "pill pill-amber"
    else:
        return "Critical", "pill pill-red"


def severity_pill_html(severity: float) -> str:
    """Return HTML for a severity badge."""
    if severity >= 0.7:
        return '<span class="pill pill-red">HIGH</span>'
    elif severity >= 0.4:
        return '<span class="pill pill-amber">MEDIUM</span>'
    else:
        return '<span class="pill pill-green">LOW</span>'


# Back-compat alias so old pages that import render_header still work
def render_header(uav_id: str, mission_name: str, mode: str):
    """Legacy shim — replaced by render_mission_header."""
    render_mission_header(mode=mode, mission_id=mission_name or "ISR-042")

