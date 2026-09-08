"""
utils/styles.py
---------------
Centralised CSS injected into every Streamlit page.
Call inject_global_styles() at the top of each page module.
"""

GLOBAL_CSS = """
<style>
/* ── Google Font ─────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ── Root palette ────────────────────────────────────────── */
:root {
    --bg-primary:    #0a0e1a;
    --bg-secondary:  #111827;
    --bg-card:       #1a2235;
    --bg-card-hover: #1f2a40;
    --accent-blue:   #3b82f6;
    --accent-cyan:   #06b6d4;
    --accent-green:  #10b981;
    --accent-yellow: #f59e0b;
    --accent-red:    #ef4444;
    --text-primary:  #f1f5f9;
    --text-secondary:#94a3b8;
    --text-muted:    #64748b;
    --border:        rgba(59,130,246,0.15);
    --glow-blue:     0 0 20px rgba(59,130,246,0.3);
    --glow-cyan:     0 0 20px rgba(6,182,212,0.3);
}

/* ── Base app ─────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
}

/* Streamlit main block */
.stApp {
    background: linear-gradient(135deg, #0a0e1a 0%, #0d1424 50%, #0a1628 100%) !important;
}

/* ── Sidebar ──────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1424 0%, #111827 100%) !important;
    border-right: 1px solid var(--border) !important;
}

[data-testid="stSidebar"] * {
    color: var(--text-primary) !important;
}

/* ── Top header banner ────────────────────────────────────── */
.uav-header {
    background: linear-gradient(135deg, #0f1d35 0%, #1a2a4a 50%, #0f1d35 100%);
    border: 1px solid rgba(59,130,246,0.3);
    border-radius: 12px;
    padding: 18px 28px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: var(--glow-blue), inset 0 1px 0 rgba(255,255,255,0.05);
    position: relative;
    overflow: hidden;
}

.uav-header::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, #3b82f6, #06b6d4, transparent);
}

.uav-header .uav-id {
    font-size: 1.4rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    background: linear-gradient(135deg, #60a5fa, #06b6d4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.uav-header .mission-name {
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-top: 2px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.uav-header .status-badge {
    padding: 6px 16px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

.status-live {
    background: rgba(16,185,129,0.15);
    border: 1px solid rgba(16,185,129,0.4);
    color: #10b981;
    box-shadow: 0 0 12px rgba(16,185,129,0.2);
}

.status-replay {
    background: rgba(245,158,11,0.15);
    border: 1px solid rgba(245,158,11,0.4);
    color: #f59e0b;
    box-shadow: 0 0 12px rgba(245,158,11,0.2);
}

/* ── Metric cards ─────────────────────────────────────────── */
.metric-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    text-align: center;
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
}

.metric-card::after {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, #3b82f6, #06b6d4);
    opacity: 0;
    transition: opacity 0.3s ease;
}

.metric-card:hover {
    border-color: rgba(59,130,246,0.4);
    box-shadow: var(--glow-blue);
    transform: translateY(-2px);
}

.metric-card:hover::after { opacity: 1; }

/* ── Section headers ─────────────────────────────────────── */
.section-title {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--accent-cyan);
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
}

/* ── Streamlit widget overrides ──────────────────────────── */
div[data-testid="stSelectbox"] label,
div[data-testid="stTextInput"] label,
div[data-testid="stSlider"] label {
    color: var(--text-secondary) !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.04em !important;
}

.stSelectbox select,
.stTextInput input {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-primary) !important;
    border-radius: 8px !important;
}

/* Radio / toggle buttons */
.stRadio > div {
    gap: 8px !important;
}

.stRadio label {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    padding: 8px 16px !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    color: var(--text-secondary) !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
}

.stRadio label:hover {
    border-color: var(--accent-blue) !important;
    color: var(--text-primary) !important;
}

/* Plotly chart backgrounds */
.js-plotly-plot .plotly .main-svg {
    background: transparent !important;
}

/* Dividers */
hr {
    border-color: var(--border) !important;
    margin: 24px 0 !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg-primary); }
::-webkit-scrollbar-thumb { background: var(--accent-blue); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--accent-cyan); }

/* Streamlit default padding tweak */
.block-container {
    padding-top: 2rem !important;
    padding-bottom: 2rem !important;
    max-width: 1400px !important;
}
</style>
"""

SIDEBAR_CSS = """
<style>
/* Sidebar nav label */
.sidebar-logo {
    text-align: center;
    padding: 16px 0 24px 0;
    border-bottom: 1px solid rgba(59,130,246,0.15);
    margin-bottom: 20px;
}

.sidebar-logo .logo-text {
    font-size: 1.1rem;
    font-weight: 700;
    background: linear-gradient(135deg, #60a5fa, #06b6d4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: 0.05em;
}

.sidebar-logo .logo-sub {
    font-size: 0.7rem;
    color: #64748b;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-top: 2px;
}

.sidebar-section {
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #475569;
    margin: 20px 0 8px 0;
    padding: 0 4px;
}
</style>
"""


def inject_global_styles():
    """Call this at the top of every page to apply the shared design system."""
    import streamlit as st
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
    st.markdown(SIDEBAR_CSS, unsafe_allow_html=True)


def render_header(uav_id: str, mission_name: str, mode: str):
    """Render the top header bar with UAV info and mode badge."""
    import streamlit as st
    badge_class = "status-live" if mode == "Live" else "status-replay"
    dot = "🟢" if mode == "Live" else "🟡"
    st.markdown(f"""
    <div class="uav-header">
        <div>
            <div class="uav-id">✈ {uav_id}</div>
            <div class="mission-name">📡 {mission_name}</div>
        </div>
        <div class="status-badge {badge_class}">{dot} {mode} Mode</div>
    </div>
    """, unsafe_allow_html=True)


def section_title(text: str):
    """Render a styled section heading."""
    import streamlit as st
    st.markdown(f'<div class="section-title">{text}</div>', unsafe_allow_html=True)
