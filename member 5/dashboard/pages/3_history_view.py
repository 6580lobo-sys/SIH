"""
pages/3_history_view.py — Historical Trend View
=================================================
Step 15 ✅ — Full mission timeline: composite_score + RUL trend charts,
             fault event Gantt strip, and key summary statistics.

Approach: fresh simulation per page load (same stateless pattern as pages 1 & 2).
The "story" of engine degradation is shown by running n_ticks and plotting
per-tick composite_score and RUL across the full timeline.
"""

import streamlit as st

from utils.styles import inject_global_styles, render_header, section_title
from utils.session import init_session, get
from utils.connector import get_engine, FAULT_TYPES
from utils.charts import (
    build_composite_trend,
    build_rul_trend_slim,
    CHANNEL_META,
)

import plotly.graph_objects as go

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="History View — DRDO Digital Twin",
    page_icon="📈",
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
                    index=0 if get("mode") == "Live" else 1, key="hist_mode")
    st.session_state["mode"] = mode

    st.divider()

    st.markdown('<div class="sidebar-section">📊 Mission Timeline</div>', unsafe_allow_html=True)
    n_ticks = st.slider(
        "Mission length (ticks)",
        min_value=40, max_value=300, value=120, step=10,
        key="hist_n_ticks",
        help="Total number of ticks to simulate for the full mission timeline.",
    )

    st.divider()

    st.markdown('<div class="sidebar-section">⚡ Fault Simulation</div>', unsafe_allow_html=True)
    st.caption("Inject a fault to see how the engine degrades over time.")

    fault_at = st.slider(
        "Inject fault at tick",
        min_value=5, max_value=n_ticks - 5, value=n_ticks // 3,
        key="hist_fault_at",
    )
    fault_type = st.selectbox(
        "Fault type", FAULT_TYPES,
        format_func=lambda f: f.replace("_", " ").title(),
        key="hist_fault_type",
    )

    col_inj, col_clr = st.columns(2)
    with col_inj:
        inject = st.button("💥 Inject", key="hist_inject_btn", use_container_width=True)
    with col_clr:
        clear  = st.button("🔄 Clear",  key="hist_clear_btn",  use_container_width=True)

    if inject:
        st.session_state["hist_fault_at_val"]   = fault_at
        st.session_state["hist_fault_type_val"] = fault_type
    if clear:
        st.session_state["hist_fault_at_val"]   = None
        st.session_state["hist_fault_type_val"] = "overheating"

    st.divider()
    st.markdown('<div class="sidebar-section">🗂 Navigation</div>', unsafe_allow_html=True)
    st.page_link("app.py",                     label="🏠  Home")
    st.page_link("pages/1_operator_view.py",   label="🎛  Operator View")
    st.page_link("pages/2_maintenance_view.py",label="🔧  Maintenance View")
    st.page_link("pages/3_history_view.py",    label="📈  History View")

# ── Resolve params ────────────────────────────────────────────────────────────
active_fault_at   = st.session_state.get("hist_fault_at_val",   None)
active_fault_type = st.session_state.get("hist_fault_type_val", "overheating")

# ── Run full-mission simulation ───────────────────────────────────────────────
_engine     = get_engine(mode=mode)
_rul_engine = get_engine(mode=mode)

composite_records: list[dict] = []
rul_records:       list[dict] = []
fault_ticks:       list[int]  = []

for _t in range(1, n_ticks + 1):
    _fault_active = active_fault_at and _t >= active_fault_at

    if active_fault_at and _t == active_fault_at:
        _engine.inject_fault(active_fault_type)
        _rul_engine.inject_fault(active_fault_type)

    _tick  = _engine.next_tick()
    _cs    = _tick["composite_score"]
    _hp    = max(0.0, min(100.0, 100.0 - _cs * 100.0))

    # Signature for fault detection
    _sig   = _engine.get_signature()
    _fd    = (_sig.get("fault_detected", False) if _sig else False) or bool(_fault_active)

    composite_records.append({
        "tick":            _t,
        "composite_score": _cs,
        "health_pct":      _hp,
        "fault_active":    _fd,
    })

    if _fd:
        fault_ticks.append(_t)

    # RUL tick (separate engine)
    _rul_tick = _rul_engine.next_tick()
    _rul_est  = _rul_engine.get_rul(_rul_tick["composite_score"])
    if _rul_est:
        rul_records.append({
            "tick":             _t,
            "rul_hours":        _rul_est["rul_hours"],
            "confidence_lower": _rul_est["confidence_lower"],
            "confidence_upper": _rul_est["confidence_upper"],
            "trend":            _rul_est["trend"],
        })

# ── Key statistics ────────────────────────────────────────────────────────────
_all_scores  = [r["composite_score"] for r in composite_records]
_mean_health = sum(r["health_pct"] for r in composite_records) / len(composite_records) if composite_records else 100.0
_peak_score  = max(_all_scores) if _all_scores else 0.0
_final_score = _all_scores[-1] if _all_scores else 0.0
_final_health= composite_records[-1]["health_pct"] if composite_records else 100.0
_fault_tick_count = len(fault_ticks)
_final_rul = rul_records[-1]["rul_hours"] if rul_records else None

_health_color = "#10b981" if _final_health >= 70 else "#f59e0b" if _final_health >= 40 else "#ef4444"
_peak_color   = "#10b981" if _peak_score < 0.10 else "#f59e0b" if _peak_score < 0.35 else "#ef4444"
_rul_color    = "#10b981" if (_final_rul or 0) > 150 else "#f59e0b" if (_final_rul or 0) > 50 else "#ef4444"

# ═══════════════════════════════════════════════════════════════════════════════
#  HEADER
# ═══════════════════════════════════════════════════════════════════════════════
render_header(get("uav_id"), get("mission_name"), get("mode"))

st.markdown("""
<h1 style="font-size:1.4rem; font-weight:700; color:#f1f5f9; margin-bottom:4px;">
    📈 History View
</h1>
<p style="color:#64748b; font-size:0.85rem; margin-bottom:4px;">
    Mission Timeline · Full composite_score + RUL story across all ticks
</p>
""", unsafe_allow_html=True)

# Fault injection banner
if active_fault_at:
    ft_label = active_fault_type.replace("_", " ").title()
    st.markdown(f"""
    <div style="background:rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.35);
                border-radius:8px; padding:10px 18px; margin-bottom:12px;
                font-size:0.85rem; color:#fca5a5; display:flex; align-items:center; gap:10px;">
        <span>⚠️</span>
        <span>Fault <strong>{ft_label}</strong> injected at tick {active_fault_at} —
        watch the composite_score spike and RUL drop below.</span>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
#  ROW 1 — Key Statistics
# ═══════════════════════════════════════════════════════════════════════════════
section_title("📋 Mission Summary Statistics")

_stat_cols = st.columns(5, gap="medium")
_stats = [
    ("Total Ticks",     str(n_ticks),                 "#60a5fa"),
    ("Final Health",    f"{_final_health:.0f}%",       _health_color),
    ("Peak Score",      f"{_peak_score:.3f}",          _peak_color),
    ("Fault Ticks",     str(_fault_tick_count),
     "#ef4444" if _fault_tick_count else "#10b981"),
    ("Final RUL",       f"{_final_rul:.0f}h" if _final_rul is not None else "—", _rul_color),
]
for col, (label, val, color) in zip(_stat_cols, _stats):
    with col:
        st.markdown(f"""
        <div class="metric-card" style="padding:16px; text-align:center;">
            <div style="font-size:0.62rem; color:#64748b; letter-spacing:0.08em;
                        text-transform:uppercase; margin-bottom:6px;">{label}</div>
            <div style="font-size:1.8rem; font-weight:800; color:{color};">{val}</div>
        </div>
        """, unsafe_allow_html=True)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
#  ROW 2 — Composite Score Trend (full mission)
# ═══════════════════════════════════════════════════════════════════════════════
section_title("📉 Composite Score — Full Mission Timeline")

st.markdown("""
<div style="background:rgba(59,130,246,0.05); border:1px solid rgba(59,130,246,0.12);
            border-radius:8px; padding:9px 16px; margin-bottom:12px; font-size:0.78rem; color:#94a3b8;">
    <span style="color:#10b981">■</span> Healthy (&lt;0.10) &nbsp;
    <span style="color:#f59e0b">■</span> Caution (0.10–0.35) &nbsp;
    <span style="color:#ef4444">■</span> Fault (&gt;0.35) &nbsp; · &nbsp;
    Dashed red line = fault injection point. Dotted lines = severity thresholds.
</div>
""", unsafe_allow_html=True)

# Step 16: guard empty records
if composite_records:
    fig_trend = build_composite_trend(
        records=composite_records,
        fault_at=active_fault_at,
        height=300,
    )
    st.plotly_chart(fig_trend, use_container_width=True, config={"displayModeBar": True,
        "modeBarButtonsToRemove": ["lasso2d", "select2d"], "displaylogo": False})
else:
    st.markdown("""
    <div style="background:rgba(59,130,246,0.06); border:1px solid rgba(59,130,246,0.2);
                border-radius:10px; padding:32px; text-align:center;">
        <div style="font-size:1.5rem; margin-bottom:8px;">⏳</div>
        <div style="color:#60a5fa; font-weight:600;">No timeline data yet</div>
        <div style="color:#475569; font-size:0.8rem; margin-top:6px;">
            Adjust the mission length slider and the data will appear here.
        </div>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
#  ROW 3 — RUL Trend (full mission) + Fault Event Timeline
# ═══════════════════════════════════════════════════════════════════════════════
section_title("🔋 RUL & Fault Event Timeline")

rul_col, gantt_col = st.columns([2, 1], gap="large")

with rul_col:
    st.markdown("""
    <div style="font-size:0.75rem; color:#64748b; margin-bottom:8px;">
        RUL (hours) over mission with 90% confidence band. Drops sharply when a fault occurs.
    </div>
    """, unsafe_allow_html=True)
    if rul_records:
        fig_rul = build_rul_trend_slim(
            records=rul_records,
            fault_at=active_fault_at,
            height=260,
        )
        st.plotly_chart(fig_rul, use_container_width=True,
                        config={"displayModeBar": False})
    else:
        st.caption("RUL data unavailable.")

with gantt_col:
    # ── Fault Event Timeline: Gantt-style strip ───────────────────────────────
    st.markdown("""
    <div style="font-size:0.75rem; color:#64748b; margin-bottom:8px;">
        Ticks where <code>fault_detected=True</code> (red), healthy ticks (green).
    </div>
    """, unsafe_allow_html=True)

    if composite_records:
        _ticks_all    = [r["tick"]         for r in composite_records]
        _fault_active = [r["fault_active"] for r in composite_records]

        # Build a Gantt-style 1-row heatmap
        _bar_colors = ["rgba(239,68,68,0.7)" if fa else "rgba(16,185,129,0.3)"
                       for fa in _fault_active]

        fig_gantt = go.Figure()
        # One bar per tick — width 1, height 1
        for t, fa in zip(_ticks_all, _fault_active):
            fig_gantt.add_trace(go.Bar(
                x=[t], y=[1],
                marker_color="rgba(239,68,68,0.7)" if fa else "rgba(16,185,129,0.3)",
                marker_line_width=0,
                showlegend=False,
                hovertemplate=f"Tick {t}<br>{'🔴 FAULT' if fa else '🟢 Healthy'}<extra></extra>",
            ))

        fig_gantt.update_layout(
            paper_bgcolor="#0a0e1a",
            plot_bgcolor="#0d1424",
            height=260,
            margin=dict(l=20, r=10, t=36, b=36),
            font=dict(family="Inter, sans-serif", color="#94a3b8", size=10),
            barmode="stack",
            bargap=0.0,
            bargroupgap=0.0,
            xaxis=dict(title="Tick", showgrid=False, zeroline=False,
                       tickfont=dict(size=9)),
            yaxis=dict(visible=False, range=[0, 1]),
            title=dict(text="<b>Fault Event Strip</b>",
                       font=dict(size=12, color="#f1f5f9"), x=0.01),
        )

        # Fault injection marker
        if active_fault_at:
            fig_gantt.add_vline(
                x=active_fault_at,
                line=dict(color="#ef4444", width=2, dash="dash"),
            )

        st.plotly_chart(fig_gantt, use_container_width=True,
                        config={"displayModeBar": False})

        # Summary pills
        _healthy_n = sum(1 for fa in _fault_active if not fa)
        _fault_n   = sum(1 for fa in _fault_active if fa)
        st.markdown(f"""
        <div style="display:flex; gap:12px; margin-top:8px; flex-wrap:wrap;">
            <span style="background:rgba(16,185,129,0.12); border:1px solid rgba(16,185,129,0.3);
                         color:#10b981; font-size:0.72rem; font-weight:700; padding:3px 12px;
                         border-radius:10px;">🟢 {_healthy_n} healthy ticks</span>
            <span style="background:rgba(239,68,68,0.12); border:1px solid rgba(239,68,68,0.3);
                         color:#ef4444; font-size:0.72rem; font-weight:700; padding:3px 12px;
                         border-radius:10px;">🔴 {_fault_n} fault ticks</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.caption("No timeline data.")

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
#  ROW 4 — Health % over time (second line chart, dual axis)
# ═══════════════════════════════════════════════════════════════════════════════
section_title("❤️ Engine Health % Over Mission")

if composite_records:
    _ticks  = [r["tick"]       for r in composite_records]
    _health = [r["health_pct"] for r in composite_records]
    _mean_h = _mean_health

    fig_health = go.Figure()

    # Colour segments: green ≥70, amber 40-69, red <40
    _seg_colors = []
    for h in _health:
        if h >= 70:
            _seg_colors.append("#10b981")
        elif h >= 40:
            _seg_colors.append("#f59e0b")
        else:
            _seg_colors.append("#ef4444")

    # Fill zones
    fig_health.add_hrect(y0=70, y1=100, fillcolor="rgba(16,185,129,0.05)", line_width=0)
    fig_health.add_hrect(y0=40, y1=70,  fillcolor="rgba(245,158,11,0.05)", line_width=0)
    fig_health.add_hrect(y0=0,  y1=40,  fillcolor="rgba(239,68,68,0.05)",  line_width=0)

    # Mean health line
    fig_health.add_hline(
        y=_mean_h,
        line=dict(color="rgba(148,163,184,0.4)", width=1, dash="dot"),
        annotation_text=f"Mean {_mean_h:.0f}%",
        annotation_position="right",
        annotation=dict(font=dict(size=9, color="#64748b")),
    )

    fig_health.add_trace(go.Scatter(
        x=_ticks, y=_health,
        mode="lines",
        line=dict(color="#a78bfa", width=2),
        fill="tozeroy",
        fillcolor="rgba(167,139,250,0.06)",
        hovertemplate="Tick %{x}<br>Health: %{y:.1f}%<extra></extra>",
        name="Health %",
    ))

    if active_fault_at:
        fig_health.add_vline(
            x=active_fault_at,
            line=dict(color="#ef4444", width=1.5, dash="dash"),
        )

    fig_health.update_layout(
        paper_bgcolor="#0a0e1a",
        plot_bgcolor="#0d1424",
        height=240,
        margin=dict(l=56, r=20, t=36, b=36),
        font=dict(family="Inter, sans-serif", color="#94a3b8", size=11),
        showlegend=False,
        xaxis=dict(title="Tick", showgrid=True,
                   gridcolor="rgba(59,130,246,0.08)", zeroline=False),
        yaxis=dict(title="Health %", range=[0, 105], showgrid=True,
                   gridcolor="rgba(59,130,246,0.08)", zeroline=False),
        title=dict(text="<b>Engine Health %</b>  (100 − composite_score×100)",
                   font=dict(size=13, color="#f1f5f9"), x=0.01),
        hoverlabel=dict(bgcolor="#1a2235", bordercolor="rgba(59,130,246,0.4)",
                        font=dict(family="Inter, sans-serif", size=12, color="#f1f5f9")),
    )

    st.plotly_chart(fig_health, use_container_width=True,
                    config={"displayModeBar": True,
                            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                            "displaylogo": False})
else:
    st.caption("No health data.")
