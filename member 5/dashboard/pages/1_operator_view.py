"""
pages/1_operator_view.py — Operator View (Pilot-facing)
=========================================================
Step 14 ✅ — Twin overlay charts removed; compact 3-channel status strip added
             (charts live exclusively in Maintenance View now)
Step 16 ✅ — Edge cases: zero-magnitude channel filter, 50-alert cap,
             "Waiting for signal" placeholder, no-tick guard
"""

import streamlit as st
import time as _time

from utils.styles import inject_global_styles, render_header, section_title
from utils.session import init_session, get, set_val
from utils.connector import get_engine, FAULT_TYPES
from utils.charts import (
    build_health_gauge,
    build_history_from_engine,
    build_rul_card_html,
    build_classification_badge_html,
    build_explainability_bar,
    CHANNEL_META,
)


def _hex_to_rgb(hex_color: str) -> str:
    """Convert '#60a5fa' → '96,165,250' for CSS rgba() usage."""
    h = hex_color.lstrip("#")
    return ",".join(str(int(h[i:i+2], 16)) for i in (0, 2, 4))


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Operator View — DRDO Digital Twin",
    page_icon="🎛",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session()
inject_global_styles()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="sidebar-logo">
        <div class="logo-text">🛩 DIGITAL TWIN</div>
        <div class="logo-sub">DRDO · SIH26054</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section">⚡ Data Source Mode</div>', unsafe_allow_html=True)
    mode = st.radio("Mode", ["Live", "Replay"],
                    index=0 if get("mode") == "Live" else 1, key="op_mode")
    st.session_state["mode"] = mode

    replay_file = None
    if mode == "Replay":
        st.markdown('<div class="sidebar-section">📂 Replay File</div>', unsafe_allow_html=True)
        replay_file = st.file_uploader("Upload Mission Log CSV", type=["csv"], key="op_replay")
        if replay_file:
            st.session_state["replay_file"] = replay_file
            st.success(f"✅ `{replay_file.name}`")
        elif get("replay_file") is None:
            st.info("Upload a mission-log CSV to begin replay.")

        # ── Innovation A: Time-Warp Replay Scrubber ──────────────────────────
        st.markdown('<div class="sidebar-section">🎬 Time-Warp Replay</div>', unsafe_allow_html=True)
        st.caption("Drag to scrub through mission history frame-by-frame.")
        _tw_n = st.session_state.get("op_n_ticks", 60)
        replay_tick = st.slider(
            "Mission tick cursor",
            min_value=1, max_value=_tw_n, value=_tw_n,
            key="op_replay_tick",
            help="Drag left to rewind the mission. All metrics update to that point in time.",
        )
        st.session_state["op_replay_tick_val"] = replay_tick
        # Progress indicator
        _pct = int(replay_tick / max(_tw_n, 1) * 100)
        st.markdown(f"""
        <div style="margin-top:6px;">
            <div style="height:4px; background:rgba(148,163,184,0.12);
                        border-radius:2px; overflow:hidden; margin-bottom:5px;">
                <div style="width:{_pct}%; height:100%; background:#60a5fa;
                            border-radius:2px; transition:width 0.2s;"></div>
            </div>
            <div style="display:flex; justify-content:space-between;">
                <span style="font-size:0.68rem; color:#60a5fa; font-weight:700;">Tick {replay_tick} / {_tw_n}</span>
                <span style="font-size:0.68rem; color:#475569;">{_pct}% elapsed</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # Mission profile (Step 10 — weighted scoring)
    st.markdown('<div class="sidebar-section">🎯 Mission Profile</div>', unsafe_allow_html=True)
    mission_profile = st.selectbox(
        "Profile",
        ["ISR Patrol", "Long-Endurance Transit", "High-Altitude Loiter",
         "Rapid-Throttle Sprint", "Hot-Weather Operations"],
        key="op_mission_profile",
    )
    st.session_state["mission_profile"] = mission_profile

    st.divider()

    # Fault simulation
    st.markdown('<div class="sidebar-section">⚡ Fault Simulation</div>', unsafe_allow_html=True)
    st.caption("Simulate a fault to see the chart gap open.")

    n_ticks = st.slider("History window", 20, 150, 60, 10, key="op_n_ticks")
    fault_at = st.slider("Inject fault at tick", 5, n_ticks - 5, 25, key="op_fault_at")
    fault_type = st.selectbox(
        "Fault type", FAULT_TYPES,
        format_func=lambda f: f.replace("_", " ").title(),
        key="op_fault_type",
    )

    col_inj, col_clr = st.columns(2)
    with col_inj:
        inject = st.button("💥 Inject", key="op_inject_btn", use_container_width=True)
    with col_clr:
        clear  = st.button("🔄 Clear",  key="op_clear_btn",  use_container_width=True)

    if inject:
        st.session_state["op_fault_at_val"]   = fault_at
        st.session_state["op_fault_type_val"] = fault_type
    if clear:
        st.session_state["op_fault_at_val"]   = None
        st.session_state["op_fault_type_val"] = "overheating"
        st.session_state.pop("op_engine", None)

    # Environmental Conditions (Block E — Scenario Simulation)
    st.markdown('<div class="sidebar-section">🌍 Environmental Conditions</div>', unsafe_allow_html=True)
    st.caption("Shifts engine baseline to match operating environment.")
    altitude_m     = st.slider("Altitude (m ASL)",   0, 8000,  1000, 250, key="op_altitude")
    ambient_temp_c = st.slider("Ambient Temp (\u00b0C)", -20, 55, 25, 1,   key="op_ambient_temp")
    throttle_pct   = st.slider("Throttle Demand (%)", 40, 100, 70, 5,    key="op_throttle_demand")

    _scenario_params = {
        "altitude_m":          altitude_m,
        "ambient_temp_c":      ambient_temp_c,
        "throttle_demand_pct": throttle_pct,
    }
    st.session_state["op_scenario_params"] = _scenario_params

    # Scenario quick-status chips
    _chips = []
    if altitude_m > 3000:  _chips.append(("\u26a0 High Altitude", "#f59e0b"))
    if ambient_temp_c > 40: _chips.append(("\u26a0 Hot Weather",  "#ef4444"))
    if throttle_pct > 85:   _chips.append(("\u26a0 High Throttle", "#ef4444"))
    if _chips:
        chip_html = " ".join(
            f'<span style="background:rgba(0,0,0,0.3); border:1px solid {c}; '
            f'color:{c}; font-size:0.62rem; font-weight:700; padding:2px 8px; '
            f'border-radius:8px;">{label}</span>'
            for label, c in _chips
        )
        st.markdown(chip_html, unsafe_allow_html=True)

    st.divider()
    st.markdown('<div class="sidebar-section">\U0001f5c2 Navigation</div>', unsafe_allow_html=True)
    st.page_link("app.py",                     label="\U0001f3e0  Home")
    st.page_link("pages/1_operator_view.py",   label="\U0001f39b  Operator View")
    st.page_link("pages/2_maintenance_view.py",label="\U0001f527  Maintenance View")
    st.page_link("pages/3_history_view.py",    label="\U0001f4c8  History View")

# ── Resolve simulation params ─────────────────────────────────────────────────
active_fault_at   = st.session_state.get("op_fault_at_val",   None)
active_fault_type = st.session_state.get("op_fault_type_val", "overheating")
_scenario_params  = st.session_state.get("op_scenario_params", {})

# ── Step 11: Engine persisted in session ──────────────────────────────────────
_engine_key    = "op_engine"
_prev_mode_key = "op_prev_mode"
_prev_csv_key  = "op_prev_csv"
_prev_scen_key = "op_prev_scenario"

_prev_mode = st.session_state.get(_prev_mode_key)
_prev_csv  = st.session_state.get(_prev_csv_key)
_prev_scen = st.session_state.get(_prev_scen_key)
_curr_csv  = getattr(replay_file, "name", None) if replay_file else None
_curr_scen = str(_scenario_params)  # string-compare for change detection

if (
    _engine_key not in st.session_state
    or _prev_mode != mode
    or _prev_csv  != _curr_csv
    or _prev_scen != _curr_scen       # reinit when scenario changes
):
    st.session_state[_engine_key]    = get_engine(mode=mode, csv_file=replay_file,
                                                  scenario_params=_scenario_params)
    st.session_state[_prev_mode_key] = mode
    st.session_state[_prev_csv_key]  = _curr_csv
    st.session_state[_prev_scen_key] = _curr_scen
    if get("mission_start_time") is None:
        set_val("mission_start_time", _time.time())

_engine = st.session_state[_engine_key]

# ── Step 16: "Waiting for signal" guard ───────────────────────────────────────
# Innovation A: in Replay mode, clamp simulation to the scrubber position
_replay_tick_val = st.session_state.get("op_replay_tick_val", n_ticks)
_sim_n_ticks = min(_replay_tick_val, n_ticks) if mode == "Replay" else n_ticks

history, composite_score = build_history_from_engine(
    engine=_engine,
    n_ticks=_sim_n_ticks,
    fault_at=active_fault_at,
    fault_type=active_fault_type,
)

_no_data = not history or all(len(v) == 0 for v in history.values())

# Derive latest actual values from last tick
def _last(ch):
    rows = history.get(ch, [])
    return rows[-1]["actual"] if rows else 0.0

latest = {ch: _last(ch) for ch in CHANNEL_META if ch != "throttle_cmd"}

_pred_raw, _act_raw = _engine.get_raw()
latest_throttle = _act_raw.get("throttle_cmd", 0.75)

# ── RUL (§2A) ─────────────────────────────────────────────────────────────────
rul_payload = _engine.get_rul(composite_score)
rul_hours   = rul_payload.get("rul_hours", 0) if rul_payload else 0
RUL_BASELINE = 280.0

# Health
health_val    = max(0.0, min(100.0, 100.0 - composite_score * 100.0))
health_color  = "#10b981" if health_val >= 70 else "#f59e0b" if health_val >= 40 else "#ef4444"
health_status = "Healthy" if health_val >= 70 else "Caution" if health_val >= 40 else "FAULT"

# Signature + Classification (§1B + §4A)
latest_sig = _engine.get_signature()
latest_cls = _engine.get_classification(latest_sig)

# ── Step 10: Mission-Reliability Score ────────────────────────────────────────
W_HEALTH, W_RUL, W_THROT, W_PROF, W_ENV = 0.40, 0.20, 0.15, 0.10, 0.15

rul_factor      = min(100.0, (rul_hours / RUL_BASELINE) * 100.0)
throttle_factor = max(0.0, (1.0 - latest_throttle) * 100.0)

_profile_boosts = {
    "ISR Patrol":              95.0,
    "Long-Endurance Transit":  88.0,
    "High-Altitude Loiter":    82.0,
    "Rapid-Throttle Sprint":   75.0,
    "Hot-Weather Operations":  85.0,
}
profile_factor = _profile_boosts.get(mission_profile, 88.0)

# Block E — Environmental factor (altitude + temperature stress)
_alt_stress  = max(0.0, altitude_m / 8000.0)          # 0 at sea level, 1 at 8 000 m
_temp_stress = max(0.0, abs(ambient_temp_c - 20.0) / 35.0)  # deviation from 20°C
_env_factor  = max(0.0, 100.0 * (1.0 - 0.5 * _alt_stress - 0.5 * _temp_stress))

mission_score = max(0.0, min(100.0,
    W_HEALTH * health_val + W_RUL * rul_factor
    + W_THROT * throttle_factor + W_PROF * profile_factor
    + W_ENV   * _env_factor
))
ms_color = "#10b981" if mission_score >= 70 else "#f59e0b" if mission_score >= 40 else "#ef4444"
ms_label = "GO" if mission_score >= 70 else "CAUTION" if mission_score >= 40 else "NO-GO"

# ═══════════════════════════════════════════════════════════════════════════════
#  HEADER
# ═══════════════════════════════════════════════════════════════════════════════
render_header(get("uav_id"), get("mission_name"), get("mode"))

st.markdown("""
<h1 style="font-size:1.4rem; font-weight:700; color:#f1f5f9; margin-bottom:4px;">
    🎛 Operator View
</h1>
<p style="color:#64748b; font-size:0.85rem; margin-bottom:4px;">
    Pilot / Mission Controller · Real-time engine health · minimal clutter
</p>
""", unsafe_allow_html=True)

# Step 16 — "Waiting for signal" state
if _no_data:
    st.markdown("""
    <div style="background:rgba(59,130,246,0.06); border:1px solid rgba(59,130,246,0.2);
                border-radius:12px; padding:40px; text-align:center; margin:32px 0;">
        <div style="font-size:2.4rem; margin-bottom:12px;">⏳</div>
        <div style="font-size:1rem; font-weight:700; color:#60a5fa;">Waiting for signal…</div>
        <div style="font-size:0.82rem; color:#475569; margin-top:8px;">
            No tick data received yet. Ensure M1's data source is running,<br>
            or use the sidebar fault simulator to generate demo data.
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# Fault banner
if active_fault_at:
    ft_label = active_fault_type.replace("_", " ").title()
    st.markdown(f"""
    <div style="background:rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.35);
                border-radius:8px; padding:10px 18px; margin-bottom:12px;
                font-size:0.85rem; color:#fca5a5; display:flex; align-items:center; gap:10px;">
        <span style="font-size:1.1rem;">⚠️</span>
        <span>FAULT ACTIVE: <strong>{ft_label}</strong> — injected at tick {active_fault_at}.
        Health: <strong style="color:#ef4444">{health_val:.0f}%</strong> ·
        Score: <strong style="color:#ef4444">{composite_score:.3f}</strong></span>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
#  ROW 1 — Health Gauge | Mission Score | 8 Metric Cards
# ═══════════════════════════════════════════════════════════════════════════════
section_title("📊 Engine Health & Mission Status")

gauge_col, mission_col, metrics_col = st.columns([1.1, 1.1, 2.8], gap="large")

with gauge_col:
    fig_gauge = build_health_gauge(composite_score, height=230)
    st.plotly_chart(fig_gauge, use_container_width=True, config={"displayModeBar": False})

with mission_col:
    ms_rgb = "16,185,129" if ms_label == "GO" else "245,158,11" if ms_label == "CAUTION" else "239,68,68"
    st.markdown(f"""
    <div class="metric-card" style="padding:16px; text-align:center; height:230px;
         display:flex; flex-direction:column; align-items:center; justify-content:center;">
        <div style="font-size:0.65rem; color:#94a3b8; letter-spacing:0.1em;
                    text-transform:uppercase; margin-bottom:6px;">Mission Success Prob.</div>
        <div style="font-size:3.2rem; font-weight:800; color:{ms_color}; line-height:1;">{mission_score:.0f}%</div>
        <div style="margin:8px 0 6px 0; font-size:0.72rem;
                    background:rgba({ms_rgb},0.12); border:1px solid rgba({ms_rgb},0.35);
                    border-radius:20px; padding:4px 14px; color:{ms_color};
                    font-weight:700; letter-spacing:0.1em;">{ms_label}</div>
        <div style="font-size:0.62rem; color:#64748b; margin-top:4px; line-height:1.5;
                    text-align:left; width:100%; padding:0 4px;">
            <span style="color:#94a3b8">Health</span> {W_HEALTH:.0%}·{health_val:.0f} &nbsp;
            <span style="color:#94a3b8">RUL</span> {W_RUL:.0%}·{rul_factor:.0f}<br>
            <span style="color:#94a3b8">Throttle</span> {W_THROT:.0%}·{throttle_factor:.0f} &nbsp;
            <span style="color:#94a3b8">Profile</span> {W_PROF:.0%}·{profile_factor:.0f}
        </div>
        <div style="font-size:0.60rem; color:#334155; margin-top:4px; font-style:italic;">
            {mission_profile}
        </div>
    </div>
    """, unsafe_allow_html=True)

with metrics_col:
    mc1, mc2, mc3, mc4 = st.columns(4)
    row1 = [
        ("RPM",        f"{latest['rpm']:.0f}",            "#60a5fa"),
        ("EGT °C",     f"{latest['egt']:.1f}",            "#f59e0b"),
        ("CHT °C",     f"{latest['cht']:.1f}",            "#ef4444"),
        ("Oil P (bar)",f"{latest['oil_pressure']:.2f}",   "#10b981"),
    ]
    for col, (label, val, color) in zip([mc1, mc2, mc3, mc4], row1):
        with col:
            st.markdown(f"""
            <div class="metric-card" style="padding:14px; text-align:center; min-height:90px;">
                <div style="font-size:0.62rem; color:#64748b; letter-spacing:0.08em;
                            text-transform:uppercase; margin-bottom:5px;">{label}</div>
                <div style="font-size:1.5rem; font-weight:700; color:{color};">{val}</div>
            </div>
            """, unsafe_allow_html=True)

    mc5, mc6, mc7, mc8 = st.columns(4)
    row2 = [
        ("Oil T °C",   f"{latest['oil_temp']:.1f}",              "#a78bfa"),
        ("Fuel L/h",   f"{latest['fuel_flow']:.1f}",             "#06b6d4"),
        ("Vib (g)",    f"{latest['vibration_amplitude']:.3f}",   "#f472b6"),
    ]
    for col, (label, val, color) in zip([mc5, mc6, mc7], row2):
        with col:
            st.markdown(f"""
            <div class="metric-card" style="padding:14px; text-align:center; min-height:90px;">
                <div style="font-size:0.62rem; color:#64748b; letter-spacing:0.08em;
                            text-transform:uppercase; margin-bottom:5px;">{label}</div>
                <div style="font-size:1.5rem; font-weight:700; color:{color};">{val}</div>
            </div>
            """, unsafe_allow_html=True)

    with mc8:
        st.markdown(build_rul_card_html(rul_payload), unsafe_allow_html=True)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
#  ROW 2 — Step 14: Compact 3-channel status strip (replaces twin charts)
# ═══════════════════════════════════════════════════════════════════════════════
section_title("📡 Live Channel Status")

# Three sentinel channels most critical for a pilot
_STATUS_CHANNELS = [
    ("egt",                "EGT",          "#f59e0b", 600.0, 750.0),
    ("oil_pressure",       "Oil Pressure", "#10b981", 3.5,   5.5),
    ("vibration_amplitude","Vibration",    "#f472b6", 0.02,  0.08),
]

strip_cols = st.columns(3, gap="large")
for col, (ch, label, color, lo, hi) in zip(strip_cols, _STATUS_CHANNELS):
    val   = latest.get(ch, 0.0)
    # Normalise to 0-100% of healthy range for the bar
    rng   = hi - lo
    pct   = max(0.0, min(100.0, (val - lo) / rng * 100.0)) if rng > 0 else 50.0
    # Status: in-range vs out-of-range
    in_range = lo <= val <= hi
    bar_color = color if in_range else "#ef4444"
    status_txt = "Normal" if in_range else "⚠ OUT OF RANGE"
    status_clr = "#10b981" if in_range else "#ef4444"

    unit_map = {"egt": "°C", "oil_pressure": "bar", "vibration_amplitude": "g"}
    unit = unit_map.get(ch, "")

    with col:
        st.markdown(f"""
        <div class="metric-card" style="padding:18px 22px;">
            <div style="font-size:0.65rem; color:#64748b; letter-spacing:0.1em;
                        text-transform:uppercase; margin-bottom:10px;">{label}</div>
            <div style="display:flex; align-items:baseline; gap:8px; margin-bottom:10px;">
                <span style="font-size:2rem; font-weight:800; color:{color};">{val:.2f}</span>
                <span style="font-size:0.8rem; color:#64748b;">{unit}</span>
            </div>
            <!-- Progress bar: position within healthy range -->
            <div style="height:5px; background:rgba(148,163,184,0.12);
                        border-radius:3px; overflow:hidden; margin-bottom:6px;">
                <div style="width:{pct:.0f}%; height:100%; background:{bar_color};
                            border-radius:3px; transition:width 0.3s;"></div>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:0.6rem; color:#334155;">
                <span>{lo}</span>
                <span style="color:{status_clr}; font-weight:600;">{status_txt}</span>
                <span>{hi}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

# Step 14 — Nudge card directing pilot to Maintenance View for deep analysis
st.markdown("""
<div style="background:rgba(6,182,212,0.05); border:1px solid rgba(6,182,212,0.18);
            border-radius:10px; padding:14px 20px; margin-top:14px;
            display:flex; align-items:center; gap:14px;">
    <span style="font-size:1.5rem;">🔧</span>
    <div>
        <div style="font-size:0.82rem; font-weight:700; color:#06b6d4;">
            Need deeper analysis?
        </div>
        <div style="font-size:0.75rem; color:#475569; margin-top:2px;">
            Twin overlay charts (predicted vs actual), full residual breakdown,
            RUL trend, and explainability are in the
            <strong style="color:#f1f5f9;">Maintenance View</strong>.
            Historical mission timeline is in the
            <strong style="color:#f1f5f9;">History View</strong>.
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
#  ROW 3 — Fault Alert Panel (Step 9 + 12 + 16)
# ═══════════════════════════════════════════════════════════════════════════════
from utils.mock_data import generate_mock_alert_log
from datetime import datetime

alert_log = generate_mock_alert_log(
    n_ticks=n_ticks,
    fault_at=active_fault_at,
    fault_type=active_fault_type,
)

# Classification engine
_cls_engine = get_engine(mode=mode)
if active_fault_at:
    _cls_engine.inject_fault(active_fault_type)

# Step 16: cap at 50 alerts, track overflow
_MAX_ALERTS = 50
_overflow   = max(0, len(alert_log) - _MAX_ALERTS)
alert_log   = list(reversed(alert_log))[:_MAX_ALERTS]   # newest-first, capped
alert_count = len(alert_log)

count_color = "#ef4444" if alert_count > 5 else "#f59e0b" if alert_count > 0 else "#10b981"
count_bg    = "rgba(239,68,68,0.12)" if alert_count > 5 else "rgba(245,158,11,0.10)" if alert_count > 0 else "rgba(16,185,129,0.08)"

section_title("🚨 Fault Alert Log")

st.markdown(f"""
<div style="display:flex; align-items:center; gap:14px; margin-bottom:14px;">
    <div style="display:flex; align-items:center; gap:8px;">
        <span style="font-size:0.85rem; color:#f1f5f9; font-weight:600;">Alert History</span>
        <span style="background:{count_bg}; border:1px solid {count_color}40;
                color:{count_color}; font-size:0.72rem; font-weight:700;
                padding:2px 10px; border-radius:12px; letter-spacing:0.05em;">
            {alert_count} event{'s' if alert_count != 1 else ''}
        </span>
        {"<span style='font-size:0.68rem; color:#64748b;'>(" + str(_overflow) + " older hidden)</span>" if _overflow else ""}
    </div>
    <div style="margin-left:auto; display:flex; gap:14px; font-size:0.7rem; color:#64748b;">
        <span>🔴 Sev &gt; 0.6</span><span>🟡 Sev 0.3–0.6</span><span>🟢 Sev &lt; 0.3</span>
        <span style="color:#475569;">🔬 = sensor breakdown</span>
    </div>
</div>
""", unsafe_allow_html=True)

if alert_log:
    for i, alert in enumerate(alert_log):
        sev = alert["severity"]

        if sev >= 0.6:
            sev_color, sev_bg, sev_border, sev_icon, sev_label = (
                "#ef4444", "rgba(239,68,68,0.12)", "rgba(239,68,68,0.35)", "🔴", "HIGH")
        elif sev >= 0.3:
            sev_color, sev_bg, sev_border, sev_icon, sev_label = (
                "#f59e0b", "rgba(245,158,11,0.10)", "rgba(245,158,11,0.30)", "🟡", "MEDIUM")
        else:
            sev_color, sev_bg, sev_border, sev_icon, sev_label = (
                "#10b981", "rgba(16,185,129,0.08)", "rgba(16,185,129,0.25)", "🟢", "LOW")

        try:
            ts_str = datetime.fromtimestamp(alert["timestamp"]).strftime("%H:%M:%S.%f")[:-3]
        except Exception:
            ts_str = f"T+{alert['tick']}"

        # Dominant channel pills
        cause_pills = ""
        for ch_name, ch_val in alert.get("dominant_channels", []):
            ch_label = CHANNEL_META.get(ch_name, {}).get("label", ch_name)
            ch_color = CHANNEL_META.get(ch_name, {}).get("color", "#94a3b8")
            cause_pills += (
                f'<span style="background:rgba({_hex_to_rgb(ch_color)},0.12);'
                f'border:1px solid rgba({_hex_to_rgb(ch_color)},0.30);color:{ch_color};'
                f'font-size:0.68rem;font-weight:600;padding:2px 8px;border-radius:6px;">'
                f'{ch_label} {ch_val:.3f}</span> '
            )

        # Classification
        _alert_sig = {
            "feature_vector":    {ch: abs(v) for ch, v in alert.get("dominant_channels", [])},
            "dominant_channels": alert.get("dominant_channels", []),
            "severity":          sev,
            "fault_detected":    True,
        }
        _alert_cls     = _cls_engine.get_classification(_alert_sig)
        cls_badge_html = build_classification_badge_html(_alert_cls)
        fault_display  = (_alert_cls.get("fault_label", "").replace("_", " ").title()
                          if _alert_cls else alert["fault_type"])
        recommended    = _alert_cls.get("recommended_action", "") if _alert_cls else ""

        with st.container():
            st.markdown(f"""
            <div style="background:{sev_bg}; border:1px solid {sev_border};
                        border-radius:10px 10px 0 0; padding:12px 16px 10px 16px;">
                <div style="display:flex; align-items:center; gap:10px; margin-bottom:6px; flex-wrap:wrap;">
                    <span>{sev_icon}</span>
                    <span style="font-size:0.68rem; font-weight:700; color:{sev_color};
                                 background:rgba(0,0,0,0.3); padding:2px 8px;
                                 border-radius:4px;">{sev_label}</span>
                    <span style="font-size:0.82rem; font-weight:600; color:#f1f5f9;">{fault_display}</span>
                    {cls_badge_html}
                    <span style="margin-left:auto; font-size:0.72rem; color:#64748b;
                                 font-family:'Inter', monospace;">
                        ⏱ {ts_str} · Tick {alert['tick']}
                    </span>
                </div>
                <div style="display:flex; align-items:center; gap:12px;">
                    <div style="flex:0 0 80px; height:4px; background:rgba(148,163,184,0.1);
                                border-radius:2px; overflow:hidden;">
                        <div style="width:{sev*100:.0f}%; height:100%; background:{sev_color};
                                    border-radius:2px;"></div>
                    </div>
                    <span style="font-size:0.7rem; color:{sev_color}; font-weight:600;
                                 min-width:38px;">{sev:.3f}</span>
                    <div style="display:flex; gap:6px; align-items:center;">
                        <span style="font-size:0.65rem; color:#475569; text-transform:uppercase;">
                            Likely cause:</span>
                        {cause_pills if cause_pills else
                         '<span style="font-size:0.65rem;color:#334155;">—</span>'}
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Step 12 + 16: Expandable explainability — filter zero-magnitude channels
            raw_channels = alert.get("dominant_channels", [])
            # Step 16: filter channels where magnitude is effectively zero
            dominant_for_chart = [(ch, v) for ch, v in raw_channels if abs(v) > 1e-6]

            with st.expander(
                f"🔬 Which sensors drove this alert? ({len(dominant_for_chart)} channels)",
                expanded=False,
            ):
                if dominant_for_chart:
                    fig_exp = build_explainability_bar(dominant_for_chart, height=200)
                    st.plotly_chart(
                        fig_exp,
                        use_container_width=True,
                        config={"displayModeBar": False},
                        key=f"exp_chart_{i}_{alert['tick']}",
                    )
                    if recommended:
                        st.markdown(f"""
                        <div style="background:rgba(96,165,250,0.06);
                                    border:1px solid rgba(96,165,250,0.20);
                                    border-radius:6px; padding:8px 14px;
                                    font-size:0.78rem; color:#94a3b8; margin-top:4px;">
                            <strong style="color:#60a5fa">🔧 Recommended:</strong> {recommended}
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    # Step 16: graceful empty-channels state
                    st.markdown("""
                    <div style="padding:12px 16px; font-size:0.78rem; color:#475569;
                                background:rgba(0,0,0,0.2); border-radius:6px;">
                        ℹ️ No significant sensor contributions recorded for this alert.
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("<div style='margin-bottom:6px;'></div>", unsafe_allow_html=True)

    # Step 16: overflow indicator
    if _overflow:
        st.markdown(f"""
        <div style="text-align:center; font-size:0.75rem; color:#475569; padding:10px;
                    border:1px solid rgba(59,130,246,0.1); border-radius:8px;
                    background:rgba(0,0,0,0.2);">
            … and <strong style="color:#60a5fa">{_overflow}</strong> older event(s) not shown.
            Increase the history window or view the full timeline in
            <strong>📈 History View</strong>.
        </div>
        """, unsafe_allow_html=True)

else:
    # Step 16: distinguish true "no fault" from "no data yet"
    if composite_score < 0.01:
        st.markdown("""
        <div style="background:rgba(59,130,246,0.05); border:1px solid rgba(59,130,246,0.15);
                    border-radius:12px; padding:28px; display:flex; align-items:center; gap:16px;">
            <div style="font-size:1.8rem;">⏳</div>
            <div>
                <div style="font-size:0.9rem; font-weight:600; color:#60a5fa;">
                    No alerts yet — engine healthy
                </div>
                <div style="font-size:0.78rem; color:#475569; margin-top:4px; line-height:1.6;">
                    Composite score is near-zero. Inject a fault via sidebar to generate alerts.
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background:rgba(16,185,129,0.05); border:1px solid rgba(16,185,129,0.2);
                    border-radius:12px; padding:28px; display:flex; align-items:center; gap:16px;">
            <div style="font-size:1.8rem;">✅</div>
            <div>
                <div style="font-size:0.9rem; font-weight:600; color:#10b981;">No Fault Alerts</div>
                <div style="font-size:0.78rem; color:#475569; margin-top:4px; line-height:1.6;">
                    All channels within residual bounds.<br>
                    Use sidebar → <strong>💥 Inject</strong> to simulate a fault.
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

# ── Fault-toggle controls ─────────────────────────────────────────────────────
with st.expander("⚡ Fault Injection Controls", expanded=False):
    st.caption("Use the sidebar sliders to configure and inject faults.")
    fc1, fc2, fc3 = st.columns(3)
    faults_ui = [
        ("🔥 Overheating",       "overheating"),
        ("💧 Oil Pressure Drop", "oil_pressure_drop"),
        ("⚡ Misfire",           "misfire"),
        ("🔩 Injector Fault",    "injector_fault"),
        ("📳 Vibration Spike",   "vibration_spike"),
    ]
    active_in_session = active_fault_type if active_fault_at else None
    for col, (label, key) in zip([fc1, fc1, fc2, fc2, fc3], faults_ui):
        with col:
            is_active = (key == active_in_session)
            badge = " 🔴" if is_active else ""
            st.markdown(f"""
            <div style="padding:8px 12px; margin:4px 0; border-radius:6px; font-size:0.82rem;
                 background:{'rgba(239,68,68,0.12)' if is_active else 'rgba(30,41,59,0.5)'};
                 border:1px solid {'rgba(239,68,68,0.4)' if is_active else 'rgba(59,130,246,0.15)'};
                 color:{'#fca5a5' if is_active else '#94a3b8'};">
                {label}{badge}
            </div>
            """, unsafe_allow_html=True)
