"""
utils/charts.py
===============
Plotly chart builders for the Digital Twin Dashboard.

All charts use the shared dark design palette and return `go.Figure` objects
ready to pass to `st.plotly_chart(fig, use_container_width=True)`.

Key export:
    build_twin_overlay(history, channel, composite_score)
        → The centerpiece chart: predicted vs actual with shaded divergence gap.
"""

import math
from typing import Optional
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ── Shared palette (mirrors styles.py) ───────────────────────────────────────
_BG          = "#0d1424"
_BG_PAPER    = "#0a0e1a"
_GRID        = "rgba(59,130,246,0.08)"
_PREDICTED   = "#60a5fa"   # cool blue  — M1's model says this
_ACTUAL      = "#f59e0b"   # warm amber — what the engine actually does
_TEXT        = "#94a3b8"
_TEXT_TITLE  = "#f1f5f9"
_FONT        = "Inter, sans-serif"

# Fill colours for the divergence shading, keyed by severity band
_FILL_HEALTHY  = "rgba(16,185,129,0.12)"    # green   composite < 0.10
_FILL_CAUTION  = "rgba(245,158,11,0.15)"    # amber   0.10 – 0.35
_FILL_FAULT    = "rgba(239,68,68,0.18)"     # red     > 0.35

# Per-channel display metadata
CHANNEL_META = {
    "rpm":                 {"label": "RPM",                  "unit": "RPM",    "color": "#60a5fa"},
    "cht":                 {"label": "CHT",                  "unit": "°C",     "color": "#ef4444"},
    "egt":                 {"label": "EGT",                  "unit": "°C",     "color": "#f59e0b"},
    "oil_pressure":        {"label": "Oil Pressure",          "unit": "bar",    "color": "#10b981"},
    "oil_temp":            {"label": "Oil Temperature",       "unit": "°C",     "color": "#a78bfa"},
    "fuel_flow":           {"label": "Fuel Flow",             "unit": "L/h",    "color": "#06b6d4"},
    "vibration_amplitude": {"label": "Vibration Amplitude",   "unit": "g",      "color": "#f472b6"},
    "vibration_freq":      {"label": "Vibration Frequency",   "unit": "Hz",     "color": "#34d399"},
}

# ── Base Plotly layout shared by all charts ───────────────────────────────────
def _base_layout(**overrides) -> dict:
    base = dict(
        font=dict(family=_FONT, color=_TEXT, size=12),
        paper_bgcolor=_BG_PAPER,
        plot_bgcolor=_BG,
        margin=dict(l=56, r=20, t=52, b=44),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right",  x=1,
            bgcolor="rgba(0,0,0,0)",
            bordercolor="rgba(59,130,246,0.2)",
            borderwidth=1,
            font=dict(size=11),
        ),
        xaxis=dict(
            showgrid=True, gridcolor=_GRID, gridwidth=1,
            zeroline=False,
            tickfont=dict(size=10, color=_TEXT),
            title_font=dict(size=11, color=_TEXT),
        ),
        yaxis=dict(
            showgrid=True, gridcolor=_GRID, gridwidth=1,
            zeroline=False,
            tickfont=dict(size=10, color=_TEXT),
            title_font=dict(size=11, color=_TEXT),
        ),
        hoverlabel=dict(
            bgcolor="#1a2235",
            bordercolor="rgba(59,130,246,0.4)",
            font=dict(family=_FONT, size=12, color="#f1f5f9"),
        ),
    )
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────────────
#  TWIN OVERLAY CHART  (THE CENTERPIECE)
# ─────────────────────────────────────────────────────────────────────────────

def build_twin_overlay(
    history: list[dict],
    channel: str,
    composite_score: float = 0.0,
    height: int = 380,
    show_residual_strip: bool = True,
) -> go.Figure:
    """
    THE CENTERPIECE CHART — Predicted vs Actual with shaded divergence gap.

    Args:
        history:         List of dicts, each containing:
                            {"tick": int, "predicted": float, "actual": float,
                             "timestamp": float}
                         Use build_history_from_engine() to generate this.
        channel:         One of CHANNEL_META keys, e.g. "egt", "rpm".
        composite_score: Latest composite_score (0–1+) from M1.
                         Controls the fill colour (green / amber / red).
        height:          Chart height in pixels.
        show_residual_strip: If True, adds a small residual subplot below.

    Returns:
        go.Figure ready for st.plotly_chart()
    """
    meta = CHANNEL_META.get(channel, {"label": channel, "unit": "", "color": _PREDICTED})

    ticks      = [d["tick"]      for d in history]
    predicted  = [d["predicted"] for d in history]
    actual     = [d["actual"]    for d in history]
    residuals  = [a - p for a, p in zip(actual, predicted)]

    # Fill colour by severity
    if composite_score < 0.10:
        fill_color  = _FILL_HEALTHY
        band_label  = "Healthy"
        band_color  = "#10b981"
    elif composite_score < 0.35:
        fill_color  = _FILL_CAUTION
        band_label  = "Caution"
        band_color  = "#f59e0b"
    else:
        fill_color  = _FILL_FAULT
        band_label  = "FAULT"
        band_color  = "#ef4444"

    rows = 2 if show_residual_strip else 1
    row_heights = [0.72, 0.28] if show_residual_strip else [1.0]

    fig = make_subplots(
        rows=rows, cols=1,
        shared_xaxes=True,
        row_heights=row_heights,
        vertical_spacing=0.06,
        subplot_titles=["", "Residual (Actual − Predicted)" if show_residual_strip else ""],
    )

    # ── Trace 1: Predicted (solid blue line) ─────────────────────────────────
    fig.add_trace(go.Scatter(
        x=ticks, y=predicted,
        mode="lines",
        name="Predicted (M1 Twin)",
        line=dict(color=_PREDICTED, width=2.5, dash="solid"),
        hovertemplate=(
            f"<b>Predicted {meta['label']}</b><br>"
            f"Tick: %{{x}}<br>"
            f"Value: %{{y:.2f}} {meta['unit']}"
            "<extra></extra>"
        ),
    ), row=1, col=1)

    # ── Trace 2: Invisible predicted (anchor for fill) ────────────────────────
    # We need to fill *between* two traces — first lay down a transparent
    # duplicate of predicted that actual will fill towards.
    fig.add_trace(go.Scatter(
        x=ticks, y=predicted,
        mode="lines",
        line=dict(color="rgba(0,0,0,0)", width=0),
        showlegend=False,
        hoverinfo="skip",
    ), row=1, col=1)

    # ── Trace 3: Actual (amber line) + fill to predicted ─────────────────────
    fig.add_trace(go.Scatter(
        x=ticks, y=actual,
        mode="lines",
        name="Actual (Engine)",
        line=dict(color=_ACTUAL, width=2.5),
        fill="tonexty",
        fillcolor=fill_color,
        hovertemplate=(
            f"<b>Actual {meta['label']}</b><br>"
            f"Tick: %{{x}}<br>"
            f"Value: %{{y:.2f}} {meta['unit']}"
            "<extra></extra>"
        ),
    ), row=1, col=1)

    # ── Residual strip (bottom subplot) ──────────────────────────────────────
    if show_residual_strip:
        res_colors = [
            "#ef4444" if abs(r) > 0.6 * max(abs(v) for v in residuals or [1])
            else "#f59e0b" if abs(r) > 0.3 * max(abs(v) for v in residuals or [1])
            else "#10b981"
            for r in residuals
        ]

        fig.add_trace(go.Bar(
            x=ticks, y=residuals,
            name="Residual",
            marker=dict(
                color=res_colors,
                opacity=0.75,
                line=dict(width=0),
            ),
            hovertemplate=(
                f"<b>Residual</b><br>"
                f"Tick: %{{x}}<br>"
                f"Value: %{{y:.3f}} {meta['unit']}"
                "<extra></extra>"
            ),
        ), row=2, col=1)

        # Zero line on residual strip
        fig.add_hline(
            y=0,
            line=dict(color="rgba(148,163,184,0.3)", width=1, dash="dot"),
            row=2, col=1,
        )

        fig.update_yaxes(
            title_text=f"Residual ({meta['unit']})",
            row=2, col=1,
            showgrid=True, gridcolor=_GRID,
            zeroline=False,
            tickfont=dict(size=9),
        )

    # ── Fault event markers (vertical lines at high-residual ticks) ───────────
    if residuals:
        max_abs_res = max(abs(r) for r in residuals) or 1.0
        threshold   = max_abs_res * 0.65
        for i, (tick, res) in enumerate(zip(ticks, residuals)):
            if abs(res) >= threshold and i > 3:
                fig.add_vline(
                    x=tick,
                    line=dict(color="rgba(239,68,68,0.4)", width=1.5, dash="dot"),
                    row=1, col=1,
                )

    # ── Annotations ───────────────────────────────────────────────────────────
    # Status badge top-right
    fig.add_annotation(
        text=f"● {band_label}",
        xref="paper", yref="paper",
        x=0.99, y=0.97,
        xanchor="right", yanchor="top",
        font=dict(color=band_color, size=12, family=_FONT),
        showarrow=False,
        bgcolor="rgba(0,0,0,0.3)",
        borderpad=4,
    )

    # Composite score badge
    fig.add_annotation(
        text=f"Score: {composite_score:.3f}",
        xref="paper", yref="paper",
        x=0.99, y=0.88,
        xanchor="right", yanchor="top",
        font=dict(color=_TEXT, size=10, family=_FONT),
        showarrow=False,
    )

    # ── Layout ────────────────────────────────────────────────────────────────
    title_html = (
        f"<b style='color:{_TEXT_TITLE}'>{meta['label']} — Digital Twin Overlay</b>"
        f"  <span style='font-size:12px; color:{_TEXT}'>Predicted vs Actual · "
        f"Gap = Divergence from Physics Model</span>"
    )

    layout_cfg = _base_layout(
        title=dict(
            text=title_html,
            x=0.01, xanchor="left",
            font=dict(size=14, family=_FONT, color=_TEXT_TITLE),
        ),
        height=height,
    )
    layout_cfg["xaxis"]["title"] = "Tick"
    layout_cfg["yaxis"]["title"] = f"{meta['label']} ({meta['unit']})"

    fig.update_layout(**layout_cfg)

    # Subplot title styling
    for ann in fig.layout.annotations:
        ann.font = dict(size=10, color=_TEXT, family=_FONT)

    return fig


# ─────────────────────────────────────────────────────────────────────────────
#  CENTERPIECE TWIN OVERLAY  (Hero visual — "What a Digital Twin is")
# ─────────────────────────────────────────────────────────────────────────────

# Gradient fill palettes for the centerpiece divergence shading
_GRAD_HEALTHY = [
    "rgba(16,185,129,0.04)",   # bottom of gap
    "rgba(16,185,129,0.10)",   # mid
    "rgba(16,185,129,0.18)",   # peak opacity
]
_GRAD_CAUTION = [
    "rgba(245,158,11,0.05)",
    "rgba(245,158,11,0.12)",
    "rgba(245,158,11,0.22)",
]
_GRAD_FAULT = [
    "rgba(239,68,68,0.06)",
    "rgba(239,68,68,0.15)",
    "rgba(239,68,68,0.28)",
]


def build_centerpiece_twin_overlay(
    history: list[dict],
    channel: str,
    composite_score: float = 0.0,
    height: int = 480,
    show_residual_strip: bool = True,
) -> go.Figure:
    """
    HERO CENTERPIECE — The visual explanation of "what a digital twin is."

    Upgrades over the standard build_twin_overlay:
      • Larger default height (480px vs 380px)
      • Gradient-opacity divergence shading
      • Max-divergence callout arrow with annotation
      • "Digital Twin = Physics Model vs Reality" inline annotation
      • Glow marker at max-divergence point
      • Spike crosshair hover mode
      • Mean/max divergence stats in subtitle

    Args:
        history:         List of dicts {tick, predicted, actual, timestamp}
        channel:         CHANNEL_META key ("egt", "rpm", etc.)
        composite_score: 0–1+ from M1 residual engine
        height:          Chart height in px (default 480 for centerpiece)
        show_residual_strip: Show the residual bar subplot below

    Returns:
        go.Figure — ready for st.plotly_chart()
    """
    meta = CHANNEL_META.get(channel, {"label": channel, "unit": "", "color": _PREDICTED})

    ticks      = [d["tick"]      for d in history]
    predicted  = [d["predicted"] for d in history]
    actual     = [d["actual"]    for d in history]
    residuals  = [a - p for a, p in zip(actual, predicted)]

    n = len(ticks)

    # ── Divergence statistics ─────────────────────────────────────────────────
    abs_residuals = [abs(r) for r in residuals]
    max_div       = max(abs_residuals) if abs_residuals else 0.0
    mean_div      = sum(abs_residuals) / max(len(abs_residuals), 1)
    max_div_idx   = abs_residuals.index(max_div) if abs_residuals else 0

    # ── Fill colour & gradient by severity ────────────────────────────────────
    if composite_score < 0.10:
        fill_gradient = _GRAD_HEALTHY
        fill_color    = _FILL_HEALTHY
        band_label    = "Healthy"
        band_color    = "#10b981"
        band_icon     = "●"
    elif composite_score < 0.35:
        fill_gradient = _GRAD_CAUTION
        fill_color    = _FILL_CAUTION
        band_label    = "Caution"
        band_color    = "#f59e0b"
        band_icon     = "▲"
    else:
        fill_gradient = _GRAD_FAULT
        fill_color    = _FILL_FAULT
        band_label    = "FAULT"
        band_color    = "#ef4444"
        band_icon     = "◆"

    rows        = 2 if show_residual_strip else 1
    row_heights = [0.74, 0.26] if show_residual_strip else [1.0]

    fig = make_subplots(
        rows=rows, cols=1,
        shared_xaxes=True,
        row_heights=row_heights,
        vertical_spacing=0.05,
        subplot_titles=[
            "",
            "Residual (Actual − Predicted)" if show_residual_strip else "",
        ],
    )

    # ── Trace 1: Predicted (blue, slightly thicker for centerpiece) ───────────
    fig.add_trace(go.Scatter(
        x=ticks, y=predicted,
        mode="lines",
        name="🔵 Predicted (Physics Twin)",
        line=dict(color=_PREDICTED, width=3, dash="solid",
                  shape="spline", smoothing=0.8),
        hovertemplate=(
            f"<b>🔵 Predicted {meta['label']}</b><br>"
            f"Tick: %{{x}}<br>"
            f"Value: %{{y:.2f}} {meta['unit']}<br>"
            f"<i>What the physics model expects</i>"
            "<extra></extra>"
        ),
    ), row=1, col=1)

    # ── Trace 2: Invisible predicted (fill anchor) ────────────────────────────
    fig.add_trace(go.Scatter(
        x=ticks, y=predicted,
        mode="lines",
        line=dict(color="rgba(0,0,0,0)", width=0),
        showlegend=False,
        hoverinfo="skip",
    ), row=1, col=1)

    # ── Trace 3: Actual (amber) + fill to predicted ──────────────────────────
    # Use per-segment fill opacity that intensifies where divergence is larger
    fig.add_trace(go.Scatter(
        x=ticks, y=actual,
        mode="lines",
        name="🟠 Actual (Engine Sensors)",
        line=dict(color=_ACTUAL, width=3, shape="spline", smoothing=0.8),
        fill="tonexty",
        fillcolor=fill_gradient[2],  # use the richest gradient band
        hovertemplate=(
            f"<b>🟠 Actual {meta['label']}</b><br>"
            f"Tick: %{{x}}<br>"
            f"Value: %{{y:.2f}} {meta['unit']}<br>"
            f"<i>What the engine actually does</i>"
            "<extra></extra>"
        ),
    ), row=1, col=1)

    # ── Divergence fill band (upper + lower boundary for gradient effect) ─────
    # Add a faint secondary fill using a mid-gradient opacity
    upper = [max(p, a) for p, a in zip(predicted, actual)]
    lower = [min(p, a) for p, a in zip(predicted, actual)]

    fig.add_trace(go.Scatter(
        x=ticks, y=upper,
        mode="lines",
        line=dict(color="rgba(0,0,0,0)", width=0),
        showlegend=False,
        hoverinfo="skip",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=ticks, y=lower,
        mode="lines",
        line=dict(color="rgba(0,0,0,0)", width=0),
        fill="tonexty",
        fillcolor=fill_gradient[0],  # lighter inner glow
        showlegend=False,
        hoverinfo="skip",
    ), row=1, col=1)

    # ── Max-divergence glow marker ────────────────────────────────────────────
    if n > 0:
        mx_tick = ticks[max_div_idx]
        mx_pred = predicted[max_div_idx]
        mx_act  = actual[max_div_idx]

        # Glow ring (larger transparent marker behind)
        fig.add_trace(go.Scatter(
            x=[mx_tick, mx_tick],
            y=[mx_pred, mx_act],
            mode="markers",
            marker=dict(
                size=18,
                color=["rgba(96,165,250,0.3)", "rgba(245,158,11,0.3)"],
                line=dict(width=0),
            ),
            showlegend=False,
            hoverinfo="skip",
        ), row=1, col=1)

        # Core dots
        fig.add_trace(go.Scatter(
            x=[mx_tick, mx_tick],
            y=[mx_pred, mx_act],
            mode="markers",
            marker=dict(
                size=9,
                color=[_PREDICTED, _ACTUAL],
                line=dict(width=2, color="rgba(255,255,255,0.6)"),
                symbol="circle",
            ),
            name="Max Divergence",
            hovertemplate=(
                f"<b>Max Divergence Point</b><br>"
                f"Tick: {mx_tick}<br>"
                f"Gap: {max_div:.2f} {meta['unit']}<br>"
                f"Pred: {mx_pred:.2f} | Act: {mx_act:.2f}"
                "<extra></extra>"
            ),
        ), row=1, col=1)

        # Vertical connector line at max divergence
        fig.add_shape(
            type="line",
            x0=mx_tick, x1=mx_tick,
            y0=min(mx_pred, mx_act), y1=max(mx_pred, mx_act),
            line=dict(color=band_color, width=2, dash="dot"),
            row=1, col=1,
        )

        # Max divergence annotation arrow
        fig.add_annotation(
            x=mx_tick,
            y=max(mx_pred, mx_act) + (max_div * 0.15),
            text=(
                f"<b>MAX GAP</b><br>"
                f"<span style='font-size:11px'>{max_div:.2f} {meta['unit']}</span>"
            ),
            showarrow=True,
            arrowhead=2,
            arrowsize=1.2,
            arrowwidth=1.5,
            arrowcolor=band_color,
            ax=40, ay=-45,
            bordercolor=band_color,
            borderwidth=1.5,
            borderpad=6,
            bgcolor="rgba(10,14,26,0.85)",
            font=dict(color=band_color, size=11, family=_FONT),
            row=1, col=1,
        )

    # ── Residual strip (bottom subplot) ──────────────────────────────────────
    if show_residual_strip:
        max_abs_r = max(abs(r) for r in residuals) if residuals else 1.0
        res_colors = [
            "#ef4444" if abs(r) > 0.6 * max_abs_r
            else "#f59e0b" if abs(r) > 0.3 * max_abs_r
            else "#10b981"
            for r in residuals
        ]

        fig.add_trace(go.Bar(
            x=ticks, y=residuals,
            name="Residual",
            marker=dict(
                color=res_colors,
                opacity=0.80,
                line=dict(width=0),
            ),
            hovertemplate=(
                f"<b>Residual</b><br>"
                f"Tick: %{{x}}<br>"
                f"Δ: %{{y:.3f}} {meta['unit']}"
                "<extra></extra>"
            ),
        ), row=2, col=1)

        # Zero line
        fig.add_hline(
            y=0,
            line=dict(color="rgba(148,163,184,0.3)", width=1, dash="dot"),
            row=2, col=1,
        )

        fig.update_yaxes(
            title_text=f"Residual ({meta['unit']})",
            row=2, col=1,
            showgrid=True, gridcolor=_GRID,
            zeroline=False,
            tickfont=dict(size=9),
        )

    # ── Fault event markers (high-residual vertical lines) ────────────────────
    if residuals:
        max_abs_res = max(abs(r) for r in residuals) or 1.0
        threshold   = max_abs_res * 0.65
        for i, (tick, res) in enumerate(zip(ticks, residuals)):
            if abs(res) >= threshold and i > 3:
                fig.add_vline(
                    x=tick,
                    line=dict(color="rgba(239,68,68,0.25)", width=1.5, dash="dot"),
                    row=1, col=1,
                )

    # ── Annotations ───────────────────────────────────────────────────────────
    # Status badge (top-right)
    fig.add_annotation(
        text=f"{band_icon} {band_label}",
        xref="paper", yref="paper",
        x=0.99, y=0.97,
        xanchor="right", yanchor="top",
        font=dict(color=band_color, size=13, family=_FONT),
        showarrow=False,
        bgcolor="rgba(10,14,26,0.75)",
        bordercolor=band_color,
        borderwidth=1,
        borderpad=6,
    )

    # Composite score + stats (top-right, below badge)
    fig.add_annotation(
        text=(
            f"<span style='color:{_TEXT}'>Score: </span>"
            f"<b style='color:{band_color}'>{composite_score:.3f}</b>"
            f"<br><span style='color:{_TEXT}; font-size:10px'>"
            f"Mean Δ: {mean_div:.2f}  ·  Max Δ: {max_div:.2f} {meta['unit']}</span>"
        ),
        xref="paper", yref="paper",
        x=0.99, y=0.86,
        xanchor="right", yanchor="top",
        font=dict(color=_TEXT, size=11, family=_FONT),
        showarrow=False,
        bgcolor="rgba(10,14,26,0.6)",
        borderpad=5,
    )

    # "What is a Digital Twin?" inline annotation (top-left)
    fig.add_annotation(
        text=(
            f"<span style='color:#64748b; font-size:10px'>"
            f"DIGITAL TWIN = The gap between what the physics model predicts "
            f"and what the engine actually does</span>"
        ),
        xref="paper", yref="paper",
        x=0.01, y=0.97,
        xanchor="left", yanchor="top",
        font=dict(size=10, family=_FONT, color="#64748b"),
        showarrow=False,
        bgcolor="rgba(10,14,26,0.5)",
        borderpad=4,
    )

    # ── Layout ────────────────────────────────────────────────────────────────
    title_html = (
        f"<b style='color:{_TEXT_TITLE}; font-size:16px'>"
        f"{meta['label']} — Digital Twin Overlay</b>"
        f"<br><span style='font-size:12px; color:{_TEXT}'>"
        f"<span style='color:{_PREDICTED}'>━━</span> Predicted (Physics Model)  ·  "
        f"<span style='color:{_ACTUAL}'>━━</span> Actual (Sensor)  ·  "
        f"<span style='color:{band_color}'>▓▓</span> Divergence Gap</span>"
    )

    layout_cfg = _base_layout(
        title=dict(
            text=title_html,
            x=0.01, xanchor="left",
            font=dict(size=16, family=_FONT, color=_TEXT_TITLE),
        ),
        height=height,
        hovermode="x unified",
    )
    layout_cfg["xaxis"]["title"] = "Simulation Tick"
    layout_cfg["yaxis"]["title"] = f"{meta['label']} ({meta['unit']})"

    # Spike crosshair for precise reading
    layout_cfg["xaxis"]["showspikes"] = True
    layout_cfg["xaxis"]["spikecolor"] = "rgba(96,165,250,0.4)"
    layout_cfg["xaxis"]["spikethickness"] = 1
    layout_cfg["xaxis"]["spikemode"] = "across"
    layout_cfg["xaxis"]["spikedash"] = "dot"

    layout_cfg["yaxis"]["showspikes"] = True
    layout_cfg["yaxis"]["spikecolor"] = "rgba(96,165,250,0.3)"
    layout_cfg["yaxis"]["spikethickness"] = 1
    layout_cfg["yaxis"]["spikedash"] = "dot"

    fig.update_layout(**layout_cfg)

    # Subplot title styling
    for ann in fig.layout.annotations:
        if ann.text and "Residual" in str(ann.text):
            ann.font = dict(size=10, color=_TEXT, family=_FONT)

    return fig


def build_centerpiece_pair(
    history_by_channel: dict[str, list[dict]],
    composite_score: float = 0.0,
    height: int = 480,
) -> tuple[go.Figure, go.Figure]:
    """
    Build the hero EGT + RPM centerpiece twin overlays.

    Returns:
        (fig_egt, fig_rpm) — two full-width centerpiece figures.
    """
    fig_egt = build_centerpiece_twin_overlay(
        history_by_channel.get("egt", []),
        "egt",
        composite_score,
        height=height,
        show_residual_strip=True,
    )
    fig_rpm = build_centerpiece_twin_overlay(
        history_by_channel.get("rpm", []),
        "rpm",
        composite_score,
        height=height,
        show_residual_strip=True,
    )
    return fig_egt, fig_rpm


# ─────────────────────────────────────────────────────────────────────────────
#  DUAL CHANNEL VIEW  (EGT + RPM side-by-side)
# ─────────────────────────────────────────────────────────────────────────────

def build_dual_overlay(
    history_by_channel: dict[str, list[dict]],
    composite_score: float = 0.0,
    height: int = 340,
) -> tuple[go.Figure, go.Figure]:
    """
    Build twin overlay charts for EGT and RPM side-by-side.

    Args:
        history_by_channel: {"egt": [...], "rpm": [...]}
        composite_score: Latest composite score.

    Returns:
        (fig_egt, fig_rpm)  — two Figure objects, render in st.columns().
    """
    fig_egt = build_twin_overlay(
        history_by_channel.get("egt", []),
        "egt",
        composite_score,
        height=height,
        show_residual_strip=True,
    )
    fig_rpm = build_twin_overlay(
        history_by_channel.get("rpm", []),
        "rpm",
        composite_score,
        height=height,
        show_residual_strip=True,
    )
    return fig_egt, fig_rpm


# ─────────────────────────────────────────────────────────────────────────────
#  HEALTH GAUGE  (Plotly Indicator)
# ─────────────────────────────────────────────────────────────────────────────

def build_health_gauge(composite_score: float, height: int = 250) -> go.Figure:
    """
    Premium circular health gauge with gradient arc, glow ring & status badges.

    composite_score is 0–1+ (M1 output); converts to health = 100 - score*100.
    Green 70–100, Yellow 40–69, Red 0–39.

    Visual upgrades over a basic indicator:
      • 20-step gradient arc (smooth red → amber → green colour transition)
      • Outer glow ring (translucent concentric indicator)
      • Status badge annotation with severity label
      • Composite score readout beneath the value
      • Refined tick marks and dark theme integration
    """
    health = max(0.0, min(100.0, 100.0 - composite_score * 100.0))

    if health >= 70:
        color  = "#10b981"
        status = "Healthy"
        glow   = "rgba(16,185,129,0.25)"
    elif health >= 40:
        color  = "#f59e0b"
        status = "Caution"
        glow   = "rgba(245,158,11,0.25)"
    else:
        color  = "#ef4444"
        status = "FAULT"
        glow   = "rgba(239,68,68,0.30)"

    # ── Gradient arc steps (20 segments for smooth colour transition) ─────────
    # Red (0-39) → Amber (40-69) → Green (70-100)
    gradient_steps = []
    n_steps = 20
    for i in range(n_steps):
        lo = (100 / n_steps) * i
        hi = (100 / n_steps) * (i + 1)
        frac = (lo + hi) / 2.0 / 100.0  # 0.0 – 1.0

        if frac < 0.40:
            # Red zone — deep red to lighter red
            r, g, b = 239, 68, 68
            opacity = 0.08 + 0.10 * (frac / 0.40)
        elif frac < 0.70:
            # Amber zone — red-amber blend
            t = (frac - 0.40) / 0.30
            r = int(239 + (245 - 239) * t)
            g = int(68  + (158 -  68) * t)
            b = int(68  + ( 11 -  68) * t)
            opacity = 0.10 + 0.06 * t
        else:
            # Green zone — amber-green blend
            t = (frac - 0.70) / 0.30
            r = int(245 + ( 16 - 245) * t)
            g = int(158 + (185 - 158) * t)
            b = int( 11 + (129 -  11) * t)
            opacity = 0.12 + 0.10 * t

        gradient_steps.append(
            dict(range=[lo, hi], color=f"rgba({r},{g},{b},{opacity:.2f})")
        )

    # ── Main gauge indicator ──────────────────────────────────────────────────
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=health,
        number=dict(
            suffix="",
            font=dict(size=42, color=color, family=_FONT),
            valueformat=".0f",
        ),
        delta=dict(
            reference=100,
            decreasing=dict(color="#ef4444", symbol="▼"),
            increasing=dict(color="#10b981", symbol="▲"),
            font=dict(size=13, family=_FONT),
            position="bottom",
        ),
        gauge=dict(
            axis=dict(
                range=[0, 100],
                tickwidth=1,
                tickcolor="rgba(148,163,184,0.25)",
                tickfont=dict(size=9, color=_TEXT, family=_FONT),
                dtick=10,
                tick0=0,
            ),
            bar=dict(
                color=color,
                thickness=0.28,
                line=dict(width=0),
            ),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            steps=gradient_steps,
            threshold=dict(
                line=dict(color="rgba(241,245,249,0.5)", width=3),
                thickness=0.82,
                value=health,
            ),
        ),
        title=dict(
            text=(
                f"<b style='font-size:14px; color:{_TEXT_TITLE}'>Engine Health</b>"
                f"<br>"
                f"<span style='font-size:12px; color:{color}; "
                f"letter-spacing:0.08em'>{status.upper()}</span>"
            ),
            font=dict(size=14, color=_TEXT_TITLE, family=_FONT),
        ),
        domain=dict(x=[0.05, 0.95], y=[0.08, 0.92]),
    ))

    # ── Annotations ───────────────────────────────────────────────────────────

    # Composite score readout (below the gauge number)
    fig.add_annotation(
        text=(
            f"<span style='color:{_TEXT}; font-size:10px'>Composite Score: </span>"
            f"<b style='color:{color}; font-size:11px'>{composite_score:.3f}</b>"
        ),
        xref="paper", yref="paper",
        x=0.5, y=0.08,
        xanchor="center", yanchor="bottom",
        showarrow=False,
        font=dict(family=_FONT, size=10, color=_TEXT),
    )

    # Status badge (top-right corner)
    badge_bg = glow.replace("0.25", "0.15").replace("0.30", "0.15")
    fig.add_annotation(
        text=f"● {status}",
        xref="paper", yref="paper",
        x=0.98, y=0.98,
        xanchor="right", yanchor="top",
        showarrow=False,
        font=dict(family=_FONT, size=10, color=color),
        bgcolor=badge_bg,
        bordercolor=color,
        borderwidth=1,
        borderpad=4,
    )

    # Zone labels along the bottom
    zone_labels = [
        (0.15, "#ef4444", "FAULT"),
        (0.50, "#f59e0b", "CAUTION"),
        (0.85, "#10b981", "HEALTHY"),
    ]
    for x_pos, z_color, z_label in zone_labels:
        fig.add_annotation(
            text=f"<span style='font-size:8px; letter-spacing:0.1em; color:{z_color}'>{z_label}</span>",
            xref="paper", yref="paper",
            x=x_pos, y=0.02,
            xanchor="center", yanchor="bottom",
            showarrow=False,
            font=dict(family=_FONT, size=8, color=z_color),
        )

    # ── Layout ────────────────────────────────────────────────────────────────
    fig.update_layout(
        height=height,
        paper_bgcolor=_BG_PAPER,
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=_FONT, color=_TEXT),
        margin=dict(l=16, r=16, t=36, b=28),
        # Outer glow ring via a subtle shape
        shapes=[
            # Outer glow arc (decorative ring)
            dict(
                type="circle",
                xref="paper", yref="paper",
                x0=0.02, y0=0.02, x1=0.98, y1=0.98,
                line=dict(color=glow, width=2, dash="dot"),
                fillcolor="rgba(0,0,0,0)",
            ),
        ],
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
#  RESIDUAL BAR CHART  (all 8 channels at once)
# ─────────────────────────────────────────────────────────────────────────────

def build_residual_bar(residuals: dict, height: int = 240) -> go.Figure:
    """
    Horizontal bar chart of latest per-channel residuals.
    Bars are coloured by absolute magnitude.
    """
    channels = list(residuals.keys())
    values   = [residuals[c] for c in channels]
    labels   = [CHANNEL_META.get(c, {}).get("label", c) for c in channels]
    abs_vals = [abs(v) for v in values]
    max_abs  = max(abs_vals) if abs_vals else 1.0

    bar_colors = [
        "#ef4444" if av / max_abs > 0.65 else
        "#f59e0b" if av / max_abs > 0.30 else
        "#10b981"
        for av in abs_vals
    ]

    fig = go.Figure(go.Bar(
        x=values,
        y=labels,
        orientation="h",
        marker=dict(color=bar_colors, opacity=0.8, line=dict(width=0)),
        text=[f"{v:+.3f}" for v in values],
        textposition="outside",
        textfont=dict(size=10, color=_TEXT),
        hovertemplate="<b>%{y}</b><br>Residual: %{x:.4f}<extra></extra>",
    ))

    fig.add_vline(x=0, line=dict(color="rgba(148,163,184,0.4)", width=1))

    layout = _base_layout(
        title=dict(
            text="<b>Per-Channel Residuals</b>  (Actual − Predicted)",
            font=dict(size=13, color=_TEXT_TITLE),
            x=0.01, xanchor="left",
        ),
        height=height,
        xaxis=dict(title="Residual magnitude", showgrid=True, gridcolor=_GRID, zeroline=False),
        yaxis=dict(showgrid=False, zeroline=False),
        showlegend=False,
    )
    fig.update_layout(**layout)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
#  DOMINANT CHANNELS  (Explainability bar — USP #3)
# ─────────────────────────────────────────────────────────────────────────────

def build_explainability_bar(dominant_channels: list[tuple], height: int = 220) -> go.Figure:
    """
    Horizontal bar chart from signature.dominant_channels.
    dominant_channels = [(channel_name, magnitude), ...] sorted DESC by M1.
    This IS the explainability data — no extra computation needed.
    """
    if not dominant_channels:
        fig = go.Figure()
        fig.update_layout(**_base_layout(height=height))
        return fig

    channels, values = zip(*dominant_channels)
    labels = [CHANNEL_META.get(c, {}).get("label", c) for c in channels]
    max_v  = max(values) or 1.0

    bar_colors = [
        CHANNEL_META.get(c, {}).get("color", _PREDICTED)
        for c in channels
    ]

    fig = go.Figure(go.Bar(
        x=list(values),
        y=list(labels),
        orientation="h",
        marker=dict(
            color=bar_colors,
            opacity=[0.4 + 0.6 * (v / max_v) for v in values],
            line=dict(width=0),
        ),
        text=[f"{v:.4f}" for v in values],
        textposition="outside",
        textfont=dict(size=10, color=_TEXT),
        hovertemplate="<b>%{y}</b><br>Contribution: %{x:.4f}<extra></extra>",
    ))

    layout = _base_layout(
        title=dict(
            text="<b>Sensor Contributions</b>  — Which sensors drove this alert?",
            font=dict(size=13, color=_TEXT_TITLE),
            x=0.01, xanchor="left",
        ),
        height=height,
        xaxis=dict(title="Feature magnitude (from M1 dominant_channels)", showgrid=True, gridcolor=_GRID, zeroline=False),
        yaxis=dict(showgrid=False, zeroline=False),
        showlegend=False,
    )
    fig.update_layout(**layout)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
#  DATA HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def build_history_from_engine(
    engine,
    n_ticks: int = 80,
    fault_at: Optional[int] = None,
    fault_type: str = "overheating",
) -> tuple[dict[str, list[dict]], float]:
    """
    Run the MockEngine for n_ticks and collect per-channel history.

    Args:
        engine:    A MockEngine instance (or any M1-compatible engine).
        n_ticks:   Number of ticks to simulate.
        fault_at:  If set, inject fault_type at this tick number.
        fault_type: Which fault to inject.

    Returns:
        (history_by_channel, final_composite_score)

        history_by_channel = {
            "egt": [{"tick": 1, "predicted": ..., "actual": ..., "timestamp": ...}, ...],
            "rpm": [...],
            ...
        }
    """
    channels = ["egt", "rpm", "cht", "oil_pressure", "oil_temp",
                "fuel_flow", "vibration_amplitude", "vibration_freq"]

    history: dict[str, list[dict]] = {ch: [] for ch in channels}
    final_composite = 0.0

    for tick in range(1, n_ticks + 1):
        if fault_at and tick == fault_at:
            engine.inject_fault(fault_type)

        residual_payload = engine.next_tick()
        pred, actual     = engine.get_raw()
        final_composite  = residual_payload["composite_score"]

        for ch in channels:
            history[ch].append({
                "tick":      tick,
                "predicted": pred.get(ch, 0.0),
                "actual":    actual.get(ch, 0.0),
                "timestamp": residual_payload["timestamp"],
                "residual":  residual_payload["residuals"].get(ch, 0.0),
            })

    return history, final_composite


# ─────────────────────────────────────────────────────────────────────────────
#  RUL TREND CHART  (§2A — Remaining Useful Life with confidence band)
# ─────────────────────────────────────────────────────────────────────────────

_TREND_ARROWS = {
    "degrading":  ("↓", "#ef4444"),
    "improving":  ("↑", "#10b981"),
    "stable":     ("→", "#f59e0b"),
}


def build_rul_trend(
    rul_history: list[dict],
    height: int = 260,
) -> go.Figure:
    """
    Line chart of RUL over time with 90% confidence band shading.

    Args:
        rul_history: List of §2A dicts, each containing:
                     {rul_hours, confidence_lower, confidence_upper, trend, ...}
        height:      Chart height in px.

    Returns:
        go.Figure ready for st.plotly_chart()
    """
    if not rul_history:
        fig = go.Figure()
        fig.update_layout(**_base_layout(height=height))
        fig.add_annotation(
            text="Awaiting RUL data...",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False,
            font=dict(color=_TEXT, size=14),
        )
        return fig

    ticks = list(range(1, len(rul_history) + 1))
    rul_values = [d.get("rul_hours", 0) for d in rul_history]
    ci_lower = [d.get("confidence_lower", d.get("rul_hours", 0)) for d in rul_history]
    ci_upper = [d.get("confidence_upper", d.get("rul_hours", 0)) for d in rul_history]

    latest = rul_history[-1]
    trend = latest.get("trend", "stable")
    arrow, trend_color = _TREND_ARROWS.get(trend, ("→", "#f59e0b"))

    # Colour by latest RUL
    latest_rul = latest.get("rul_hours", 0)
    if latest_rul > 150:
        line_color = "#10b981"
    elif latest_rul > 50:
        line_color = "#f59e0b"
    else:
        line_color = "#ef4444"

    fig = go.Figure()

    # Confidence band — upper boundary (invisible, anchor for fill)
    fig.add_trace(go.Scatter(
        x=ticks, y=ci_upper,
        mode="lines",
        line=dict(color="rgba(0,0,0,0)", width=0),
        showlegend=False,
        hoverinfo="skip",
    ))

    # Confidence band — lower boundary (filled to upper)
    fig.add_trace(go.Scatter(
        x=ticks, y=ci_lower,
        mode="lines",
        line=dict(color="rgba(0,0,0,0)", width=0),
        fill="tonexty",
        fillcolor=f"rgba({','.join(str(int(line_color.lstrip('#')[i:i+2], 16)) for i in (0, 2, 4))},0.12)",
        showlegend=True,
        name="90% CI",
        hoverinfo="skip",
    ))

    # Main RUL line
    fig.add_trace(go.Scatter(
        x=ticks, y=rul_values,
        mode="lines+markers",
        name="RUL (hours)",
        line=dict(color=line_color, width=2.5, shape="spline", smoothing=0.6),
        marker=dict(size=4, color=line_color),
        hovertemplate=(
            "<b>RUL Estimate</b><br>"
            "Tick: %{x}<br>"
            "RUL: %{y:.1f} hrs<br>"
            f"Trend: {trend} {arrow}"
            "<extra></extra>"
        ),
    ))

    # Trend arrow annotation (top-right)
    fig.add_annotation(
        text=f"<span style='font-size:18px; color:{trend_color}'>{arrow}</span>"
             f"<br><span style='font-size:10px; color:{trend_color}'>{trend.upper()}</span>",
        xref="paper", yref="paper",
        x=0.98, y=0.95,
        xanchor="right", yanchor="top",
        showarrow=False,
        bgcolor="rgba(10,14,26,0.7)",
        bordercolor=trend_color,
        borderwidth=1,
        borderpad=6,
    )

    # Latest value annotation
    fig.add_annotation(
        text=f"<b style='color:{line_color}'>{latest_rul:.0f}h</b>",
        x=ticks[-1], y=rul_values[-1],
        xanchor="left",
        showarrow=True,
        arrowhead=2,
        arrowcolor=line_color,
        ax=30, ay=-20,
        font=dict(color=line_color, size=12),
        bgcolor="rgba(10,14,26,0.7)",
        borderpad=4,
    )

    layout = _base_layout(
        title=dict(
            text=(
                f"<b style='color:{_TEXT_TITLE}'>RUL Trend</b>"
                f"  <span style='font-size:11px; color:{_TEXT}'>"
                f"Remaining Useful Life · {latest.get('model_id', 'mock')}</span>"
            ),
            x=0.01, xanchor="left",
            font=dict(size=14, color=_TEXT_TITLE),
        ),
        height=height,
    )
    layout["xaxis"]["title"] = "Tick"
    layout["yaxis"]["title"] = "RUL (flight-hours)"

    fig.update_layout(**layout)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
#  CLASSIFICATION BADGE HTML  (§4A — for alert panel entries)
# ─────────────────────────────────────────────────────────────────────────────

# Icons per fault label
_CLS_ICONS = {
    "overheating":        "\U0001f525",
    "oil_pressure_drop":  "\U0001f4a7",
    "misfire":            "\u26a1",
    "injector_fault":     "\u26fd",
    "vibration_anomaly":  "\U0001f4f3",
    "unknown":            "\u2753",
}


def build_classification_badge_html(cls_dict: Optional[dict]) -> str:
    """
    Build an HTML badge string for a §4A classification payload.

    Returns something like:
        🔥 Overheating · 87%

    Styled as an inline pill for embedding in the alert panel.
    Returns empty string if cls_dict is None.
    """
    if not cls_dict:
        return ""

    label = cls_dict.get("fault_label", "unknown")
    confidence = cls_dict.get("confidence", 0.0)
    display_label = label.replace("_", " ").title()
    icon = _CLS_ICONS.get(label, "\u2753")

    # Colour by confidence
    if confidence >= 0.80:
        badge_color = "#60a5fa"
        badge_bg = "rgba(96,165,250,0.15)"
        badge_border = "rgba(96,165,250,0.35)"
    elif confidence >= 0.60:
        badge_color = "#a78bfa"
        badge_bg = "rgba(167,139,250,0.12)"
        badge_border = "rgba(167,139,250,0.30)"
    else:
        badge_color = "#94a3b8"
        badge_bg = "rgba(148,163,184,0.10)"
        badge_border = "rgba(148,163,184,0.25)"

    return (
        f'<span style="'
        f'background:{badge_bg};'
        f'border:1px solid {badge_border};'
        f'color:{badge_color};'
        f'font-size:0.72rem;'
        f'font-weight:700;'
        f'padding:3px 10px;'
        f'border-radius:8px;'
        f'letter-spacing:0.04em;'
        f'margin-left:8px;'
        f'">{icon} {display_label} &middot; {confidence:.0%}</span>'
    )


def build_rul_card_html(rul_dict: Optional[dict]) -> str:
    """
    Build HTML for the RUL metric card with trend arrow and confidence interval.

    Returns a styled div showing: RUL value, trend arrow, and CI range.
    """
    if not rul_dict:
        return """
        <div class="metric-card" style="padding:14px; text-align:center; min-height:90px;">
            <div style="font-size:0.62rem; color:#64748b; letter-spacing:0.08em;
                        text-transform:uppercase; margin-bottom:5px;">RUL (HRS)</div>
            <div style="font-size:1.5rem; font-weight:700; color:#64748b;">---</div>
            <div style="font-size:0.6rem; color:#475569; margin-top:2px;">Awaiting data</div>
        </div>
        """

    rul = rul_dict.get("rul_hours", 0)
    trend = rul_dict.get("trend", "stable")
    ci_lo = rul_dict.get("confidence_lower", rul)
    ci_hi = rul_dict.get("confidence_upper", rul)

    arrow, trend_color = _TREND_ARROWS.get(trend, ("→", "#f59e0b"))
    rul_color = "#10b981" if rul > 150 else "#f59e0b" if rul > 50 else "#ef4444"

    return f"""
    <div class="metric-card" style="padding:14px; text-align:center; min-height:90px;">
        <div style="font-size:0.62rem; color:#64748b; letter-spacing:0.08em;
                    text-transform:uppercase; margin-bottom:5px;">RUL (HRS)</div>
        <div style="display:flex; align-items:baseline; justify-content:center; gap:6px;">
            <span style="font-size:1.5rem; font-weight:700; color:{rul_color};">{rul:.0f}</span>
            <span style="font-size:1.2rem; color:{trend_color}; font-weight:700;">{arrow}</span>
        </div>
        <div style="font-size:0.58rem; color:#475569; margin-top:2px;">
            {ci_lo:.0f}–{ci_hi:.0f}h (90% CI) · {trend}
        </div>
    </div>
    """


# ─────────────────────────────────────────────────────────────────────────────
#  HISTORY VIEW CHARTS  (Step 15 — composite_score + RUL over full mission)
# ─────────────────────────────────────────────────────────────────────────────

def build_composite_trend(
    records: list[dict],
    fault_at: Optional[int] = None,
    height: int = 280,
) -> go.Figure:
    """
    Composite-score time-series with coloured severity-band fills.

    records: list of dicts with keys: tick, composite_score, fault_active
    fault_at: optional tick number where fault was injected (draws a vertical line)
    """
    if not records:
        fig = go.Figure()
        fig.update_layout(**_base_layout(height=height,
            title=dict(text="<b>Composite Score Trend</b>",
                       font=dict(size=13, color=_TEXT_TITLE), x=0.01)))
        return fig

    ticks  = [r["tick"] for r in records]
    scores = [r["composite_score"] for r in records]

    # Colour each segment by severity
    seg_colors = []
    for s in scores:
        if s > 0.35:
            seg_colors.append(_PAL_FAULT)
        elif s > 0.10:
            seg_colors.append(_PAL_CAUTION)
        else:
            seg_colors.append(_PAL_HEALTHY)

    # Band fill helpers — filled areas for the three bands
    max_t = max(ticks)
    fig = go.Figure()

    # Background bands
    for lo, hi, clr, label in [
        (0, 0.10,  "rgba(16,185,129,0.07)",  "Healthy (<0.10)"),
        (0.10, 0.35, "rgba(245,158,11,0.07)", "Caution (0.10–0.35)"),
        (0.35, 1.2,  "rgba(239,68,68,0.07)",  "Fault (>0.35)"),
    ]:
        fig.add_hrect(y0=lo, y1=hi, fillcolor=clr, line_width=0,
                      annotation_text=label,
                      annotation_position="right",
                      annotation=dict(font=dict(size=9, color=_TEXT)))

    # Main composite line
    fig.add_trace(go.Scatter(
        x=ticks, y=scores,
        mode="lines",
        name="Composite Score",
        line=dict(color="#60a5fa", width=2),
        fill="tozeroy",
        fillcolor="rgba(96,165,250,0.06)",
        hovertemplate="Tick %{x}<br>Score: %{y:.4f}<extra></extra>",
    ))

    # Fault injection vertical line
    if fault_at and fault_at in ticks:
        fig.add_vline(
            x=fault_at,
            line=dict(color="#ef4444", width=1.5, dash="dash"),
            annotation_text=f"Fault @ T{fault_at}",
            annotation_position="top right",
            annotation=dict(font=dict(size=10, color="#ef4444")),
        )

    # Threshold lines
    fig.add_hline(y=0.10, line=dict(color="#10b981", width=1, dash="dot"))
    fig.add_hline(y=0.35, line=dict(color="#f59e0b", width=1, dash="dot"))

    layout = _base_layout(
        title=dict(text="<b>Composite Score</b>  — degradation over mission",
                   font=dict(size=13, color=_TEXT_TITLE), x=0.01, xanchor="left"),
        height=height,
        xaxis=dict(title="Tick", showgrid=True, gridcolor=_GRID, zeroline=False),
        yaxis=dict(title="composite_score (0–1+)", showgrid=True,
                   gridcolor=_GRID, zeroline=False, range=[0, max(0.5, max(scores) * 1.15)]),
        showlegend=False,
    )
    fig.update_layout(**layout)
    return fig


_PAL_HEALTHY = "rgba(16,185,129,0.1)"
_PAL_CAUTION = "rgba(245,158,11,0.1)"
_PAL_FAULT   = "rgba(239,68,68,0.1)"


def build_rul_trend_slim(
    records: list[dict],
    fault_at: Optional[int] = None,
    height: int = 220,
) -> go.Figure:
    """
    RUL over mission timeline with 90% CI shading.

    records: list of dicts with keys: tick, rul_hours, confidence_lower, confidence_upper, trend
    """
    if not records:
        fig = go.Figure()
        fig.update_layout(**_base_layout(height=height,
            title=dict(text="<b>RUL Trend</b>",
                       font=dict(size=13, color=_TEXT_TITLE), x=0.01)))
        return fig

    ticks  = [r["tick"]             for r in records]
    rul    = [r["rul_hours"]        for r in records]
    lo     = [r["confidence_lower"] for r in records]
    hi     = [r["confidence_upper"] for r in records]

    fig = go.Figure()

    # CI shading
    fig.add_trace(go.Scatter(
        x=ticks + ticks[::-1],
        y=hi + lo[::-1],
        fill="toself",
        fillcolor="rgba(96,165,250,0.08)",
        line=dict(width=0),
        name="90% CI",
        hoverinfo="skip",
    ))

    # RUL line
    rul_color = "#10b981" if (rul[-1] > 150) else "#f59e0b" if (rul[-1] > 50) else "#ef4444"
    fig.add_trace(go.Scatter(
        x=ticks, y=rul,
        mode="lines",
        name="RUL (hours)",
        line=dict(color=rul_color, width=2.5),
        hovertemplate="Tick %{x}<br>RUL: %{y:.1f}h<extra></extra>",
    ))

    if fault_at and fault_at in ticks:
        fig.add_vline(
            x=fault_at,
            line=dict(color="#ef4444", width=1.5, dash="dash"),
            annotation_text=f"Fault @ T{fault_at}",
            annotation_position="top right",
            annotation=dict(font=dict(size=10, color="#ef4444")),
        )

    layout = _base_layout(
        title=dict(text="<b>Remaining Useful Life</b>  — §2A estimate over mission",
                   font=dict(size=13, color=_TEXT_TITLE), x=0.01, xanchor="left"),
        height=height,
        xaxis=dict(title="Tick", showgrid=True, gridcolor=_GRID, zeroline=False),
        yaxis=dict(title="RUL (hours)", showgrid=True,
                   gridcolor=_GRID, zeroline=False, rangemode="tozero"),
        showlegend=True,
    )
    fig.update_layout(**layout)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
#  INNOVATION B — Anomaly Confidence Heatmap
# ─────────────────────────────────────────────────────────────────────────────

def build_anomaly_heatmap(
    history: dict,
    channels: Optional[list] = None,
    height: int = 280,
) -> go.Figure:
    """
    2-D heatmap: channels (rows) × ticks (columns), coloured by residual magnitude.

    Shows *when* each sensor started diverging — often 5-10 ticks before
    composite_score crosses the fault threshold (the 'early warning' story).

    history: output of build_history_from_engine() — dict of channel → list of dicts
    channels: optional subset of channel keys (default: all 8)
    """
    _channels = channels or [
        "egt", "rpm", "cht", "oil_pressure",
        "oil_temp", "fuel_flow", "vibration_amplitude", "vibration_freq",
    ]

    z_data:   list = []
    y_labels: list = []
    x_ticks        = None

    for ch in _channels:
        rows = history.get(ch, [])
        if not rows:
            continue
        if x_ticks is None:
            x_ticks = [r["tick"] for r in rows]
        residuals = [abs(r.get("residual", 0.0)) for r in rows]
        z_data.append(residuals)
        y_labels.append(CHANNEL_META.get(ch, {}).get("label", ch))

    if not z_data or x_ticks is None:
        fig = go.Figure()
        fig.update_layout(**_base_layout(height=height,
            title=dict(text="<b>Anomaly Heatmap</b>",
                       font=dict(size=13, color=_TEXT_TITLE), x=0.01)))
        return fig

    _flat = [v for row in z_data for v in row]
    _zmax = max(_flat) if _flat else 1.0

    fig = go.Figure(go.Heatmap(
        z=z_data,
        x=x_ticks,
        y=y_labels,
        colorscale=[
            [0.00, "#10b981"],   # green  — healthy
            [0.30, "#f59e0b"],   # amber  — caution
            [1.00, "#ef4444"],   # red    — fault
        ],
        zmin=0,
        zmax=_zmax,
        showscale=True,
        colorbar=dict(
            title=dict(text="Residual", font=dict(size=10, color=_TEXT)),
            tickfont=dict(size=9, color=_TEXT),
            thickness=12,
            len=0.85,
        ),
        hovertemplate="<b>%{y}</b><br>Tick %{x}<br>|Residual|: %{z:.5f}<extra></extra>",
    ))

    layout = _base_layout(
        title=dict(
            text="<b>Anomaly Confidence Heatmap</b>"
                 "  — |residual| per sensor × tick",
            font=dict(size=13, color=_TEXT_TITLE), x=0.01, xanchor="left",
        ),
        height=height,
        xaxis=dict(title="Tick", showgrid=False, zeroline=False,
                   tickfont=dict(size=9, color=_TEXT)),
        yaxis=dict(showgrid=False, zeroline=False,
                   tickfont=dict(size=10, color=_TEXT), automargin=True),
        showlegend=False,
    )
    fig.update_layout(**layout)
    return fig
