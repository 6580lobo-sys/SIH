"""
pages/3_history_view.py — Page 4: Diagnostics
==============================================
UAV Engine Twin · DRDO SIH26054
"Detected fault, evidence, and recommendations"

AI fault detection, evidence bars from dominant_channels,
parameter trend charts, and recommended actions.
"""

import time as _time
import datetime
import streamlit as st
import plotly.graph_objects as go

from utils.styles import (
    inject_global_styles, render_mission_header, render_sidebar_nav,
    render_page_title, section_title, health_color, severity_pill_html,
)
from utils.session import init_session, get, set_val
from utils.connector import get_engine, FAULT_TYPES
from utils.charts import CHANNEL_META
from utils.mock_classification import _LABEL_DISPLAY, FAULT_ICONS, _RECOMMENDATIONS
from utils.mock_data import _CHANNEL_RANGES

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Diagnostics — UAV Engine Twin",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session()
inject_global_styles()

# ── Engine init ───────────────────────────────────────────────────────────────
if "diag_engine" not in st.session_state:
    st.session_state["diag_engine"] = get_engine(mode=get("mode"))

engine = st.session_state["diag_engine"]

N_HIST = 120
if "diag_history" not in st.session_state:
    st.session_state["diag_history"] = []

for _ in range(4):
    tick = engine.next_tick()
    pred, actual = engine.get_raw()
    tick["predicted"] = pred
    tick["actual"]    = actual
    st.session_state["diag_history"].append(tick)

if len(st.session_state["diag_history"]) > N_HIST:
    st.session_state["diag_history"] = st.session_state["diag_history"][-N_HIST:]

history   = st.session_state["diag_history"]
latest    = history[-1] if history else {}
pred      = latest.get("predicted", {})
actual    = latest.get("actual", {})
composite = latest.get("composite_score", 0.05)
sig       = engine.get_signature()
cls_data  = engine.get_classification(sig)

fault_active   = (sig.get("fault_detected", False)  if sig else False)
fault_label    = (cls_data.get("fault_label", "unknown") if cls_data else "unknown")
fault_display  = _LABEL_DISPLAY.get(fault_label, fault_label.replace("_"," ").title())
confidence     = (cls_data.get("confidence",  0.0)   if cls_data else 0.0)
severity       = (sig.get("severity",         0.0)   if sig      else 0.0)
dominant       = (sig.get("dominant_channels", [])   if sig      else [])
fault_id       = (cls_data.get("fault_id",    "—")   if cls_data else "—")
rec_action     = (cls_data.get("recommended_action",
                               _RECOMMENDATIONS.get(fault_label, "")) if cls_data else "")

# Detected timestamp (use now if fault just occurred)
detected_at_ts = _time.time() if fault_active else None
detected_str   = (datetime.datetime.utcfromtimestamp(detected_at_ts).strftime("%Y-%m-%d %H:%M:%S UTC")
                  if detected_at_ts else "—")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    render_sidebar_nav(active="diagnostics")
    st.divider()
    st.markdown('<div class="sidebar-section">⚡ Data Source</div>', unsafe_allow_html=True)
    mode = st.radio("Mode", ["Live", "Replay"],
                    index=0 if get("mode") == "Live" else 1, key="diag_mode")
    set_val("mode", mode)
    st.divider()
    st.markdown('<div class="sidebar-section">🔧 Fault Injection</div>', unsafe_allow_html=True)
    fault_choice = st.selectbox("Inject Fault", ["None"] + FAULT_TYPES, key="diag_fault")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Inject", key="diag_inject", use_container_width=True):
            if fault_choice != "None":
                engine.inject_fault(fault_choice)
                st.success(f"✓ {fault_choice}")
    with c2:
        if st.button("Clear", key="diag_clear", use_container_width=True):
            engine.clear_fault()
            st.session_state["diag_history"] = []
            st.rerun()
    if st.button("🔄 Reset", key="diag_reset", use_container_width=True):
        engine.clear_fault()
        st.session_state["diag_history"] = []
        st.rerun()

# ── Header ────────────────────────────────────────────────────────────────────
render_mission_header(mode=mode, mission_id="ISR-042", has_alerts=fault_active)
render_page_title(
    "Diagnostics",
    "AI fault detection · Evidence analysis · Recommended actions",
)

# ═══════════════════════════════════════════════════════════════════════════════
#  FAULT ALERT BANNER
# ═══════════════════════════════════════════════════════════════════════════════
if fault_active:
    fault_icon = FAULT_ICONS.get(fault_label, "⚠️")
    subsystem_map = {
        "overheating":        "Thermal / Combustion System",
        "oil_pressure_drop":  "Lubrication System",
        "misfire":            "Ignition / Combustion",
        "injector_fault":     "Fuel Delivery System",
        "vibration_anomaly":  "Mechanical / Drivetrain",
        "unknown":            "Unknown Subsystem",
    }
    subsystem = subsystem_map.get(fault_label, "Unknown")

    banner_html = f"""<div class="fault-banner">
    <div style="display:flex; align-items:center; gap:16px;">
        <span style="font-size:2.4rem;">{fault_icon}</span>
        <div>
            <div style="font-size:0.68rem; font-weight:700; letter-spacing:0.14em; color:#f87171; text-transform:uppercase;">
                AI Fault Detection Alert
            </div>
            <div style="font-size:1.4rem; font-weight:800; color:#fef2f2; margin:2px 0;">
                {fault_display}
            </div>
            <div style="font-size:0.75rem; color:#fca5a5; opacity:0.85;">
                Detected at: {detected_str} &nbsp;·&nbsp; Subsystem: <span style="color:#94a3b8;">{subsystem}</span>
            </div>
        </div>
    </div>
    <div class="fault-banner-badges">
        {severity_pill_html(severity)}
        <div style="background:rgba(239,68,68,0.12); border:1px solid rgba(239,68,68,0.3); border-radius:6px; padding:4px 10px; text-align:center;">
            <div style="font-size:0.6rem; color:#64748b; letter-spacing:0.1em; text-transform:uppercase;">Confidence</div>
            <div style="font-size:0.95rem; font-weight:800; color:#fca5a5; font-family:monospace;">{confidence*100:.0f}%</div>
        </div>
    </div>
</div>"""
    st.markdown(textwrap.dedent(banner_html), unsafe_allow_html=True)
else:
    clean_html = """<div class="clean-banner">
    <span style="font-size:1.4rem;">✅</span>
    <div>
        <div style="font-size:0.9rem; font-weight:700; color:#34d399;">No Faults Detected</div>
        <div style="font-size:0.75rem; color:#10b981; opacity:0.75; margin-top:2px;">
            All engine channels within nominal parameters · AI monitoring active
        </div>
    </div>
</div>"""
    st.markdown(textwrap.dedent(clean_html), unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  ROW 1 — Fault Information  |  Key Evidence (Residual Analysis)
# ═══════════════════════════════════════════════════════════════════════════════
col_info, col_evidence = st.columns([1, 1.4], gap="large")

with col_info:
    section_title("📋 FAULT INFORMATION")

    # Estimate onset based on tick count
    onset_ticks = max(0, len(history) - 30)
    onset_time  = (_time.time() - onset_ticks * 0.5) if fault_active else None
    onset_str   = (datetime.datetime.utcfromtimestamp(onset_time).strftime("%H:%M:%S UTC")
                   if onset_time else "—")

    if fault_active:
        subsystem_map2 = {
            "overheating":       "Thermal / Combustion System",
            "oil_pressure_drop": "Lubrication System",
            "misfire":           "Ignition / Combustion",
            "injector_fault":    "Fuel Delivery System",
            "vibration_anomaly": "Mechanical / Drivetrain",
        }
        rows = [
            ("Likely Subsystem",  subsystem_map2.get(fault_label, "Unknown"),   "#93c5fd"),
            ("Fault Type",        fault_display,                                 "#fbbf24"),
            ("Confidence",        f"{confidence*100:.1f}%",                      "#34d399"),
            ("Detected At",       detected_str,                                  "#94a3b8"),
            ("Current Status",    "Active — Monitoring",                         "#f87171"),
            ("Estimated Onset",   onset_str,                                     "#94a3b8"),
        ]
    else:
        rows = [
            ("System Status",  "All Nominal",          "#34d399"),
            ("Last Fault",     "None",                  "#94a3b8"),
            ("Confidence",     "—",                     "#94a3b8"),
            ("Detected At",    "—",                     "#94a3b8"),
            ("Current Status", "Healthy Monitoring",   "#34d399"),
            ("AI Model",       "mock_ensemble_v1",      "#94a3b8"),
        ]

    st.markdown('<div class="dt-card" style="padding:16px 20px;">', unsafe_allow_html=True)
    for label, value, v_color in rows:
        st.markdown(f"""<div style="display:flex; justify-content:space-between; align-items:center; padding:9px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
    <span style="font-size:0.75rem; color:#64748b; font-weight:600;">{label}</span>
    <span style="font-size:0.8rem; font-weight:700; color:{v_color}; font-family:'JetBrains Mono',monospace; text-align:right;">{value}</span>
</div>""", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with col_evidence:
    section_title("📊 KEY EVIDENCE — Residual Analysis (Dominant Channels)")

    st.markdown('<div class="dt-card" style="padding:16px 20px;">', unsafe_allow_html=True)

    if dominant:
        # Sort by magnitude (already sorted by mock_data, but re-sort to be safe)
        sorted_dom = sorted(dominant, key=lambda x: abs(x[1]), reverse=True)
        max_mag    = max(abs(v) for _, v in sorted_dom) if sorted_dom else 1.0

        for i, (ch, mag) in enumerate(sorted_dom[:7]):
            bar_pct   = min(100, int(abs(mag) / max(max_mag, 1e-9) * 100))
            # Choose color by magnitude rank
            if i == 0:
                bar_color = "#ef4444"
            elif i == 1:
                bar_color = "#f59e0b"
            else:
                bar_color = "#3b82f6"

            ch_label = ch.replace("_", " ").title()
            sign     = "+" if mag >= 0 else ""

            # Also show actual residual from latest tick
            lo, hi, unit = _CHANNEL_RANGES.get(ch, (0.0, 1.0, ""))
            rng = max(hi - lo, 1e-6)
            row_html = f"""<div class="evidence-row">
    <div style="display:flex; flex-direction:column; width:160px; flex-shrink:0;">
        <span class="evidence-label">{ch_label}</span>
        <span style="font-size:0.62rem; color:#4b5e7a; font-family:monospace;">norm: {norm_res:+.3f}</span>
    </div>
    <div class="evidence-bar-outer">
        <div class="evidence-bar-inner" style="width:{bar_pct}%; background:{bar_color}; box-shadow: 0 0 6px {bar_color}60;"></div>
    </div>
    <div class="evidence-delta" style="color:{bar_color};">{sign}{actual_res:.3f}</div>
</div>"""
            st.markdown(textwrap.dedent(row_html), unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="text-align:center; padding:24px; color:#4b5e7a; font-size:0.85rem;">
            ✅ No dominant anomaly channels — engine operating normally
        </div>
        """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  ROW 2 — Parameter Trends chart  |  Recommended Actions
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)
col_trend, col_actions = st.columns([1.6, 1], gap="large")

with col_trend:
    section_title("📈 PARAMETER TRENDS — Actual / Expected / Residual")

    # Channel selector
    all_channels = [
        ("Oil Pressure",        "oil_pressure"),
        ("EGT",                 "egt"),
        ("RPM",                 "rpm"),
        ("Cylinder Head Temp",  "cht"),
        ("Oil Temperature",     "oil_temp"),
        ("Vibration",           "vibration_amplitude"),
        ("Fuel Flow",           "fuel_flow"),
    ]

    # Default to most relevant channel based on fault
    fault_default = {
        "oil_pressure_drop":  "Oil Pressure",
        "overheating":        "EGT",
        "misfire":            "RPM",
        "injector_fault":     "Fuel Flow",
        "vibration_anomaly":  "Vibration",
    }
    default_label = fault_default.get(fault_label, "EGT") if fault_active else "EGT"
    default_idx   = next((i for i, (l, _) in enumerate(all_channels) if l == default_label), 0)

    ch_label_sel = st.selectbox(
        "Parameter", [l for l, _ in all_channels],
        index=default_idx, key="diag_ch_sel",
    )
    sel_ch = next(c for l, c in all_channels if l == ch_label_sel)

    pts = min(len(history), 80)
    hist_sl = history[-pts:]

    act_vals  = [h.get("actual",    {}).get(sel_ch, 0.0) for h in hist_sl]
    pred_vals = [h.get("predicted", {}).get(sel_ch, 0.0) for h in hist_sl]
    res_vals  = [a - p for a, p in zip(act_vals, pred_vals)]
    ticks     = list(range(len(act_vals)))

    ch_meta   = CHANNEL_META.get(sel_ch, {"unit": "", "color": "#60a5fa"})
    lo, hi, unit = _CHANNEL_RANGES.get(sel_ch, (0.0, 1.0, ""))
    rng       = max(hi - lo, 1e-6)

    fig_trend = go.Figure()

    # Divergence fill
    fig_trend.add_trace(go.Scatter(
        x=ticks + ticks[::-1],
        y=act_vals + pred_vals[::-1],
        fill="toself",
        fillcolor="rgba(245,158,11,0.07)",
        line=dict(width=0),
        showlegend=False, hoverinfo="skip",
    ))

    fig_trend.add_trace(go.Scatter(
        x=ticks, y=pred_vals,
        mode="lines",
        line=dict(color="#60a5fa", width=1.5, dash="dot"),
        name="Expected",
        hovertemplate=f"Expected: %{{y:.2f}} {unit}<extra></extra>",
    ))

    fig_trend.add_trace(go.Scatter(
        x=ticks, y=act_vals,
        mode="lines",
        line=dict(color=ch_meta.get("color", "#f59e0b"), width=2.5),
        name="Actual",
        hovertemplate=f"Actual: %{{y:.2f}} {unit}<extra></extra>",
    ))

    fig_trend.add_trace(go.Scatter(
        x=ticks, y=res_vals,
        mode="lines",
        line=dict(color="#a78bfa", width=1.5),
        name="Residual",
        yaxis="y2",
        hovertemplate=f"Residual: %{{y:.3f}}<extra></extra>",
    ))

    # Fault onset annotation
    if fault_active and len(ticks) > 20:
        onset_tick = max(0, len(ticks) - 25)
        fig_trend.add_vline(
            x=onset_tick,
            line_color="rgba(239,68,68,0.5)",
            line_width=1.5,
            line_dash="dash",
            annotation_text="⚠ Onset",
            annotation_font_color="#ef4444",
            annotation_font_size=10,
        )

    fig_trend.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(10,14,26,0.6)",
        height=300,
        margin=dict(l=52, r=52, t=14, b=44),
        showlegend=True,
        legend=dict(
            orientation="h", y=-0.2,
            font=dict(size=10, color="#94a3b8"),
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis=dict(
            title=dict(text="Tick (Last 80)", font=dict(size=10, color="#64748b")),
            showgrid=True, gridcolor="rgba(59,130,246,0.07)",
            tickfont=dict(size=9, color="#64748b"), zeroline=False,
        ),
        yaxis=dict(
            title=dict(text=f"{ch_label_sel} ({unit})", font=dict(size=10, color="#64748b")),
            showgrid=True, gridcolor="rgba(59,130,246,0.07)",
            tickfont=dict(size=9, color="#64748b"), zeroline=False,
        ),
        yaxis2=dict(
            title=dict(text="Residual", font=dict(size=10, color="#a78bfa")),
            overlaying="y", side="right",
            showgrid=False,
            tickfont=dict(size=9, color="#a78bfa"),
            zeroline=True, zerolinecolor="rgba(167,139,250,0.2)",
        ),
        font=dict(family="Inter, sans-serif"),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#1a2235", font=dict(size=11, color="#f1f5f9")),
    )

    st.plotly_chart(fig_trend, use_container_width=True, config={"displayModeBar": False})

with col_actions:
    section_title("🔧 RECOMMENDED ACTIONS")

    if fault_active and rec_action:
        # Split recommendation into bullet list
        rec_parts = rec_action.replace(". ", ".\n").split("\n")
        rec_parts = [r.strip() for r in rec_parts if r.strip()]

        # Also add standard items based on fault type
        extra_actions = {
            "oil_pressure_drop": [
                ("⚠️", "URGENT", "Abort mission if oil pressure < 2.5 bar"),
                ("🔍", "CHECK",  "Inspect oil level and pump integrity"),
                ("🛢️", "CHECK",  "Check oil system for leaks or blockage"),
                ("📊", "MONITOR","Review oil pressure trend for next 2 hours"),
                ("📋", "PLAN",   "Schedule oil system service before next mission"),
            ],
            "overheating": [
                ("🌡️", "URGENT", "Reduce throttle to lower thermal load"),
                ("🔍", "CHECK",  "Monitor CHT/EGT — watch for upward trend"),
                ("⏱️", "MONITOR","Track temperature for next 15 minutes"),
                ("📋", "PLAN",   "Schedule inspection within 5 flight-hours"),
            ],
            "misfire": [
                ("⚡", "URGENT", "Inspect spark plugs and ignition leads"),
                ("🔍", "CHECK",  "Check fuel injector spray pattern"),
                ("📊", "MONITOR","Monitor RPM stability and vibration"),
                ("📋", "PLAN",   "Ground inspection recommended"),
            ],
            "injector_fault": [
                ("⛽", "URGENT", "Inspect fuel injector for clog/leak"),
                ("🔍", "CHECK",  "Check fuel pressure at injector rail"),
                ("📊", "MONITOR","Monitor fuel flow rate trend"),
                ("📋", "PLAN",   "Replace injector before next mission"),
            ],
            "vibration_anomaly": [
                ("⚙️", "URGENT", "Check propeller balance and mounting"),
                ("🔍", "CHECK",  "Inspect engine mounts for looseness"),
                ("📊", "MONITOR","Track vibration frequency and amplitude"),
                ("📋", "PLAN",   "Mechanical inspection recommended"),
            ],
        }
        actions = extra_actions.get(fault_label, [
            ("⚠️", "MONITOR", "Monitor closely for next 2 hours"),
            ("📋", "PLAN",    "Plan maintenance before next mission"),
            ("🔍", "CHECK",   "Review related sensor data"),
        ])

        st.markdown('<div class="dt-card" style="padding:16px 20px;">', unsafe_allow_html=True)
        for icon, priority, action_text in actions:
            p_color = "#ef4444" if priority == "URGENT" else "#f59e0b" if priority == "CHECK" else "#3b82f6"
            act_html = f"""<div class="action-row">
    <span class="action-icon">{icon}</span>
    <div>
        <span style="font-size:0.62rem; font-weight:800; color:{p_color}; letter-spacing:0.12em; text-transform:uppercase; margin-right:6px;">{priority}</span>
        <span style="font-size:0.8rem; color:#94a3b8;">{action_text}</span>
    </div>
</div>"""
            st.markdown(textwrap.dedent(act_html), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        no_act_html = """<div class="dt-card" style="padding:16px 20px;">
    <div style="text-align:center; padding:16px; color:#4b5e7a;">
        <div style="font-size:1.5rem; margin-bottom:8px;">✅</div>
        <div style="font-size:0.85rem; font-weight:600; color:#10b981; margin-bottom:6px;">No Actions Required</div>
        <div style="font-size:0.75rem; color:#4b5e7a; line-height:1.6;">
            Engine operating within all nominal parameters. Continue monitoring — next scheduled inspection per maintenance plan.
        </div>
    </div>
</div>"""
        st.markdown(textwrap.dedent(no_act_html), unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  BOTTOM — Generate Report button
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='margin-top:28px; display:flex; justify-content:flex-end;'></div>",
            unsafe_allow_html=True)

_, _, btn_col = st.columns([2, 1, 1])
with btn_col:
    if st.button("📥 Generate Detailed Report →", key="diag_report_btn",
                 type="primary", use_container_width=True):
        try:
            from utils.report import generate_html_report
            rul_data = engine.get_rul(composite)
            report_html = generate_html_report(
                uav_id=get("uav_id") or "UAV-07",
                mission_name=get("mission_name") or "MISSION ISR-042",
                mode=mode,
                tick_history=history,
                rul_history=[rul_data] if rul_data else [],
                classification_history=[cls_data] if cls_data else [],
                alerts=[],
            )
            st.download_button(
                label="📄 Download HTML Report",
                data=report_html,
                file_name=f"uav_report_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.html",
                mime="text/html",
                key="diag_download",
            )
            st.success("✅ Report generated!")
        except Exception as e:
            st.error(f"Report generation failed: {e}")

# ── Fault history mini-log ────────────────────────────────────────────────────
if fault_active:
    st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
    section_title("🗂 FAULT EVENT LOG")

    events = st.session_state.get("diag_event_log", [])
    if not events or events[-1].get("fault_id") != fault_id:
        events.append({
            "fault_id":   fault_id,
            "fault_type": fault_display,
            "severity":   severity,
            "confidence": confidence,
            "detected":   detected_str,
        })
        st.session_state["diag_event_log"] = events[-10:]

    st.markdown('<div class="dt-card" style="padding:14px 20px;">', unsafe_allow_html=True)
    st.markdown("""
    <div style="display:grid; grid-template-columns:auto 1fr 1fr 1fr 1fr;
                gap:10px; padding-bottom:8px; border-bottom:1px solid rgba(255,255,255,0.06);">
        <div style="font-size:0.65rem; color:#4b5e7a; font-weight:700; text-transform:uppercase; letter-spacing:0.1em;">ID</div>
        <div style="font-size:0.65rem; color:#4b5e7a; font-weight:700; text-transform:uppercase; letter-spacing:0.1em;">Type</div>
        <div style="font-size:0.65rem; color:#4b5e7a; font-weight:700; text-transform:uppercase; letter-spacing:0.1em;">Severity</div>
        <div style="font-size:0.65rem; color:#4b5e7a; font-weight:700; text-transform:uppercase; letter-spacing:0.1em;">Confidence</div>
        <div style="font-size:0.65rem; color:#4b5e7a; font-weight:700; text-transform:uppercase; letter-spacing:0.1em;">Detected</div>
    </div>
    """, unsafe_allow_html=True)

    for ev in reversed(events):
        sev_c = "#ef4444" if ev["severity"] > 0.7 else "#f59e0b" if ev["severity"] > 0.4 else "#10b981"
        st.markdown(f"""
        <div style="display:grid; grid-template-columns:auto 1fr 1fr 1fr 1fr;
                    gap:10px; padding:7px 0; border-bottom:1px solid rgba(255,255,255,0.04);
                    font-size:0.75rem;">
            <span style="color:#64748b; font-family:monospace;">{ev['fault_id']}</span>
            <span style="color:#94a3b8;">{ev['fault_type']}</span>
            <span style="color:{sev_c}; font-weight:700;">{ev['severity']*100:.0f}%</span>
            <span style="color:#93c5fd;">{ev['confidence']*100:.0f}%</span>
            <span style="color:#64748b; font-family:monospace; font-size:0.68rem;">{ev['detected']}</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if mode == "Live":
    _time.sleep(0.12)
    st.rerun()
