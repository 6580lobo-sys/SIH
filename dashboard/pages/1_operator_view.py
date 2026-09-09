"""
pages/1_operator_view.py — Page 2: Digital Twin
================================================
UAV Engine Twin · DRDO SIH26054
"Explore engine components, temperature, health and live data"

Interactive engine schematic with component health overlays,
twin residual details (actual vs predicted), and component deep-dive panel.
"""

import streamlit as st
import plotly.graph_objects as go
import time as _time

from utils.styles import (
    inject_global_styles, render_mission_header, render_sidebar_nav,
    render_page_title, section_title, health_color, health_pill, severity_pill_html,
)
from utils.session import init_session, get, set_val
from utils.connector import get_engine, FAULT_TYPES
from utils.charts import CHANNEL_META

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Digital Twin — UAV Engine Twin",
    page_icon="🔷",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session()
inject_global_styles()

# ── Engine session init ───────────────────────────────────────────────────────
if "dt_engine" not in st.session_state:
    st.session_state["dt_engine"] = get_engine(mode=get("mode"))

engine = st.session_state["dt_engine"]

# Collect ticks
if "dt_history" not in st.session_state:
    st.session_state["dt_history"] = []

for _ in range(3):
    tick = engine.next_tick()
    pred, actual = engine.get_raw()
    tick["predicted"] = pred
    tick["actual"]    = actual
    st.session_state["dt_history"].append(tick)

if len(st.session_state["dt_history"]) > 80:
    st.session_state["dt_history"] = st.session_state["dt_history"][-80:]

history    = st.session_state["dt_history"]
latest     = history[-1] if history else {}
pred       = latest.get("predicted", {})
actual     = latest.get("actual", {})
composite  = latest.get("composite_score", 0.05)
health_pct = max(0.0, min(100.0, (1.0 - composite) * 100.0))
sig        = engine.get_signature()

# ── Component definitions ─────────────────────────────────────────────────────
# Each component: (display_name, primary_channel for actual/pred, weight_mod, position_desc)
COMPONENTS = {
    "Compressor": {
        "channel":    "rpm",
        "weight":     0.9,
        "temp_ch":    "cht",
        "related":    [("RPM",        "rpm"),
                       ("Fuel Flow",  "fuel_flow"),
                       ("EGT",        "egt")],
        "desc":       "Intake air compression stage · Axial compressor",
    },
    "Combustor": {
        "channel":    "egt",
        "weight":     1.2,
        "temp_ch":    "egt",
        "related":    [("EGT",        "egt"),
                       ("Fuel Flow",  "fuel_flow"),
                       ("Vibration",  "vibration_amplitude")],
        "desc":       "Fuel–air combustion chamber · Annular design",
    },
    "Turbine": {
        "channel":    "egt",
        "weight":     1.1,
        "temp_ch":    "egt",
        "related":    [("EGT",        "egt"),
                       ("RPM",        "rpm"),
                       ("Oil Temp",   "oil_temp")],
        "desc":       "Power turbine stage · Single-spool",
    },
    "Gearbox": {
        "channel":    "vibration_amplitude",
        "weight":     1.0,
        "temp_ch":    "oil_temp",
        "related":    [("Vibration",  "vibration_amplitude"),
                       ("Vib Freq",   "vibration_freq"),
                       ("Oil Temp",   "oil_temp")],
        "desc":       "Reduction gearbox · Drive output",
    },
    "Accessory Gearbox": {
        "channel":    "fuel_flow",
        "weight":     0.8,
        "temp_ch":    "oil_temp",
        "related":    [("Fuel Flow",  "fuel_flow"),
                       ("RPM",        "rpm"),
                       ("Oil Pressure","oil_pressure")],
        "desc":       "Accessory drive · Fuel pump, alternator",
    },
    "Lubrication System": {
        "channel":    "oil_pressure",
        "weight":     1.3,
        "temp_ch":    "oil_temp",
        "related":    [("Oil Pressure","oil_pressure"),
                       ("Oil Temp",   "oil_temp"),
                       ("Vibration",  "vibration_amplitude")],
        "desc":       "Oil pump, filter, scavenge system",
    },
}


def component_health(name: str) -> float:
    """Compute per-component health % based on dominant residual channel + weight."""
    meta     = COMPONENTS[name]
    ch       = meta["channel"]
    weight   = meta["weight"]
    residuals = latest.get("residuals", {})
    ch_res   = abs(residuals.get(ch, 0.0))
    from utils.mock_data import _CHANNEL_RANGES
    lo, hi, _ = _CHANNEL_RANGES.get(ch, (0.0, 1.0, ""))
    rng       = max(hi - lo, 1e-6)
    norm_res  = ch_res / rng * weight
    h         = max(0.0, min(100.0, (1.0 - norm_res * 5.0) * 100.0))
    # Also blend with composite
    h = h * 0.7 + health_pct * 0.3
    return round(h, 1)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    render_sidebar_nav(active="digital_twin")
    st.divider()
    st.markdown('<div class="sidebar-section">⚡ Data Source</div>', unsafe_allow_html=True)
    mode = st.radio("Mode", ["Live", "Replay"],
                    index=0 if get("mode") == "Live" else 1, key="dt_mode")
    set_val("mode", mode)
    st.divider()
    st.markdown('<div class="sidebar-section">🔧 Fault Injection</div>', unsafe_allow_html=True)
    fault_choice = st.selectbox("Inject Fault", ["None"] + FAULT_TYPES, key="dt_fault")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Inject", key="dt_inject", use_container_width=True):
            if fault_choice != "None":
                engine.inject_fault(fault_choice)
                st.success(f"✓ {fault_choice}")
    with c2:
        if st.button("Clear", key="dt_clear", use_container_width=True):
            engine.clear_fault()
            st.session_state["dt_history"] = []
            st.rerun()
    if st.button("🔄 Reset", key="dt_reset", use_container_width=True):
        engine.clear_fault()
        st.session_state["dt_history"] = []
        st.rerun()

# ── Header ────────────────────────────────────────────────────────────────────
fault_active = sig.get("fault_detected", False) if sig else False
render_mission_header(mode=mode, mission_id="ISR-042", has_alerts=fault_active)
render_page_title(
    "Digital Twin",
    "Explore engine components, temperature, health and live data",
)

import textwrap
import os

# ── Tab selector ─────────────────────────────────────────────────────────────
tab_choice = st.session_state.get("dt_tab", "Engine CAD Cutaway")
tabs = ["Engine CAD Cutaway", "Schematic Twin", "Thermal View", "System Overview"]
tab_sel = st.radio("View", tabs, index=tabs.index(tab_choice) if tab_choice in tabs else 0,
                   horizontal=True, key="dt_tab")

# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN CONTENT: Engine schematic + right detail panel
# ═══════════════════════════════════════════════════════════════════════════════
col_engine, col_detail = st.columns([2, 1], gap="large")

with col_engine:
    comp_healths = {name: component_health(name) for name in COMPONENTS}
    selected_comp = st.session_state.get("dt_selected_comp", "Combustor")

    if tab_sel == "Engine CAD Cutaway":
        img_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "engine_twin_cutaway.jpg")
        if os.path.exists(img_path):
            st.image(img_path, caption="DRDO UAV AUPE-95 HP Aero-Engine Digital Twin CAD Cutaway", use_container_width=True)
        else:
            st.info("High-res CAD Engine Model Active")

        # Component badges row
        badge_cols = st.columns(len(comp_healths))
        for i, (comp_name, h) in enumerate(comp_healths.items()):
            with badge_cols[i]:
                c = health_color(h)
                is_sel = (comp_name == selected_comp)
                btn_label = f"**{comp_name}**\n\n`{h:.1f}%`"
                if st.button(f"{comp_name} ({h:.1f}%)", key=f"btn_comp_{comp_name}", use_container_width=True, type="primary" if is_sel else "secondary"):
                    st.session_state["dt_selected_comp"] = comp_name
                    st.rerun()

    elif tab_sel == "Schematic Twin":
        svg_code = """<div class="dt-card" style="padding:24px; min-height:420px; position:relative;">
    <div style="text-align:center; margin-bottom:14px;">
        <div style="font-size:0.68rem; letter-spacing:0.18em; color:#4b5e7a; text-transform:uppercase; font-weight:700;">
            MALE UAV · PISTON AERO ENGINE · DIGITAL TWIN SCHEMATIC
        </div>
    </div>
    <div style="position:relative; width:100%; overflow:hidden;">
        <svg viewBox="0 0 700 240" xmlns="http://www.w3.org/2000/svg" style="width:100%; height:auto; display:block;">
            <defs>
                <linearGradient id="engBody" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stop-color="#1a2c4e"/>
                    <stop offset="50%" stop-color="#1e3460"/>
                    <stop offset="100%" stop-color="#162540"/>
                </linearGradient>
            </defs>
            <rect width="700" height="240" rx="10" fill="#0c1424" stroke="rgba(59,130,246,0.15)"/>
            <ellipse cx="60" cy="120" rx="40" ry="50" fill="#0f1a2e" stroke="#3b82f6" stroke-width="1.5"/>
            <text x="60" y="124" text-anchor="middle" fill="#3b82f6" font-size="10" font-family="monospace">AIR INTAKE</text>
            <rect x="110" y="55" width="470" height="130" rx="10" fill="url(#engBody)" stroke="rgba(59,130,246,0.3)"/>
            <rect x="120" y="65" width="95" height="110" rx="6" fill="rgba(96,165,250,0.12)" stroke="rgba(96,165,250,0.4)"/>
            <text x="167" y="125" text-anchor="middle" fill="#93c5fd" font-size="11" font-weight="700">COMPRESSOR</text>
            <rect x="225" y="65" width="115" height="110" rx="6" fill="rgba(245,158,11,0.12)" stroke="rgba(245,158,11,0.4)"/>
            <text x="282" y="125" text-anchor="middle" fill="#fcd34d" font-size="11" font-weight="700">COMBUSTOR</text>
            <rect x="350" y="65" width="105" height="110" rx="6" fill="rgba(239,68,68,0.12)" stroke="rgba(239,68,68,0.4)"/>
            <text x="402" y="125" text-anchor="middle" fill="#fca5a5" font-size="11" font-weight="700">TURBINE</text>
            <rect x="465" y="65" width="105" height="110" rx="6" fill="rgba(167,139,250,0.12)" stroke="rgba(167,139,250,0.4)"/>
            <text x="517" y="125" text-anchor="middle" fill="#d8b4fe" font-size="11" font-weight="700">GEARBOX</text>
            <ellipse cx="635" cy="120" rx="38" ry="48" fill="#0f1a2e" stroke="#ef4444" stroke-width="1.5"/>
            <text x="635" y="124" text-anchor="middle" fill="#ef4444" font-size="10" font-family="monospace">EXHAUST</text>
        </svg>
    </div>
</div>"""
        st.markdown(textwrap.dedent(svg_code), unsafe_allow_html=True)
    else:
        st.info(f"📊 {tab_sel} Telemetry & Component Heatmap Active")

    # Component selector
    st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)
    selected_comp = st.selectbox(
        "🔍 Select Component Details",
        list(COMPONENTS.keys()),
        index=list(COMPONENTS.keys()).index(
            st.session_state.get("dt_selected_comp", "Combustor")
        ),
        key="dt_selected_comp",
    )


# ── Right panel — Component Details ───────────────────────────────────────────
with col_detail:
    section_title("🔍 COMPONENT DETAILS")

    comp_meta = COMPONENTS[selected_comp]
    ch        = comp_meta["channel"]
    temp_ch   = comp_meta["temp_ch"]
    ch_health = comp_healths[selected_comp]
    h_color   = health_color(ch_health)
    h_lbl, h_pill_cls = health_pill(ch_health)

    act_temp  = actual.get(temp_ch, 0.0)
    pred_temp = pred.get(temp_ch, act_temp)
    residual  = act_temp - pred_temp
    act_ch    = actual.get(ch, 0.0)
    pred_ch   = pred.get(ch, act_ch)

    # Sparkline for the primary channel
    spark_vals = [h.get("actual", {}).get(ch, act_ch) for h in history[-25:]]
    if len(spark_vals) < 2:
        spark_vals = [act_ch, act_ch]

    ch_meta   = CHANNEL_META.get(ch, {"unit": "", "color": "#60a5fa"})
    temp_meta = CHANNEL_META.get(temp_ch, {"unit": "°C", "color": "#f59e0b"})

    st.markdown(f"""
    <div class="dt-card" style="padding:20px;">
        <!-- Component header -->
        <div style="display:flex; justify-content:space-between; align-items:flex-start;
                    margin-bottom:14px;">
            <div>
                <div style="font-size:1rem; font-weight:700; color:#f1f5f9; margin-bottom:4px;">
                    {selected_comp}
                </div>
                <div style="font-size:0.7rem; color:#4b5e7a; line-height:1.5;">
                    {comp_meta['desc']}
                </div>
            </div>
            <span class="{h_pill_cls}">{h_lbl}</span>
        </div>

        <!-- Health score bar -->
        <div style="margin-bottom:16px;">
            <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                <span style="font-size:0.68rem; color:#64748b; font-weight:700;
                             letter-spacing:0.1em; text-transform:uppercase;">Health Score</span>
                <span style="font-size:0.82rem; font-weight:700; color:{h_color};
                             font-family:monospace;">{ch_health:.1f}%</span>
            </div>
            <div class="progress-bar-outer">
                <div class="progress-bar-inner"
                     style="width:{ch_health:.1f}%; background:{h_color};
                            box-shadow: 0 0 8px {h_color}60;">
                </div>
            </div>
        </div>

        <!-- Twin data rows -->
        <div style="border:1px solid rgba(255,255,255,0.05); border-radius:8px;
                    padding:12px; margin-bottom:14px;">
            <div style="font-size:0.65rem; font-weight:700; letter-spacing:0.14em;
                        color:#4b5e7a; text-transform:uppercase; margin-bottom:10px;">
                Twin Overlay — Temperature
            </div>

            <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:10px;">
                <div>
                    <div style="font-size:0.62rem; color:#64748b; margin-bottom:3px;">Actual</div>
                    <div style="font-size:1.3rem; font-weight:700; color:#f59e0b;
                                font-family:monospace;">{act_temp:.1f}{temp_meta['unit']}</div>
                </div>
                <div>
                    <div style="font-size:0.62rem; color:#64748b; margin-bottom:3px;">Expected</div>
                    <div style="font-size:1.3rem; font-weight:700; color:#60a5fa;
                                font-family:monospace;">{pred_temp:.1f}{temp_meta['unit']}</div>
                </div>
            </div>

            <!-- Residual -->
            <div style="background:rgba(0,0,0,0.3); border-radius:6px; padding:8px 10px;
                        display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:0.68rem; color:#64748b; font-weight:700;
                             letter-spacing:0.08em; text-transform:uppercase;">
                    Residual (Δ)
                </span>
                <span style="font-size:1rem; font-weight:700;
                             font-family:monospace;
                             color:{'#ef4444' if abs(residual) > 10 else '#10b981'};">
                    {'+' if residual >= 0 else ''}{residual:.2f}{temp_meta['unit']}
                </span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Sparkline chart
    fig_spark = go.Figure()
    fig_spark.add_trace(go.Scatter(
        y=spark_vals,
        mode="lines",
        line=dict(color=ch_meta.get("color", "#60a5fa"), width=2),
        fill="tozeroy",
        fillcolor=f"{ch_meta.get('color','#60a5fa')}15",
        name="Actual",
    ))
    pred_vals = [h.get("predicted", {}).get(ch, act_ch) for h in history[-25:]]
    fig_spark.add_trace(go.Scatter(
        y=pred_vals,
        mode="lines",
        line=dict(color="#60a5fa", width=1.5, dash="dot"),
        name="Expected",
    ))
    fig_spark.update_layout(
        height=100,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=True,
        legend=dict(
            orientation="h", y=1.1,
            font=dict(size=9, color="#94a3b8"),
            bgcolor="rgba(0,0,0,0)",
        ),
        font=dict(family="Inter, sans-serif"),
    )
    st.plotly_chart(fig_spark, use_container_width=True, config={"displayModeBar": False})

    # Related parameters
    section_title("⚡ RELATED PARAMETERS")
    for param_label, param_ch in comp_meta["related"]:
        p_act  = actual.get(param_ch, 0.0)
        p_pred = pred.get(param_ch, p_act)
        p_res  = p_act - p_pred
        p_meta = CHANNEL_META.get(param_ch, {"unit": "", "color": "#60a5fa"})
        p_sign = "+" if p_res >= 0 else ""
        p_ok   = abs(p_res) < abs(p_pred) * 0.05
        p_color = "#10b981" if p_ok else "#f59e0b"

        st.markdown(f"""
        <div style="display:flex; justify-content:space-between; align-items:center;
                    padding:7px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
            <div>
                <div style="font-size:0.75rem; font-weight:600; color:#94a3b8;">{param_label}</div>
                <div style="font-size:0.68rem; color:#4b5e7a;">{p_act:.2f} {p_meta.get('unit','')}</div>
            </div>
            <div style="text-align:right;">
                <div style="font-size:0.72rem; font-weight:700; color:{p_color};
                            font-family:monospace;">Δ {p_sign}{p_res:.2f}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)
    st.button("📈 View Historical Data →", key="dt_hist_btn", use_container_width=True)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if mode == "Live":
    _time.sleep(0.15)
    st.rerun()
