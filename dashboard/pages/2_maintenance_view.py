"""
pages/2_maintenance_view.py — Page 3: Telemetry
================================================
UAV Engine Twin · DRDO SIH26054
"Real-time engine parameters, expected vs actual vs residual"

2×4 grid of twin-overlay parameter charts + residual analysis.
"""

import time as _time
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from utils.styles import (
    inject_global_styles, render_mission_header, render_sidebar_nav,
    render_page_title, section_title, health_color,
)
from utils.session import init_session, get, set_val
from utils.connector import get_engine, FAULT_TYPES
from utils.charts import CHANNEL_META, build_twin_overlay

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Telemetry — UAV Engine Twin",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session()
inject_global_styles()

# ── Engine init ───────────────────────────────────────────────────────────────
if "telem_engine" not in st.session_state:
    st.session_state["telem_engine"] = get_engine(mode=get("mode"))

engine = st.session_state["telem_engine"]

# Collect history
N_HIST = 120
if "telem_history" not in st.session_state:
    st.session_state["telem_history"] = []

for _ in range(4):
    tick = engine.next_tick()
    pred, actual = engine.get_raw()
    tick["predicted"] = pred
    tick["actual"]    = actual
    st.session_state["telem_history"].append(tick)

if len(st.session_state["telem_history"]) > N_HIST:
    st.session_state["telem_history"] = st.session_state["telem_history"][-N_HIST:]

history   = st.session_state["telem_history"]
latest    = history[-1] if history else {}
pred      = latest.get("predicted", {})
actual    = latest.get("actual",    {})
composite = latest.get("composite_score", 0.05)
sig       = engine.get_signature()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    render_sidebar_nav(active="telemetry")
    st.divider()
    st.markdown('<div class="sidebar-section">⚡ Data Source</div>', unsafe_allow_html=True)
    mode = st.radio("Mode", ["Live", "Replay"],
                    index=0 if get("mode") == "Live" else 1, key="telem_mode")
    set_val("mode", mode)
    st.divider()
    st.markdown('<div class="sidebar-section">🔧 Fault Injection</div>', unsafe_allow_html=True)
    fault_choice = st.selectbox("Inject Fault", ["None"] + FAULT_TYPES, key="telem_fault")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Inject", key="telem_inject", use_container_width=True):
            if fault_choice != "None":
                engine.inject_fault(fault_choice)
                st.success(f"✓ {fault_choice}")
    with c2:
        if st.button("Clear", key="telem_clear", use_container_width=True):
            engine.clear_fault()
            st.session_state["telem_history"] = []
            st.rerun()
    if st.button("🔄 Reset", key="telem_reset", use_container_width=True):
        engine.clear_fault()
        st.session_state["telem_history"] = []
        st.rerun()
    st.divider()
    st.markdown('<div class="sidebar-section">📊 Chart Options</div>', unsafe_allow_html=True)
    show_residual = st.checkbox("Show Residual Strip", value=True, key="telem_res")
    n_points = st.slider("Points Shown", 20, N_HIST, 60, key="telem_pts")

# ── Header ────────────────────────────────────────────────────────────────────
fault_active = sig.get("fault_detected", False) if sig else False
render_mission_header(mode=mode, mission_id="ISR-042", has_alerts=fault_active)
render_page_title(
    "Telemetry",
    "Real-time engine parameters · Expected vs Actual vs Residual",
)

# ── Time-range toolbar ────────────────────────────────────────────────────────
time_ranges = ["Live (20 Hz)", "Last 5 min", "Last 1 hour", "Last 6 hours", "Last 24 hours"]
selected_range = st.session_state.get("telem_range", "Live (20 Hz)")

tr_cols = st.columns([1, 1, 1, 1, 1, 2])
for i, tr in enumerate(time_ranges):
    with tr_cols[i]:
        active_cls = "active" if tr == selected_range else ""
        if st.button(tr, key=f"telem_tr_{i}", use_container_width=True):
            st.session_state["telem_range"] = tr
            selected_range = tr

with tr_cols[5]:
    st.button("🔀 Compare", key="telem_compare", use_container_width=True)

st.markdown("<div style='margin-top:6px;'></div>", unsafe_allow_html=True)

# Trim history based on time range
pts_map = {
    "Live (20 Hz)":  n_points,
    "Last 5 min":    min(len(history), 60),
    "Last 1 hour":   min(len(history), 80),
    "Last 6 hours":  min(len(history), 100),
    "Last 24 hours": len(history),
}
pts = pts_map.get(selected_range, n_points)
hist_slice = history[-pts:]

# ═══════════════════════════════════════════════════════════════════════════════
#  PARAMETER CHART GRID — 2 columns × 4 rows
# ═══════════════════════════════════════════════════════════════════════════════

PARAMS = [
    ("rpm",                 "RPM",              "RPM",  "#60a5fa"),
    ("egt",                 "EGT",              "°C",   "#f59e0b"),
    ("cht",                 "Cylinder Head Temp","°C",  "#ef4444"),
    ("oil_pressure",        "Oil Pressure",     "bar",  "#10b981"),
    ("oil_temp",            "Oil Temperature",  "°C",   "#a78bfa"),
    ("vibration_amplitude", "Vibration",        "g",    "#f472b6"),
    ("fuel_flow",           "Fuel Flow",        "L/h",  "#06b6d4"),
    ("vibration_freq",      "Manifold Pressure","Hz",   "#34d399"),
]

section_title("📡 LIVE PARAMETER CHARTS — Actual vs Expected")

for row_i in range(4):
    col_a, col_b = st.columns(2, gap="medium")
    for col_i, col_obj in enumerate([col_a, col_b]):
        param_idx = row_i * 2 + col_i
        ch, label, unit, color = PARAMS[param_idx]

        act_vals  = [h.get("actual",    {}).get(ch, 0.0) for h in hist_slice]
        pred_vals = [h.get("predicted", {}).get(ch, 0.0) for h in hist_slice]
        tick_x    = list(range(len(act_vals)))

        cur_val = act_vals[-1]  if act_vals  else 0.0
        cur_pred = pred_vals[-1] if pred_vals else 0.0
        cur_res  = cur_val - cur_pred
        res_sign = "+" if cur_res >= 0 else ""
        res_color = "#ef4444" if abs(cur_res) > abs(cur_pred) * 0.05 else "#10b981"

        with col_obj:
            st.markdown(f"""
            <div class="dt-card" style="padding:14px 16px; margin-bottom:0;">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;
                            margin-bottom:8px;">
                    <div>
                        <div style="font-size:0.65rem; font-weight:700; letter-spacing:0.14em;
                                    color:#4b5e7a; text-transform:uppercase;">{label}</div>
                        <div style="display:flex; align-items:baseline; gap:3px; margin-top:2px;">
                            <span style="font-size:1.5rem; font-weight:700; color:{color};
                                         font-family:'JetBrains Mono',monospace;">
                                {cur_val:.2f}
                            </span>
                            <span style="font-size:0.72rem; color:#64748b;">{unit}</span>
                        </div>
                    </div>
                    <div style="text-align:right;">
                        <div style="font-size:0.65rem; color:#64748b; margin-bottom:2px;">
                            Expected: <span style="color:#93c5fd;">{cur_pred:.2f}</span>
                        </div>
                        <div style="font-size:0.68rem; font-weight:700; color:{res_color};
                                    font-family:monospace;">
                            Δ {res_sign}{cur_res:.3f}
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Build twin overlay chart
            fig = go.Figure()

            # Shaded divergence gap
            fig.add_trace(go.Scatter(
                x=tick_x + tick_x[::-1],
                y=act_vals + pred_vals[::-1],
                fill="toself",
                fillcolor="rgba(245,158,11,0.06)",
                line=dict(width=0),
                showlegend=False,
                hoverinfo="skip",
            ))

            fig.add_trace(go.Scatter(
                x=tick_x, y=pred_vals,
                mode="lines",
                line=dict(color="#60a5fa", width=1.5, dash="dot"),
                name="Expected",
                hovertemplate=f"Expected: %{{y:.2f}} {unit}<extra></extra>",
            ))

            fig.add_trace(go.Scatter(
                x=tick_x, y=act_vals,
                mode="lines",
                line=dict(color=color, width=2),
                name="Actual",
                hovertemplate=f"Actual: %{{y:.2f}} {unit}<extra></extra>",
            ))

            if show_residual:
                res_vals = [a - p for a, p in zip(act_vals, pred_vals)]
                fig.add_trace(go.Bar(
                    x=tick_x, y=res_vals,
                    name="Residual",
                    marker=dict(
                        color=["#ef4444" if abs(r) > 0.01 else "#10b981" for r in res_vals],
                        opacity=0.45,
                    ),
                    yaxis="y2",
                    showlegend=False,
                    hovertemplate=f"Residual: %{{y:.3f}}<extra></extra>",
                ))

            layout_kwargs = dict(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(10,14,26,0.5)",
                height=180,
                margin=dict(l=40, r=8, t=6, b=28),
                showlegend=True,
                legend=dict(
                    orientation="h", y=1.25,
                    font=dict(size=9, color="#94a3b8"),
                    bgcolor="rgba(0,0,0,0)",
                ),
                xaxis=dict(
                    showgrid=True, gridcolor="rgba(59,130,246,0.07)",
                    tickfont=dict(size=8, color="#64748b"),
                    zeroline=False,
                ),
                yaxis=dict(
                    showgrid=True, gridcolor="rgba(59,130,246,0.07)",
                    tickfont=dict(size=8, color="#64748b"),
                    title=dict(text=unit, font=dict(size=8, color="#64748b")),
                    zeroline=False,
                ),
                font=dict(family="Inter, sans-serif"),
                hovermode="x unified",
                hoverlabel=dict(
                    bgcolor="#1a2235",
                    bordercolor="rgba(59,130,246,0.4)",
                    font=dict(size=10, color="#f1f5f9"),
                ),
            )

            if show_residual:
                layout_kwargs["yaxis2"] = dict(
                    overlaying="y", side="right",
                    showgrid=False,
                    tickfont=dict(size=7, color="#4b5e7a"),
                    zeroline=True,
                    zerolinecolor="rgba(255,255,255,0.1)",
                    title=dict(text="Δ", font=dict(size=8, color="#4b5e7a")),
                )

            fig.update_layout(**layout_kwargs)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# ═══════════════════════════════════════════════════════════════════════════════
#  RESIDUAL ANALYSIS CARD — multi-channel normalized residuals
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)
section_title("🔬 RESIDUAL ANALYSIS — Multi-Channel Normalized Anomaly Signals")

RES_CHANNELS = [
    ("rpm",                 "RPM",          "#60a5fa"),
    ("egt",                 "EGT",          "#f59e0b"),
    ("oil_pressure",        "Oil Pressure", "#10b981"),
    ("vibration_amplitude", "Vibration",    "#f472b6"),
    ("oil_temp",            "Oil Temp",     "#a78bfa"),
    ("fuel_flow",           "Fuel Flow",    "#06b6d4"),
]

from utils.mock_data import _CHANNEL_RANGES

fig_res = go.Figure()

for ch, label, color in RES_CHANNELS:
    lo, hi, _ = _CHANNEL_RANGES.get(ch, (0.0, 1.0, ""))
    rng = max(hi - lo, 1e-6)

    norm_res_vals = []
    for h in hist_slice:
        a = h.get("actual",    {}).get(ch, 0.0)
        p = h.get("predicted", {}).get(ch, a)
        norm_res_vals.append((a - p) / rng)

    fig_res.add_trace(go.Scatter(
        x=list(range(len(norm_res_vals))),
        y=norm_res_vals,
        mode="lines",
        line=dict(color=color, width=1.5),
        name=label,
        hovertemplate=f"{label}: %{{y:.3f}}<extra></extra>",
    ))

fig_res.add_hline(y=0,    line_color="rgba(255,255,255,0.1)", line_width=1)
fig_res.add_hline(y=0.05, line_color="rgba(245,158,11,0.3)", line_width=1, line_dash="dot")
fig_res.add_hline(y=-0.05,line_color="rgba(245,158,11,0.3)", line_width=1, line_dash="dot")

fig_res.update_layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(10,14,26,0.6)",
    height=280,
    margin=dict(l=52, r=14, t=14, b=44),
    showlegend=True,
    legend=dict(
        orientation="h", y=-0.22,
        font=dict(size=10, color="#94a3b8"),
        bgcolor="rgba(0,0,0,0)",
        bordercolor="rgba(59,130,246,0.1)", borderwidth=1,
    ),
    xaxis=dict(
        title=dict(text="Tick", font=dict(size=10, color="#64748b")),
        showgrid=True, gridcolor="rgba(59,130,246,0.07)",
        tickfont=dict(size=9, color="#64748b"),
        zeroline=False,
    ),
    yaxis=dict(
        title=dict(text="Normalized Residual (Δ/range)", font=dict(size=10, color="#64748b")),
        showgrid=True, gridcolor="rgba(59,130,246,0.07)",
        tickfont=dict(size=9, color="#64748b"),
        zeroline=True, zerolinecolor="rgba(255,255,255,0.08)",
    ),
    font=dict(family="Inter, sans-serif"),
    hovermode="x unified",
    hoverlabel=dict(bgcolor="#1a2235", font=dict(size=11, color="#f1f5f9")),
)

st.plotly_chart(fig_res, use_container_width=True, config={"displayModeBar": False})

# Annotation strip
st.markdown("""
<div style="display:flex; gap:16px; flex-wrap:wrap; margin-top:8px; padding:10px 16px;
            background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.04);">
    <div style="font-size:0.7rem; color:#64748b;">
        <span style="color:#f59e0b;">⚠</span>&nbsp; Dashed lines = ±5% threshold
    </div>
    <div style="font-size:0.7rem; color:#64748b;">
        <span style="color:#60a5fa;">ℹ</span>&nbsp; Residual = (Actual − Expected) ÷ channel range
    </div>
    <div style="font-size:0.7rem; color:#64748b;">
        <span style="color:#10b981;">✓</span>&nbsp; Signals near zero = healthy baseline
    </div>
</div>
""", unsafe_allow_html=True)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if mode == "Live":
    _time.sleep(0.12)
    st.rerun()
