"""
pages/2_maintenance_view.py — Maintenance View (Technician-facing)
===================================================================
DAY 2 UPDATE: Steps 9–13 complete.

Step 13 ✅ — Auto-generated HTML mission report wired to '📥 Generate Report' button.

CENTERPIECE: Digital Twin Overlay — predicted vs actual with shaded divergence.

Now includes:
  - EGT and RPM hero overlays + any-channel deep-dive
  - Residual bar + explainability bar (from M1 signature + M4 classification)
  - RUL trend chart with confidence band (section 2A) — real §2A payload
  - Maintenance advisory with M4 recommended_action (section 4A)
  - Auto-generated HTML mission report (Step 13)
"""

import time as _time
import streamlit as st

from utils.styles import inject_global_styles, render_header, section_title
from utils.session import init_session, get, set_val
from utils.connector import get_engine, FAULT_TYPES
from utils.charts import (
    build_twin_overlay,
    build_dual_overlay,
    build_centerpiece_twin_overlay,
    build_centerpiece_pair,
    build_residual_bar,
    build_explainability_bar,
    build_history_from_engine,
    build_rul_trend,
    build_rul_card_html,
    build_classification_badge_html,
    build_anomaly_heatmap,
    CHANNEL_META,
)
from utils.report import generate_html_report
from utils.mock_data import generate_mock_alert_log, MockEngine

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Maintenance View — DRDO Digital Twin",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session()
inject_global_styles()

# ── Initialise engine in session (persist across reruns) ─────────────────────
if "maint_engine" not in st.session_state:
    st.session_state["maint_engine"] = get_engine(mode=get("mode"))

engine = st.session_state["maint_engine"]

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
                    index=0 if get("mode") == "Live" else 1, key="maint_mode")
    st.session_state["mode"] = mode

    if mode == "Replay":
        replay_file = st.file_uploader("Upload Mission Log CSV", type=["csv"], key="maint_replay")
        if replay_file:
            st.session_state["replay_file"] = replay_file
            st.success(f"✅ `{replay_file.name}`")

    st.divider()

    # ── Chart controls ────────────────────────────────────────────
    st.markdown('<div class="sidebar-section">📊 Chart Controls</div>', unsafe_allow_html=True)

    n_ticks = st.slider(
        "History window (ticks)",
        min_value=20, max_value=200, value=80, step=10,
        key="maint_n_ticks",
        help="How many ticks of history to display in the overlay chart.",
    )

    deep_channel = st.selectbox(
        "Deep-dive channel",
        list(CHANNEL_META.keys()),
        index=2,  # EGT default
        format_func=lambda c: CHANNEL_META[c]["label"],
        key="maint_deep_channel",
        help="Full-width deep-dive chart below the EGT+RPM pair.",
    )

    show_residual_strip = st.toggle(
        "Show residual strip",
        value=True,
        key="maint_residual_strip",
    )

    st.divider()

    # ── Fault simulation ──────────────────────────────────────────
    st.markdown('<div class="sidebar-section">⚡ Fault Simulation</div>', unsafe_allow_html=True)
    st.caption("Inject a fault to watch the gap open on the chart.")

    fault_at_tick = st.slider(
        "Inject fault at tick",
        min_value=5, max_value=n_ticks - 5, value=30,
        key="maint_fault_at",
    )

    fault_type = st.selectbox(
        "Fault type",
        FAULT_TYPES,
        format_func=lambda f: f.replace("_", " ").title(),
        key="maint_fault_type",
    )

    col_inj, col_clr = st.columns(2)
    with col_inj:
        inject = st.button("💥 Inject", key="maint_inject_btn", use_container_width=True)
    with col_clr:
        clear  = st.button("🔄 Clear",  key="maint_clear_btn",  use_container_width=True)

    if inject:
        st.session_state["maint_fault_at_val"] = fault_at_tick
        st.session_state["maint_fault_type_val"] = fault_type
        st.session_state["maint_engine"] = get_engine(mode=mode)
        engine = st.session_state["maint_engine"]

    if clear:
        st.session_state["maint_fault_at_val"] = None
        st.session_state["maint_engine"] = get_engine(mode=mode)
        engine = st.session_state["maint_engine"]

    st.divider()
    st.markdown('<div class="sidebar-section">\U0001f5c2 Navigation</div>', unsafe_allow_html=True)
    st.page_link("app.py",                     label="\U0001f3e0  Home")
    st.page_link("pages/1_operator_view.py",   label="\U0001f39b  Operator View")
    st.page_link("pages/2_maintenance_view.py",label="\U0001f527  Maintenance View")
    st.page_link("pages/3_history_view.py",    label="\U0001f4c8  History View")

# ── Resolve simulation parameters ─────────────────────────────────────────────
active_fault_at   = st.session_state.get("maint_fault_at_val",   None)
active_fault_type = st.session_state.get("maint_fault_type_val", "overheating")

# ── Run simulation (auto-uses real M1 if twin_core is available) ──────────────
_sim_engine = get_engine(mode=mode)
history, composite_score = build_history_from_engine(
    engine=_sim_engine,
    n_ticks=n_ticks,
    fault_at=active_fault_at,
    fault_type=active_fault_type,
)

# ── RUL history (one estimate per tick for the trend chart) ───────────────────
_rul_engine = get_engine(mode=mode)
rul_history = []
composite_history = []
for _tick_idx in range(1, n_ticks + 1):
    if active_fault_at and _tick_idx == active_fault_at:
        _rul_engine.inject_fault(active_fault_type)
    _tick_data = _rul_engine.next_tick()
    composite_history.append(_tick_data["composite_score"])
    _rul_est = _rul_engine.get_rul(_tick_data["composite_score"])
    if _rul_est:
        rul_history.append(_rul_est)

latest_rul = rul_history[-1] if rul_history else None

# Latest residuals (last tick) — Step 16: guard against empty history
latest_residuals = {}
for ch in history:
    rows = history.get(ch, [])
    latest_residuals[ch] = rows[-1]["residual"] if rows else 0.0

# Step 14: latest signature + classification for the summary panel
_sig_engine = get_engine(mode=mode)
if active_fault_at:
    _sig_engine.inject_fault(active_fault_type)
for _ in range(min(n_ticks, 10)):
    _sig_engine.next_tick()
latest_sig = _sig_engine.get_signature()
latest_cls = _sig_engine.get_classification(latest_sig)

# ═══════════════════════════════════════════════════════════════════════════════
#  HEADER
# ═══════════════════════════════════════════════════════════════════════════════
render_header(get("uav_id"), get("mission_name"), get("mode"))

st.markdown("""
<h1 style="font-size:1.4rem; font-weight:700; color:#f1f5f9; margin-bottom:4px;">
    🔧 Maintenance View
</h1>
<p style="color:#64748b; font-size:0.85rem; margin-bottom:4px;">
    Ground Technician · Deep-dive diagnostics & residual analysis
</p>
""", unsafe_allow_html=True)

# Fault banner
if active_fault_at:
    ft_label = active_fault_type.replace("_", " ").title()
    st.markdown(f"""
    <div style="background:rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.35);
                border-radius:8px; padding:10px 18px; margin-bottom:16px;
                font-size:0.85rem; color:#fca5a5; display:flex; align-items:center; gap:10px;">
        <span style="font-size:1.1rem;">⚠️</span>
        <span>Simulated fault active: <strong>{ft_label}</strong>
        injected at tick {active_fault_at}.
        Composite score: <strong style="color:#ef4444">{composite_score:.3f}</strong></span>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
#  Step 14 — Classification / Signature Summary (technician-facing header panel)
# ═══════════════════════════════════════════════════════════════════════════════
if latest_cls:
    from utils.mock_classification import FAULT_ICONS, _LABEL_DISPLAY  # type: ignore
    _fl  = latest_cls.get("fault_label", "unknown")
    _icon = FAULT_ICONS.get(_fl, "\u2753")
    _conf = latest_cls.get("confidence", 0.0)
    _rec  = latest_cls.get("recommended_action", "")
    _lbl  = _LABEL_DISPLAY.get(_fl, _fl.replace("_"," ").title())
    _top3 = latest_cls.get("top_k_classes", [])[:3]
    _top3_html = " &nbsp;·&nbsp; ".join(
        f'<span style="color:#94a3b8">{t["label"].replace("_"," ").title()}</span> '
        f'<span style="color:#60a5fa;font-weight:700">{t["confidence"]:.0%}</span>'
        for t in _top3
    )
    _conf_clr = "#60a5fa" if _conf >= 0.80 else "#a78bfa" if _conf >= 0.60 else "#94a3b8"
    section_title("\U0001f50d M4 Fault Classification Summary")
    st.markdown(f"""
    <div style="background:rgba(239,68,68,0.06); border:1px solid rgba(239,68,68,0.22);
                border-radius:12px; padding:18px 24px; margin-bottom:16px;
                display:flex; gap:28px; align-items:flex-start; flex-wrap:wrap;">
        <div style="text-align:center; min-width:90px;">
            <div style="font-size:2.4rem;">{_icon}</div>
            <div style="font-size:1rem; font-weight:800; color:#ef4444; margin-top:4px;">{_lbl}</div>
            <div style="font-size:0.72rem; color:{_conf_clr}; font-weight:700;">{_conf:.0%} confidence</div>
        </div>
        <div style="flex:1; min-width:240px;">
            <div style="font-size:0.68rem; color:#64748b; text-transform:uppercase;
                        letter-spacing:0.1em; margin-bottom:6px;">Top-k classes</div>
            <div style="font-size:0.78rem; margin-bottom:12px;">{_top3_html}</div>
            <div style="font-size:0.68rem; color:#64748b; text-transform:uppercase;
                        letter-spacing:0.1em; margin-bottom:6px;">Recommended action</div>
            <div style="font-size:0.82rem; color:#f1f5f9; line-height:1.6;">{_rec}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.divider()
elif active_fault_at:
    section_title("\U0001f50d M4 Fault Classification Summary")
    st.info("Classification pending — run a few more ticks to build the signature.")
    st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
#  CENTERPIECE — What a Digital Twin Is (Hero Section)
# ═══════════════════════════════════════════════════════════════════════════════

section_title("🧬 CENTERPIECE — What Is a Digital Twin?")

# Hero explainer banner
st.markdown("""
<div style="
    background: linear-gradient(135deg, rgba(59,130,246,0.08) 0%, rgba(6,182,212,0.06) 50%, rgba(16,185,129,0.04) 100%);
    border: 1px solid rgba(59,130,246,0.25);
    border-radius: 14px;
    padding: 24px 28px;
    margin-bottom: 24px;
    position: relative;
    overflow: hidden;
">
    <!-- Glow accent bar -->
    <div style="position:absolute; top:0; left:0; right:0; height:2px;
                background: linear-gradient(90deg, #3b82f6, #06b6d4, #10b981);"></div>

    <div style="display:flex; align-items:center; gap:18px; margin-bottom:14px;">
        <div style="font-size:2rem;">🧬</div>
        <div>
            <div style="font-size:1.05rem; font-weight:700; color:#f1f5f9;
                        letter-spacing:0.03em;">
                A Digital Twin is the <span style="color:#06b6d4">gap</span> between
                what the physics model predicts and what the engine actually does.
            </div>
            <div style="font-size:0.78rem; color:#64748b; margin-top:4px;">
                When the gap is small and green → the engine matches the model → healthy.
                When the gap opens and turns red → something is diverging → fault detected.
            </div>
        </div>
    </div>

    <div style="display:flex; gap:28px; padding-top:12px;
                border-top:1px solid rgba(59,130,246,0.12);">
        <div style="display:flex; align-items:center; gap:8px;">
            <div style="width:28px; height:3px; background:#60a5fa; border-radius:2px;"></div>
            <span style="font-size:0.78rem; color:#94a3b8;">
                <strong style="color:#60a5fa">Predicted</strong> — M1's physics twin model
            </span>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
            <div style="width:28px; height:3px; background:#f59e0b; border-radius:2px;"></div>
            <span style="font-size:0.78rem; color:#94a3b8;">
                <strong style="color:#f59e0b">Actual</strong> — Engine sensor reading
            </span>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
            <div style="width:18px; height:14px; border-radius:3px;
                        background:linear-gradient(180deg, rgba(16,185,129,0.25), rgba(16,185,129,0.08));
                        border:1px solid rgba(16,185,129,0.3);"></div>
            <span style="font-size:0.78rem; color:#94a3b8;">
                <strong style="color:#10b981">Shaded gap</strong> — Divergence magnitude
            </span>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
            <span style="font-size:0.78rem; color:#64748b;">
                🟢 Healthy  · 🟡 Caution  · 🔴 Fault
            </span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── EGT Centerpiece (full-width) ──────────────────────────────────────────────
fig_egt, fig_rpm = build_centerpiece_pair(
    history_by_channel=history,
    composite_score=composite_score,
    height=480,
)

st.plotly_chart(fig_egt, use_container_width=True, config={
    "displayModeBar": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
    "displaylogo": False,
})

# ── RPM Centerpiece (full-width) ──────────────────────────────────────────────
st.plotly_chart(fig_rpm, use_container_width=True, config={
    "displayModeBar": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
    "displaylogo": False,
})

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
#  DEEP-DIVE — Full-width channel selector
# ═══════════════════════════════════════════════════════════════════════════════
meta = CHANNEL_META[deep_channel]
section_title(f"🔬 Deep-Dive — {meta['label']} ({meta['unit']})")

fig_deep = build_centerpiece_twin_overlay(
    history=history[deep_channel],
    channel=deep_channel,
    composite_score=composite_score,
    height=440,
    show_residual_strip=show_residual_strip,
)
st.plotly_chart(fig_deep, use_container_width=True, config={
    "displayModeBar": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
    "displaylogo": False,
})

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
#  ROW — Residual Bar  +  Explainability Bar
# ═══════════════════════════════════════════════════════════════════════════════
section_title("📊 Residuals & Sensor Contributions")

res_col, exp_col = st.columns(2, gap="large")

with res_col:
    fig_res = build_residual_bar(latest_residuals, height=280)
    st.plotly_chart(fig_res, use_container_width=True, config={"displayModeBar": False})

with exp_col:
    # Build a mock signature for the explainability chart
    mock_engine_sig = MockEngine(noise_sigma=0.015)
    if active_fault_at:
        mock_engine_sig.inject_fault(active_fault_type)
        mock_engine_sig._fault_age = mock_engine_sig.fault_ramp_ticks
    mock_engine_sig.next_tick()
    sig = mock_engine_sig.get_signature()

    if sig and sig["dominant_channels"]:
        fig_exp = build_explainability_bar(sig["dominant_channels"], height=280)
        st.plotly_chart(fig_exp, use_container_width=True, config={"displayModeBar": False})
    else:
        st.markdown("""
        <div class="metric-card" style="padding:24px; min-height:280px; display:flex;
             align-items:center; justify-content:center; text-align:center;">
            <div>
                <div style="font-size:1.2rem; margin-bottom:8px;">✅</div>
                <div style="font-size:0.85rem; color:#10b981; font-weight:600;">
                    No dominant anomaly channels</div>
                <div style="font-size:0.75rem; color:#64748b; margin-top:6px;">
                    Engine operating within normal parameters</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

st.divider()

# Innovation B — Anomaly Confidence Heatmap
section_title("🔥 Anomaly Confidence Heatmap")

st.markdown("""
<div style="background:rgba(59,130,246,0.05); border:1px solid rgba(59,130,246,0.12);
            border-radius:8px; padding:9px 16px; margin-bottom:12px;
            font-size:0.78rem; color:#94a3b8;">
    <strong style="color:#10b981;">&#9632;</strong> Healthy &nbsp;
    <strong style="color:#f59e0b;">&#9632;</strong> Caution &nbsp;
    <strong style="color:#ef4444;">&#9632;</strong> Fault &nbsp;&middot;&nbsp;
    Hover a cell to see the exact residual magnitude for that sensor at that tick.
    Notice how red cells appear
    <strong style="color:#f1f5f9;">5&ndash;10 ticks before</strong>
    composite_score crosses 0.35 &mdash; the twin catches it early.
</div>
""", unsafe_allow_html=True)

fig_heatmap = build_anomaly_heatmap(history, height=280)
st.plotly_chart(fig_heatmap, use_container_width=True, config={
    "displayModeBar": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
    "displaylogo": False,
})

st.divider()

# Maintenance Advisory + RUL + Report
section_title("🔧 Maintenance Advisory & RUL")

adv_col, rul_col = st.columns([2, 1], gap="large")

with adv_col:
    if active_fault_at:
        ft_label = active_fault_type.replace("_", " ").title()
        recommendations = {
            "overheating":        ["🌡️ Check cooling system & coolant levels",
                                   "🔍 Inspect EGT/CHT sensor calibration",
                                   "⚙️ Reduce throttle demand; inspect intercooler"],
            "oil_pressure_drop":  ["🛢️ Check oil level and pump integrity",
                                   "🔧 Inspect oil filter for blockage",
                                   "🚨 Abort mission if pressure < 2.5 bar"],
            "misfire":            ["🔌 Inspect spark plugs & ignition leads",
                                   "⛽ Check fuel injector spray pattern",
                                   "📊 Review RPM vs EGT correlation trend"],
            "injector_fault":     ["⛽ Inspect fuel injector for clog/leak",
                                   "🔧 Check fuel pressure at injector rail",
                                   "📋 Log fault event for trend analysis"],
            "vibration_spike":    ["🔩 Inspect propeller balance & mounting",
                                   "⚙️ Check engine mounts for looseness",
                                   "📳 Review vibration amplitude history"],
        }
        recs = recommendations.get(active_fault_type, [])
        st.markdown(f"""
        <div style="background:rgba(239,68,68,0.06); border:1px solid rgba(239,68,68,0.25);
                    border-radius:10px; padding:18px 22px;">
            <div style="font-size:0.8rem; color:#ef4444; font-weight:600;
                        letter-spacing:0.08em; text-transform:uppercase; margin-bottom:12px;">
                ⚠️ Fault Detected: {ft_label}
            </div>
            {"".join(f'<div style="font-size:0.85rem; color:#f1f5f9; margin-bottom:8px;">{r}</div>' for r in recs)}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background:rgba(16,185,129,0.06); border:1px solid rgba(16,185,129,0.25);
                    border-radius:10px; padding:18px 22px;">
            <div style="font-size:0.8rem; color:#10b981; font-weight:600;
                        letter-spacing:0.08em; text-transform:uppercase; margin-bottom:10px;">
                ✅ Engine Operating Normally
            </div>
            <div style="font-size:0.85rem; color:#94a3b8; line-height:1.7;">
                No maintenance actions required at this time.<br>
                Continue scheduled inspection per DRDO maintenance schedule.
            </div>
        </div>
        """, unsafe_allow_html=True)

with rul_col:
    # Real RUL from §2A payload
    if latest_rul:
        rul_h   = latest_rul.get("rul_hours", 0)
        rul_lo  = latest_rul.get("confidence_lower", rul_h)
        rul_hi  = latest_rul.get("confidence_upper", rul_h)
        rul_tnd = latest_rul.get("trend", "stable")
        rul_color = "#10b981" if rul_h > 150 else "#f59e0b" if rul_h > 50 else "#ef4444"
        _arrows = {"degrading": ("↓", "#ef4444"), "improving": ("↑", "#10b981"), "stable": ("→", "#f59e0b")}
        arr, arr_clr = _arrows.get(rul_tnd, ("→", "#f59e0b"))
        st.markdown(f"""
        <div class="metric-card" style="padding:24px; text-align:center;">
            <div style="font-size:0.7rem; color:#94a3b8; letter-spacing:0.1em;
                        text-transform:uppercase; margin-bottom:10px;">RUL Estimate</div>
            <div style="display:flex; align-items:baseline; justify-content:center; gap:8px;">
                <span style="font-size:3rem; font-weight:800; color:{rul_color};">{rul_h:.0f}</span>
                <span style="font-size:1.5rem; color:{arr_clr}; font-weight:700;">{arr}</span>
            </div>
            <div style="font-size:0.75rem; color:#64748b; margin-top:4px;">hours remaining</div>
            <div style="margin-top:10px; font-size:0.72rem; color:#475569;
                        border-top:1px solid rgba(59,130,246,0.1); padding-top:8px;">
                {rul_lo:.0f}–{rul_hi:.0f}h (90% CI) · {rul_tnd}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="metric-card" style="padding:24px; text-align:center;">
            <div style="font-size:0.7rem; color:#94a3b8; letter-spacing:0.1em;
                        text-transform:uppercase; margin-bottom:10px;">RUL Estimate</div>
            <div style="font-size:2rem; font-weight:700; color:#64748b;">---</div>
            <div style="font-size:0.75rem; color:#64748b; margin-top:4px;">Awaiting data</div>
        </div>
        """, unsafe_allow_html=True)

st.divider()

# Mission report (Step 13) + Innovation C — Export Mission Log CSV
section_title("📄 Mission Report & Data Export")
rpt_c1, rpt_c2, rpt_c3 = st.columns([2.5, 1, 1])

with rpt_c1:
    st.markdown("""
    <div style="font-size:0.82rem; color:#64748b; padding:8px 0; line-height:1.7;">
        <strong style="color:#f1f5f9;">📥 HTML Report</strong>
        &mdash; self-contained page: health trend spark-line, fault events, RUL, maintenance actions.<br>
        <strong style="color:#f1f5f9;">💾 CSV Log</strong>
        &mdash; per-tick residuals in M1&rsquo;s exact schema.
        <span style="color:#06b6d4;">Upload it back in Replay mode</span>
        to re-analyse this mission from scratch (full round-trip demo).
    </div>""", unsafe_allow_html=True)

with rpt_c2:
    if st.button("📥 Generate Report", key="gen_report_btn"):
        _report_html = generate_html_report(
            uav_id=get("uav_id"),
            mission_name=get("mission_name"),
            mode=mode,
            composite_history=composite_history,
            alert_log=generate_mock_alert_log(
                n_ticks=n_ticks,
                fault_at=active_fault_at,
                fault_type=active_fault_type,
            ),
            final_rul_payload=latest_rul,
            active_fault_type=active_fault_type,
            mission_profile=get("mission_profile"),
            duration_ticks=n_ticks,
            mission_start_time=get("mission_start_time"),
        )
        st.download_button(
            label="⬇ Download .html",
            data=_report_html.encode("utf-8"),
            file_name="mission_report.html",
            mime="text/html",
            key="report_dl_btn",
        )
        st.success("✅ Ready")

# Innovation C: Export per-tick residuals as CSV (M1 schema)
with rpt_c3:
    if st.button("💾 Export CSV Log", key="csv_export_btn"):
        import pandas as _pd
        _channels = [ch for ch in history if history[ch]]
        _n_rows   = max((len(history[ch]) for ch in _channels), default=0)
        _rows = []
        for _i in range(_n_rows):
            _row = {}
            for _ch in _channels:
                if _i < len(history[_ch]):
                    _e = history[_ch][_i]
                    _row.setdefault("tick",            _e["tick"])
                    _row.setdefault("timestamp",       _e["timestamp"])
                    _row[f"residuals.{_ch}"]  = _e["residual"]
                    _row[f"actual.{_ch}"]     = _e["actual"]
                    _row[f"predicted.{_ch}"]  = _e["predicted"]
            _row["composite_score"] = (
                composite_history[_i] if _i < len(composite_history) else None
            )
            _rows.append(_row)
        _csv_bytes = _pd.DataFrame(_rows).to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇ Download .csv",
            data=_csv_bytes,
            file_name="mission_log.csv",
            mime="text/csv",
            key="csv_dl_btn",
        )
        st.success("✅ Ready — upload in Replay!")

