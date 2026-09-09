"""
app.py — Page 1: Overview (Mission Control Dashboard)
=======================================================
UAV Engine Twin · DRDO SIH26054
"Live engine status, health, RUL and key insights at a glance"

Run:
    streamlit run app.py
"""

import time as _time
import math
import streamlit as st
import plotly.graph_objects as go

from utils.styles import (
    inject_global_styles, render_mission_header, render_sidebar_nav,
    render_page_title, section_title, health_color, health_pill, severity_pill_html,
)
from utils.session import init_session, get, set_val, push_tick, push_rul
from utils.connector import get_engine, FAULT_TYPES
from utils.charts import CHANNEL_META

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Overview — UAV Engine Twin",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "UAV Engine Twin · DRDO SIH26054"},
)

init_session()
inject_global_styles()

# ── Engine session init ───────────────────────────────────────────────────────
if "overview_engine" not in st.session_state:
    st.session_state["overview_engine"] = get_engine(mode=get("mode"))

engine = st.session_state["overview_engine"]

# ── Collect data ticks ────────────────────────────────────────────────────────
N_TICKS = 80
if "ov_history" not in st.session_state:
    st.session_state["ov_history"] = []

for _ in range(4):   # advance a few ticks each load
    tick = engine.next_tick()
    pred, actual = engine.get_raw()
    tick["predicted"] = pred
    tick["actual"]    = actual
    st.session_state["ov_history"].append(tick)

if len(st.session_state["ov_history"]) > N_TICKS:
    st.session_state["ov_history"] = st.session_state["ov_history"][-N_TICKS:]

history = st.session_state["ov_history"]
latest  = history[-1] if history else {}
pred    = latest.get("predicted", {})
actual  = latest.get("actual",    {})
composite = latest.get("composite_score", 0.05)
health_pct = max(0.0, min(100.0, (1.0 - composite) * 100.0))
rul_data = engine.get_rul(composite)
sig      = engine.get_signature()
cls_data = engine.get_classification(sig)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    render_sidebar_nav(active="overview")
    st.divider()
    st.markdown('<div class="sidebar-section">⚡ Data Source</div>', unsafe_allow_html=True)
    mode = st.radio("Mode", ["Live", "Replay"],
                    index=0 if get("mode") == "Live" else 1, key="ov_mode")
    set_val("mode", mode)
    st.divider()
    st.markdown('<div class="sidebar-section">🎯 Mission Profile</div>', unsafe_allow_html=True)
    mission_profile = st.selectbox("Profile", [
        "ISR Patrol", "Long-Endurance Transit",
        "High-Altitude Loiter", "Combat Air Patrol",
    ], key="ov_profile")
    st.divider()
    st.markdown('<div class="sidebar-section">⚙️ Fault Injection</div>', unsafe_allow_html=True)
    fault_choice = st.selectbox("Inject Fault", ["None"] + FAULT_TYPES, key="ov_fault")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Inject", key="ov_inject", use_container_width=True):
            if fault_choice != "None":
                engine.inject_fault(fault_choice)
                st.success(f"✓ {fault_choice}")
    with c2:
        if st.button("Clear", key="ov_clear", use_container_width=True):
            engine.clear_fault()
            st.session_state["ov_history"] = []
            st.rerun()
    if st.button("🔄 Reset All", key="ov_reset", use_container_width=True):
        engine.clear_fault()
        st.session_state["ov_history"] = []
        st.rerun()

# ── Header ────────────────────────────────────────────────────────────────────
fault_active = sig.get("fault_detected", False) if sig else False
render_mission_header(
    mode=mode,
    mission_id=mission_profile or "ISR-042",
    has_alerts=fault_active,
)

render_page_title(
    "Overview",
    "Live engine status, health, RUL and key insights at a glance",
)

# ═══════════════════════════════════════════════════════════════════════════════
#  ROW 1 — Hero card  |  Engine Health  |  RUL
# ═══════════════════════════════════════════════════════════════════════════════
col_hero, col_gauge, col_rul = st.columns([2, 1.2, 1.2], gap="medium")

# ── Hero / UAV Identity card ──────────────────────────────────────────────────
with col_hero:
    active_fault_name = engine.active_fault or ""
    fault_label_html = (
        f'<span class="pill pill-red" style="margin-left:8px;">⚠ {active_fault_name.replace("_"," ").upper()}</span>'
        if active_fault_name else ""
    )
    altitude_v = 1200 + (composite * 200)
    airspeed_v = 145  - (composite * 20)
    env_temp_v = 22   + (composite * 8)

    st.markdown(f"""
    <div class="uav-hero-card">
        <div class="scan-line"></div>

        <div style="display:flex; align-items:flex-start; gap:20px;">
            <!-- UAV silhouette -->
            <div style="font-size:5rem; line-height:1; filter: drop-shadow(0 0 20px rgba(59,130,246,0.5));">
                ✈️
            </div>
            <div style="flex:1;">
                <div style="font-size:1.6rem; font-weight:900; color:#f1f5f9;
                            letter-spacing:0.04em; font-family:'JetBrains Mono',monospace;">
                    UAV-07
                </div>
                <div style="margin: 6px 0 10px 0; display:flex; flex-wrap:wrap; gap:6px; align-items:center;">
                    <span class="pill pill-purple">Reconnaissance</span>
                    <span class="pill pill-blue">Endurance</span>
                    <span class="pill pill-green">Reliable</span>
                    <span class="in-mission-pill">● IN MISSION</span>
                    {fault_label_html}
                </div>
                <div style="font-size:0.78rem; color:#4b5e7a; margin-bottom:14px;">
                    DRDO MALE UAV · Piston Aero Engine · SIH26054
                </div>
                <!-- Quick stats -->
                <div style="display:flex; gap:10px; flex-wrap:wrap;">
                    <div class="stat-chip">
                        <div class="stat-chip-val">{altitude_v:.0f}m</div>
                        <div class="stat-chip-label">Altitude</div>
                    </div>
                    <div class="stat-chip">
                        <div class="stat-chip-val">{airspeed_v:.0f}kts</div>
                        <div class="stat-chip-label">Airspeed</div>
                    </div>
                    <div class="stat-chip">
                        <div class="stat-chip-val">{env_temp_v:.0f}°C</div>
                        <div class="stat-chip-label">Env Temp</div>
                    </div>
                    <div class="stat-chip">
                        <div class="stat-chip-val">{composite*100:.1f}%</div>
                        <div class="stat-chip-label">Anomaly</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── Engine Health Gauge ───────────────────────────────────────────────────────
with col_gauge:
    h_color = health_color(health_pct)
    h_label, h_pill = health_pill(health_pct)

    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number",
        value=round(health_pct, 1),
        number=dict(
            suffix="%",
            font=dict(size=32, color=h_color, family="JetBrains Mono, monospace"),
        ),
        gauge=dict(
            axis=dict(
                range=[0, 100],
                tickwidth=1,
                tickcolor="rgba(255,255,255,0.1)",
                tickfont=dict(size=9, color="#64748b"),
            ),
            bar=dict(color=h_color, thickness=0.22),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            steps=[
                dict(range=[0,  45], color="rgba(239,68,68,0.12)"),
                dict(range=[45, 75], color="rgba(245,158,11,0.10)"),
                dict(range=[75,100], color="rgba(16,185,129,0.10)"),
            ],
            threshold=dict(
                line=dict(color="white", width=2),
                thickness=0.7,
                value=health_pct,
            ),
        ),
        title=dict(
            text="ENGINE HEALTH",
            font=dict(size=11, color="#64748b", family="Inter, sans-serif"),
        ),
        domain=dict(x=[0, 1], y=[0, 1]),
    ))

    fig_gauge.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=220,
        margin=dict(l=10, r=10, t=30, b=10),
        font=dict(family="Inter, sans-serif"),
    )

    st.markdown("""
    <div class="dt-card" style="text-align:center; padding: 18px 16px 12px;">
    """, unsafe_allow_html=True)
    st.plotly_chart(fig_gauge, use_container_width=True)
    st.markdown(f"""
        <div style="text-align:center; margin-top:-10px; padding-bottom:8px;">
            <span class="{h_pill}">{h_label}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── RUL Card ──────────────────────────────────────────────────────────────────
with col_rul:
    rul_hours = rul_data.get("rul_hours", 47.2) if rul_data else 47.2
    rul_trend = rul_data.get("trend",     "stable") if rul_data else "stable"
    rul_lo    = rul_data.get("confidence_lower", rul_hours * 0.85) if rul_data else rul_hours * 0.85
    rul_hi    = rul_data.get("confidence_upper", rul_hours * 1.15) if rul_data else rul_hours * 1.15
    baseline  = 280.0
    rul_pct   = min(100.0, (rul_hours / baseline) * 100.0)
    rul_color = health_color(rul_pct)

    trend_icon = {"stable": "→", "degrading": "↓", "improving": "↑"}.get(rul_trend, "→")
    trend_pill_cls = {
        "stable":    "pill pill-blue",
        "degrading": "pill pill-red",
        "improving": "pill pill-green",
    }.get(rul_trend, "pill pill-blue")

    status_text = (
        "Sufficient for planned mission" if rul_hours > 48 else
        "Plan maintenance before next mission" if rul_hours > 12 else
        "Critical — ground immediately"
    )

    st.markdown(f"""
    <div class="dt-card" style="text-align:center; padding: 20px 18px;">
        <div class="card-label">REMAINING USEFUL LIFE</div>
        <div class="hero-metric" style="color:{rul_color}; font-size:2.8rem; margin: 10px 0 4px;">
            {rul_hours:.1f}
        </div>
        <div class="hero-unit">Hours &nbsp;·&nbsp; CI [{rul_lo:.0f} – {rul_hi:.0f}]</div>

        <div style="margin: 14px 0 6px;">
            <div class="progress-bar-outer">
                <div class="progress-bar-inner"
                     style="width:{rul_pct:.1f}%; background:{rul_color};
                            box-shadow: 0 0 8px {rul_color}60;">
                </div>
            </div>
            <div style="display:flex; justify-content:space-between;
                        font-size:0.65rem; color:#4b5e7a; margin-top:4px;">
                <span>0h</span><span>{baseline:.0f}h baseline</span>
            </div>
        </div>

        <div style="margin-top:10px; display:flex; gap:8px; justify-content:center; flex-wrap:wrap;">
            <span class="{trend_pill_cls}">{trend_icon} {rul_trend.title()}</span>
        </div>
        <div style="margin-top:10px; font-size:0.75rem; color:#64748b; line-height:1.4;">
            {status_text}
        </div>
    </div>
    """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  ROW 2 — Key Engine Parameters (6 mini-cards)
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
section_title("⚡ KEY ENGINE PARAMETERS")

PARAM_DISPLAY = [
    ("rpm",                 "RPM",          "RPM",  "#60a5fa"),
    ("egt",                 "EGT",          "°C",   "#f59e0b"),
    ("oil_pressure",        "Oil Pressure", "bar",  "#10b981"),
    ("oil_temp",            "Oil Temp",     "°C",   "#a78bfa"),
    ("vibration_amplitude", "Vibration",    "g",    "#f472b6"),
    ("fuel_flow",           "Fuel Flow",    "L/h",  "#06b6d4"),
]

param_cols = st.columns(6, gap="small")
for i, (ch, label, unit, color) in enumerate(PARAM_DISPLAY):
    val_actual = actual.get(ch, 0.0)
    val_pred   = pred.get(ch, val_actual)
    residual   = val_actual - val_pred
    res_sign   = "+" if residual >= 0 else ""
    res_color  = "#ef4444" if abs(residual) > (val_pred * 0.05) else "#10b981"

    # Build tiny sparkline from history
    spark_vals = [h.get("actual", {}).get(ch, 0.0) for h in history[-20:]]
    if len(spark_vals) < 2:
        spark_vals = [val_actual, val_actual]

    with param_cols[i]:
        st.markdown(f"""
        <div class="param-card" style="border-top: 2px solid {color}40;">
            <div class="param-label">{label}</div>
            <div style="display:flex; align-items:baseline; gap:2px;">
                <div class="param-value" style="color:{color};">{val_actual:.1f}</div>
                <div class="param-unit">{unit}</div>
            </div>
            <div style="font-size:0.65rem; color:{res_color}; margin-top:3px;
                        font-family:'JetBrains Mono',monospace;">
                Δ {res_sign}{residual:.2f}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Tiny sparkline
        fig_spark = go.Figure()
        fig_spark.add_trace(go.Scatter(
            y=spark_vals,
            mode="lines",
            line=dict(color=color, width=1.5),
            fill="tozeroy",
            fillcolor=f"{color}15",
        ))
        fig_spark.update_layout(
            height=50,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            showlegend=False,
        )
        st.plotly_chart(fig_spark, use_container_width=True, config={"displayModeBar": False})

# ═══════════════════════════════════════════════════════════════════════════════
#  ROW 3 — Health Trend chart  |  Active Alerts  |  Mission Status
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
col_trend, col_alerts, col_status = st.columns([2.2, 1.4, 1.4], gap="medium")

# ── Engine Health Trend ───────────────────────────────────────────────────────
with col_trend:
    section_title("📈 ENGINE HEALTH TREND — Last 80 Ticks")

    health_vals = [max(0.0, min(100.0, (1.0 - h.get("composite_score", 0.05)) * 100.0))
                   for h in history]
    tick_labels = list(range(1, len(health_vals) + 1))

    # Color segments
    fig_trend = go.Figure()

    # Shaded zones
    fig_trend.add_hrect(y0=0,  y1=45,  fillcolor="rgba(239,68,68,0.06)",  line_width=0)
    fig_trend.add_hrect(y0=45, y1=75,  fillcolor="rgba(245,158,11,0.05)", line_width=0)
    fig_trend.add_hrect(y0=75, y1=100, fillcolor="rgba(16,185,129,0.05)", line_width=0)

    fig_trend.add_trace(go.Scatter(
        x=tick_labels, y=health_vals,
        mode="lines",
        line=dict(color="#60a5fa", width=2),
        fill="tozeroy",
        fillcolor="rgba(96,165,250,0.08)",
        name="Health %",
        hovertemplate="Tick %{x}<br>Health: %{y:.1f}%<extra></extra>",
    ))

    fig_trend.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(13,18,32,0.6)",
        height=220,
        margin=dict(l=44, r=14, t=14, b=36),
        xaxis=dict(
            showgrid=True, gridcolor="rgba(59,130,246,0.07)",
            tickfont=dict(size=9, color="#64748b"),
            title=dict(text="Tick", font=dict(size=9, color="#64748b")),
        ),
        yaxis=dict(
            range=[0, 105],
            showgrid=True, gridcolor="rgba(59,130,246,0.07)",
            tickfont=dict(size=9, color="#64748b"),
            title=dict(text="Health %", font=dict(size=9, color="#64748b")),
        ),
        showlegend=False,
        font=dict(family="Inter, sans-serif"),
    )

    # Threshold lines
    fig_trend.add_hline(y=75, line_dash="dot",
                        line_color="rgba(16,185,129,0.4)", line_width=1)
    fig_trend.add_hline(y=45, line_dash="dot",
                        line_color="rgba(239,68,68,0.4)",  line_width=1)

    st.plotly_chart(fig_trend, use_container_width=True, config={"displayModeBar": False})

# ── Active Alerts card ────────────────────────────────────────────────────────
with col_alerts:
    section_title("🚨 ACTIVE ALERTS")

    if fault_active and sig:
        dominant = sig.get("dominant_channels", [])
        severity = sig.get("severity", 0.5)
        top_ch   = dominant[0][0].replace("_", " ").title() if dominant else "Unknown"

        st.markdown(f"""
        <div class="dt-card card-red" style="padding:16px;">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:10px;">
                <span style="font-size:1.2rem;">⚠️</span>
                <div>
                    <div style="font-size:0.82rem; font-weight:700; color:#fca5a5;">
                        ANOMALY DETECTED
                    </div>
                    <div style="font-size:0.68rem; color:#64748b; margin-top:2px;">
                        Primary: {top_ch}
                    </div>
                </div>
            </div>
            <div style="margin-bottom:8px;">
                {severity_pill_html(severity)}
                <span style="font-size:0.7rem; color:#94a3b8; margin-left:6px;">
                    Severity {severity*100:.0f}%
                </span>
            </div>
            <div style="font-size:0.72rem; color:#64748b; line-height:1.6;">
        """, unsafe_allow_html=True)

        for ch, mag in (dominant[:3] if dominant else []):
            bar_w = min(100, int(mag * 500))
            st.markdown(f"""
                <div style="margin-bottom:6px;">
                    <div style="display:flex; justify-content:space-between;
                                font-size:0.68rem; color:#94a3b8; margin-bottom:2px;">
                        <span>{ch.replace('_',' ').title()}</span>
                        <span style="font-family:'JetBrains Mono',monospace;">{mag:+.3f}</span>
                    </div>
                    <div style="height:4px; background:rgba(239,68,68,0.15);
                                border-radius:2px; overflow:hidden;">
                        <div style="width:{bar_w}%; height:100%;
                                    background:#ef4444; border-radius:2px;"></div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("</div></div>", unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="clean-banner" style="margin-bottom:0; flex-direction:column;
             align-items:flex-start; gap:6px;">
            <div style="display:flex; gap:8px; align-items:center;">
                <span>✅</span>
                <strong>No Critical Alerts</strong>
            </div>
            <div style="font-size:0.75rem; color:#10b981; opacity:0.8;">
                All systems nominal · Engine performing within expected parameters
            </div>
        </div>
        """, unsafe_allow_html=True)

# ── Mission Status card ───────────────────────────────────────────────────────
with col_status:
    section_title("📋 MISSION STATUS")

    engine_ok  = health_pct >= 75
    rul_ok     = rul_hours > 24
    maint_ok   = not fault_active
    fuel_ok    = actual.get("fuel_flow", 20) > 10

    checks = [
        (engine_ok,  "Engine performance stable"),
        (rul_ok,     f"RUL adequate ({rul_hours:.0f}h remaining)"),
        (maint_ok,   "No maintenance required"),
        (fuel_ok,    "Fuel flow nominal"),
        (True,       f"Profile: {mission_profile}"),
    ]

    st.markdown('<div class="dt-card" style="padding:16px;">', unsafe_allow_html=True)
    for ok, label in checks:
        icon  = "✅" if ok else "⚠️"
        color = "#94a3b8" if ok else "#fca5a5"
        st.markdown(f"""
        <div class="check-row">
            <span class="check-icon">{icon}</span>
            <span style="color:{color}; font-size:0.78rem;">{label}</span>
        </div>
        """, unsafe_allow_html=True)

    # ETA
    ticks_so_far = len(history)
    st.markdown(f"""
    <div style="margin-top:12px; padding-top:10px;
                border-top: 1px solid rgba(255,255,255,0.05);">
        <div style="font-size:0.65rem; color:#4b5e7a; letter-spacing:0.1em;
                    text-transform:uppercase; margin-bottom:4px;">
            Estimated Completion
        </div>
        <div style="font-size:0.88rem; font-weight:700; color:#60a5fa;
                    font-family:'JetBrains Mono',monospace;">
            T+{ticks_so_far * 30 // 60:02d}:{(ticks_so_far * 30) % 60:02d} elapsed
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if mode == "Live":
    _time.sleep(0.1)
    st.rerun()
