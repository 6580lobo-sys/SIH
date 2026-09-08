"""
app.py — Main entry point for the Digital Twin Dashboard
=========================================================
UAV: MALE UAV Aero Piston Engine Digital Twin
Project: SIH26054 — DRDO AI-Enabled Digital Twin
Member: M4 (Dashboard / HMI + Mission Lead)

Run:
    streamlit run app.py
"""

import streamlit as st
from utils.styles import inject_global_styles, render_header, section_title
from utils.session import init_session, get, set_val

# ── Page config (MUST be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="DRDO Digital Twin — UAV Engine Monitor",
    page_icon="✈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "DRDO AI-Enabled Digital Twin for MALE UAV Aero Piston Engine | SIH26054",
    },
)

# ── Init session state ────────────────────────────────────────────────────────
init_session()

# ── Inject global CSS ─────────────────────────────────────────────────────────
inject_global_styles()

# ═══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    # Logo / branding
    st.markdown("""
    <div class="sidebar-logo">
        <div class="logo-text">🛩 DIGITAL TWIN</div>
        <div class="logo-sub">DRDO · SIH26054</div>
    </div>
    """, unsafe_allow_html=True)

    # ── UAV Identity ──────────────────────────────────────────────────────────
    st.markdown('<div class="sidebar-section">✈ UAV Identity</div>', unsafe_allow_html=True)

    uav_id = st.text_input(
        "UAV ID",
        value=get("uav_id"),
        key="uav_id_input",
        placeholder="e.g. UAV-DRDO-001",
    )
    set_val("uav_id", uav_id)

    mission_name = st.text_input(
        "Mission Name",
        value=get("mission_name"),
        key="mission_name_input",
        placeholder="e.g. OPERATION SKYWATCH",
    )
    set_val("mission_name", mission_name)

    st.divider()

    # ── Source Mode ───────────────────────────────────────────────────────────
    st.markdown('<div class="sidebar-section">⚡ Data Source Mode</div>', unsafe_allow_html=True)

    mode = st.radio(
        "Select Mode",
        options=["Live", "Replay"],
        index=0 if get("mode") == "Live" else 1,
        key="mode_radio",
        help=(
            "**Live**: streams from M1's physics twin + M2's fault injector.\n\n"
            "**Replay**: reads a saved mission-log CSV via CsvReplaySource."
        ),
    )
    set_val("mode", mode)

    # Show replay file uploader only in Replay mode
    if mode == "Replay":
        st.markdown('<div class="sidebar-section">📂 Replay File</div>', unsafe_allow_html=True)
        replay_file = st.file_uploader(
            "Upload Mission Log CSV",
            type=["csv"],
            key="replay_uploader",
            help="Upload a mission-log CSV to replay through M1's CsvReplaySource.",
        )
        if replay_file:
            set_val("replay_file", replay_file)
            st.success(f"✅ Loaded: `{replay_file.name}`")
        elif get("replay_file") is None:
            st.info("Upload a mission-log CSV to begin replay.")

    st.divider()

    # ── Navigation ────────────────────────────────────────────────────────────
    st.markdown('<div class="sidebar-section">🗂 Navigation</div>', unsafe_allow_html=True)
    st.page_link("app.py",                               label="🏠  Home Dashboard",    icon=None)
    st.page_link("pages/1_operator_view.py",              label="🎛  Operator View",     icon=None)
    st.page_link("pages/2_maintenance_view.py",           label="🔧  Maintenance View",  icon=None)
    st.page_link("pages/3_history_view.py",               label="📈  History View",      icon=None)

    st.divider()

    # ── GAP 4: Global Reset ───────────────────────────────────────────────────
    st.markdown('<div class="sidebar-section">🔄 Demo Controls</div>', unsafe_allow_html=True)
    st.caption("Reset all faults and engine state for a clean back-to-back judge walkthrough.")
    if st.button("🔄 Reset All — Healthy Baseline",
                 key="global_reset_btn", use_container_width=True):
        _keep = {"uav_id", "mission_name"}
        _clear = [k for k in list(st.session_state.keys()) if k not in _keep]
        for _k in _clear:
            del st.session_state[_k]
        st.success("✅ All state cleared. Engine reset to healthy baseline.")
        st.rerun()

    st.divider()

    # ── System status strip ───────────────────────────────────────────────────
    st.markdown('<div class="sidebar-section">📡 System Status</div>', unsafe_allow_html=True)
    if mode == "Live":
        st.markdown("🟢 **Stream**: Active")
    else:
        st.markdown("🟡 **Stream**: Replay")

    st.caption("MALE UAV Piston Engine v2")
    st.caption("Build: SIH26054 · M4 Dashboard")


# ═══════════════════════════════════════════════════════════════════════════════
#  HOME / LANDING PAGE
# ═══════════════════════════════════════════════════════════════════════════════

# Top header banner
render_header(get("uav_id"), get("mission_name"), get("mode"))

# Page title
st.markdown("""
<h1 style="
    font-size:1.8rem;
    font-weight:800;
    background: linear-gradient(135deg, #f1f5f9, #94a3b8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 4px;
">MALE UAV Aero Piston Engine</h1>
<p style="color:#64748b; font-size:0.9rem; margin-bottom:32px;">
    AI-Enabled Digital Twin · DRDO SIH26054
</p>
""", unsafe_allow_html=True)

# ── Quick-nav cards ───────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3, gap="large")

with col1:
    st.markdown("""
    <div class="metric-card" style="text-align:left; padding:28px;">
        <div style="font-size:2rem; margin-bottom:12px;">🎛</div>
        <div style="font-size:1.1rem; font-weight:700; color:#f1f5f9; margin-bottom:6px;">
            Operator View
        </div>
        <div style="font-size:0.85rem; color:#94a3b8; line-height:1.6;">
            Real-time engine health gauge, live parameter charts,
            fault alert panel, and mission-reliability score.
            Designed for the <strong style="color:#60a5fa">pilot / mission controller</strong>.
        </div>
        <div style="margin-top:16px; font-size:0.75rem; color:#3b82f6; font-weight:600; letter-spacing:0.06em;">
            → USE THIS DURING FLIGHT
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("pages/1_operator_view.py", label="Open Operator View →")

with col2:
    st.markdown("""
    <div class="metric-card" style="text-align:left; padding:28px;">
        <div style="font-size:2rem; margin-bottom:12px;">🔧</div>
        <div style="font-size:1.1rem; font-weight:700; color:#f1f5f9; margin-bottom:6px;">
            Maintenance View
        </div>
        <div style="font-size:0.85rem; color:#94a3b8; line-height:1.6;">
            Digital twin overlay (predicted vs actual), full
            signature breakdown, RUL trend, explainability charts,
            and maintenance recommendations.
            Designed for the <strong style="color:#06b6d4">ground technician</strong>.
        </div>
        <div style="margin-top:16px; font-size:0.75rem; color:#06b6d4; font-weight:600; letter-spacing:0.06em;">
            → USE THIS FOR PRE/POST-FLIGHT ANALYSIS
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("pages/2_maintenance_view.py", label="Open Maintenance View →")

with col3:
    st.markdown("""
    <div class="metric-card" style="text-align:left; padding:28px;">
        <div style="font-size:2rem; margin-bottom:12px;">📈</div>
        <div style="font-size:1.1rem; font-weight:700; color:#f1f5f9; margin-bottom:6px;">
            History View
        </div>
        <div style="font-size:0.85rem; color:#94a3b8; line-height:1.6;">
            Composite score &amp; RUL over the full mission timeline.
            See the <strong style="color:#10b981">engine degradation story</strong>
            tick-by-tick — the narrative judges remember.
        </div>
        <div style="margin-top:16px; font-size:0.75rem; color:#10b981; font-weight:600; letter-spacing:0.06em;">
            → USE THIS FOR POST-MISSION ANALYSIS
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("pages/3_history_view.py", label="Open History View →")

st.divider()

# ── GAP 1: Architecture Diagram — Twin Data Flow ──────────────────────────────
section_title("🏗 System Architecture — Twin Data Flow")

_arch_left, _arch_right = st.columns([3, 1], gap="large")

with _arch_left:
    st.markdown("""
    <div style="background:rgba(15,23,42,0.7); border:1px solid rgba(59,130,246,0.18);
                border-radius:12px; padding:22px 26px; overflow-x:auto;">
      <div style="font-family:'Courier New',monospace; font-size:0.73rem;
                  color:#64748b; line-height:2.0; white-space:pre;">
<span style="color:#475569">          ┌──────────────────────────────────┐</span>
<span style="color:#475569">          │      </span><span style="color:#60a5fa;font-weight:700">CONTROL INPUTS</span><span style="color:#475569">             │</span>
<span style="color:#475569">          │  throttle_cmd · altitude · temp  │</span>
<span style="color:#475569">          └──────┬───────────────────┬───────┘</span>
<span style="color:#475569">                 │  (same inputs)    │</span>
<span style="color:#475569">                 ▼                   ▼</span>
<span style="color:#475569">   ┌─────────────────────┐  ┌──────────────────────┐</span>
   │ <span style="color:#3b82f6;font-weight:700">REFERENCE MODEL</span>     │  │ <span style="color:#06b6d4;font-weight:700">ACTUAL SOURCE</span>        │
<span style="color:#475569">   │ (EngineSimulator)   │  │ (pluggable)           │</span>
<span style="color:#475569">   │ Pure physics +      │  │  • M1 healthy sim     │</span>
<span style="color:#475569">   │ scenario_params     │  │  • M2 Fault Injector  │</span>
<span style="color:#475569">   │ (Block E)           │  │  • CsvReplaySource    │</span>
<span style="color:#475569">   └──────────┬──────────┘  └──────────┬───────────┘</span>
<span style="color:#475569">              │  predicted {}           │  actual {}</span>
<span style="color:#475569">              └──────────┬─────────────┘</span>
<span style="color:#475569">                         ▼</span>
<span style="color:#475569">              ┌──────────────────────┐</span>
              │ <span style="color:#10b981;font-weight:700">RESIDUAL ENGINE</span>      │
<span style="color:#475569">              │ 1. actual − predicted │</span>
<span style="color:#475569">              │ 2. normalise ÷ range  │</span>
<span style="color:#475569">              │ 3. EWMA smooth        │</span>
<span style="color:#475569">              │ 4. composite_score    │</span>
<span style="color:#475569">              └──────┬───────┬───────┘</span>
<span style="color:#475569">                     │       │       │</span>
<span style="color:#475569">                     ▼       ▼       ▼</span>
<span style="color:#475569">             ┌──────────┐ ┌──────────┐ ┌──────────┐</span>
             │<span style="color:#3b82f6;font-weight:700">M4 Gauge</span>  │ │<span style="color:#f59e0b;font-weight:700">M3 Sig.</span>   │ │<span style="color:#10b981;font-weight:700">M4 Alerts</span> │
<span style="color:#475569">             │health %   │ │dominant  │ │Mission   │</span>
<span style="color:#475569">             │miss.score │ │channels  │ │Score     │</span>
<span style="color:#475569">             └──────────┘ └──────────┘ └──────────┘</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

with _arch_right:
    for label, body, color in [
        ("Reference model gets CONTROL INPUTS, not sensor data",
         "throttle_cmd feeds the model — it predicts what RPM/EGT should be independently. Drawing an arrow from actual sensors back in would make it a filter, not a twin.",
         "#3b82f6"),
        ("Residual = actual − predicted, NOT a threshold on raw values",
         "EGT=885°C at idle (predicted=650°C) is a massive anomaly. EGT=885°C at full throttle (predicted=880°C) is fine. Context-aware, not fixed-limit.",
         "#10b981"),
        ("Actual source is PLUGGABLE",
         "Same DigitalTwin class handles: healthy sim · M2 Fault Injector · CsvReplaySource — swap without changing any page code.",
         "#06b6d4"),
    ]:
        st.markdown(f"""
        <div style="background:rgba(0,0,0,0.25); border-left:3px solid {color};
                    border-radius:0 8px 8px 0; padding:10px 14px; margin-bottom:10px;">
            <div style="font-size:0.72rem; font-weight:700; color:{color};
                        margin-bottom:5px;">{label}</div>
            <div style="font-size:0.70rem; color:#64748b; line-height:1.6;">{body}</div>
        </div>
        """, unsafe_allow_html=True)

st.divider()

# ── Mode info ─────────────────────────────────────────────────────────────────
section_title(f"{'⚡ Live Mode Active' if get('mode') == 'Live' else '🔁 Replay Mode Active'}")

if get("mode") == "Live":
    st.markdown("""
    <div style="background:rgba(16,185,129,0.06); border:1px solid rgba(16,185,129,0.25);
                border-radius:10px; padding:16px 20px; font-size:0.88rem; color:#94a3b8; line-height:1.7;">
        The dashboard is in <strong style="color:#10b981">Live Mode</strong>.
        It will read M1's per-tick residual stream and M2's fault-injection events in real time.<br>
        Navigate to <strong>Operator View</strong> to start monitoring, or use the sidebar to switch to <strong>Replay Mode</strong>.
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div style="background:rgba(245,158,11,0.06); border:1px solid rgba(245,158,11,0.25);
                border-radius:10px; padding:16px 20px; font-size:0.88rem; color:#94a3b8; line-height:1.7;">
        The dashboard is in <strong style="color:#f59e0b">Replay Mode</strong>.
        Upload a mission-log CSV in the sidebar, then navigate to <strong>Operator View</strong>
        to replay the mission through M1's <code>CsvReplaySource</code>.
    </div>
    """, unsafe_allow_html=True)
