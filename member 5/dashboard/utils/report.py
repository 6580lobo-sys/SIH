"""
utils/report.py
===============
Step 13 — Auto-generated mission report.

Builds a self-contained, single-page HTML document summarising a completed
mission (Live or Replay).  Returned as a UTF-8 string ready for
`st.download_button(data=html, file_name="mission_report.html", mime="text/html")`.

Contents
--------
  • Mission header  (UAV ID, mission name, date/time, profile, mode)
  • Health trend    (inline SVG spark-line from composite_score history)
  • Fault event table  (tick, severity, fault label, dominant channels, recommendation)
  • Final RUL        (value, CI, trend)
  • Maintenance recommendations summary

Zero extra dependencies — pure Python + HTML/CSS only.

Usage
-----
    from utils.report import generate_html_report
    html = generate_html_report(...)
    st.download_button("📥 Download Report", data=html,
                       file_name="mission_report.html", mime="text/html")
"""

from __future__ import annotations

import html as _html
import math
import time
from datetime import datetime
from typing import Optional


# ── Colour palette (matches dashboard dark theme) ─────────────────────────────
_PAL = {
    "bg":        "#0d1424",
    "card":      "#0f172a",
    "border":    "rgba(59,130,246,0.18)",
    "text":      "#94a3b8",
    "title":     "#f1f5f9",
    "green":     "#10b981",
    "amber":     "#f59e0b",
    "red":       "#ef4444",
    "blue":      "#60a5fa",
    "cyan":      "#06b6d4",
    "purple":    "#a78bfa",
}

_CHANNEL_LABELS = {
    "rpm":                 "RPM",
    "cht":                 "CHT",
    "egt":                 "EGT",
    "oil_pressure":        "Oil Pressure",
    "oil_temp":            "Oil Temperature",
    "fuel_flow":           "Fuel Flow",
    "vibration_amplitude": "Vibration Amplitude",
    "vibration_freq":      "Vibration Frequency",
}

_TREND_ARROW = {
    "degrading": ("↓", "#ef4444"),
    "improving": ("↑", "#10b981"),
    "stable":    ("→", "#f59e0b"),
}


# ── Spark-line SVG ────────────────────────────────────────────────────────────

def _build_sparkline_svg(
    values: list[float],
    width: int = 700,
    height: int = 120,
) -> str:
    """
    Build an inline SVG line chart from a list of float values (0.0–1.0+).
    Renders as a health-trend spark-line coloured by severity bands.
    """
    if not values:
        return ""

    n = len(values)
    if n < 2:
        return ""

    # Normalise to SVG coordinates
    vmin = min(values)
    vmax = max(values) or 1.0
    pad = 10

    def _x(i: int) -> float:
        return pad + (i / (n - 1)) * (width - 2 * pad)

    def _y(v: float) -> float:
        norm = (v - vmin) / max(vmax - vmin, 1e-6)
        # Flip: high composite = low health = top of chart
        return pad + (1 - norm) * (height - 2 * pad)

    # Build polyline points
    points = " ".join(f"{_x(i):.1f},{_y(v):.1f}" for i, v in enumerate(values))

    # Colour by final value
    last = values[-1]
    if last > 0.35:
        stroke = _PAL["red"]
    elif last > 0.10:
        stroke = _PAL["amber"]
    else:
        stroke = _PAL["green"]

    # Fill area under the line
    fill_pts = (
        f"{_x(0):.1f},{height - pad} "
        + points
        + f" {_x(n - 1):.1f},{height - pad}"
    )

    return f"""
<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg"
     style="width:100%; height:{height}px; background:rgba(0,0,0,0.3); border-radius:6px;">
  <!-- Grid lines -->
  {''.join(
      f'<line x1="{pad}" y1="{_y(t):.1f}" x2="{width-pad}" y2="{_y(t):.1f}" '
      f'stroke="rgba(59,130,246,0.1)" stroke-width="1"/>'
      for t in [0.10, 0.35, 0.60]
      if vmin <= t <= vmax
  )}
  <!-- Fill -->
  <polygon points="{fill_pts}" fill="{stroke}" opacity="0.10"/>
  <!-- Line -->
  <polyline points="{points}" fill="none" stroke="{stroke}"
            stroke-width="2" stroke-linejoin="round"/>
  <!-- Start / end dots -->
  <circle cx="{_x(0):.1f}" cy="{_y(values[0]):.1f}" r="4" fill="{_PAL['green']}"/>
  <circle cx="{_x(n-1):.1f}" cy="{_y(values[-1]):.1f}" r="5" fill="{stroke}"/>
  <!-- Labels -->
  <text x="{pad+2}" y="{height-pad-4}" fill="{_PAL['text']}"
        font-size="9" font-family="Inter,sans-serif">Tick 1</text>
  <text x="{width-pad-2}" y="{height-pad-4}" fill="{_PAL['text']}"
        font-size="9" font-family="Inter,sans-serif" text-anchor="end">Tick {n}</text>
  <text x="{_x(n-1)+6:.1f}" y="{_y(values[-1]):.1f}" fill="{stroke}"
        font-size="10" font-family="Inter,sans-serif" alignment-baseline="middle">
    {values[-1]:.3f}
  </text>
</svg>"""


# ── Fault event table ─────────────────────────────────────────────────────────

def _build_fault_table(alert_log: list[dict]) -> str:
    if not alert_log:
        return f"""
<div style="background:rgba(16,185,129,0.06); border:1px solid rgba(16,185,129,0.2);
            border-radius:8px; padding:16px; text-align:center; color:{_PAL['green']};">
    ✅ No fault events detected during this mission.
</div>"""

    rows = ""
    for alert in alert_log:
        sev = alert.get("severity", 0.0)
        sev_color = _PAL["red"] if sev >= 0.6 else _PAL["amber"] if sev >= 0.3 else _PAL["green"]
        sev_label = "HIGH" if sev >= 0.6 else "MEDIUM" if sev >= 0.3 else "LOW"

        fault_label = alert.get("fault_type", "unknown").replace("_", " ").title()

        dominant_str = ", ".join(
            f"{_CHANNEL_LABELS.get(ch, ch)} ({v:.3f})"
            for ch, v in alert.get("dominant_channels", [])
        ) or "—"

        tick = alert.get("tick", "—")
        try:
            ts_str = datetime.fromtimestamp(alert["timestamp"]).strftime("%H:%M:%S")
        except Exception:
            ts_str = f"T+{tick}"

        rows += f"""
<tr>
  <td style="padding:8px 12px; color:{_PAL['text']}; font-family:monospace;">{tick}</td>
  <td style="padding:8px 12px; color:{_PAL['text']};">{ts_str}</td>
  <td style="padding:8px 12px;">
    <span style="background:rgba(0,0,0,0.4); color:{sev_color}; font-size:0.72rem;
                 font-weight:700; padding:2px 8px; border-radius:4px;
                 border:1px solid {sev_color}40;">{sev_label}</span>
  </td>
  <td style="padding:8px 12px; color:{_PAL['title']}; font-weight:600;">{_html.escape(fault_label)}</td>
  <td style="padding:8px 12px; color:{_PAL['text']}; font-size:0.82rem;">{_html.escape(dominant_str)}</td>
  <td style="padding:8px 12px; color:{_PAL['blue']}; font-size:0.78rem;">{sev:.3f}</td>
</tr>"""

    return f"""
<table style="width:100%; border-collapse:collapse; background:rgba(0,0,0,0.2); border-radius:8px; overflow:hidden;">
  <thead>
    <tr style="background:rgba(59,130,246,0.12);">
      <th style="padding:10px 12px; text-align:left; color:{_PAL['blue']}; font-size:0.75rem; letter-spacing:0.08em;">TICK</th>
      <th style="padding:10px 12px; text-align:left; color:{_PAL['blue']}; font-size:0.75rem; letter-spacing:0.08em;">TIME</th>
      <th style="padding:10px 12px; text-align:left; color:{_PAL['blue']}; font-size:0.75rem; letter-spacing:0.08em;">SEV</th>
      <th style="padding:10px 12px; text-align:left; color:{_PAL['blue']}; font-size:0.75rem; letter-spacing:0.08em;">FAULT</th>
      <th style="padding:10px 12px; text-align:left; color:{_PAL['blue']}; font-size:0.75rem; letter-spacing:0.08em;">DOMINANT SENSORS</th>
      <th style="padding:10px 12px; text-align:left; color:{_PAL['blue']}; font-size:0.75rem; letter-spacing:0.08em;">SCORE</th>
    </tr>
  </thead>
  <tbody>{"".join(rows.split()[:0]) + rows}</tbody>
</table>"""


# ── Maintenance recommendations ───────────────────────────────────────────────

def _build_recommendations(alert_log: list[dict]) -> str:
    """Deduplicate fault labels and list all recommended actions."""
    from utils.mock_classification import _RECOMMENDATIONS, _LABEL_DISPLAY  # type: ignore

    seen_labels: dict[str, str] = {}
    for alert in alert_log:
        fault_key = alert.get("fault_type", "").replace(" ", "_").lower()
        if fault_key and fault_key not in seen_labels:
            action = _RECOMMENDATIONS.get(fault_key, _RECOMMENDATIONS.get("unknown", ""))
            seen_labels[fault_key] = action

    if not seen_labels:
        return f"""<p style="color:{_PAL['text']};">No maintenance actions required — engine operated within normal parameters.</p>"""

    items = ""
    for fk, action in seen_labels.items():
        label = _LABEL_DISPLAY.get(fk, fk.replace("_", " ").title())
        items += f"""
<div style="display:flex; gap:12px; align-items:flex-start; margin-bottom:10px;">
  <span style="color:{_PAL['amber']}; font-size:1rem; flex-shrink:0;">⚠</span>
  <div>
    <div style="color:{_PAL['title']}; font-weight:600; font-size:0.85rem;">{_html.escape(label)}</div>
    <div style="color:{_PAL['text']}; font-size:0.82rem; margin-top:2px;">{_html.escape(action)}</div>
  </div>
</div>"""
    return items


# ── Card helper ───────────────────────────────────────────────────────────────

def _card(title: str, body: str, accent: str = "#3b82f6") -> str:
    return f"""
<div style="background:{_PAL['card']}; border:1px solid {accent}30;
            border-radius:12px; padding:24px 28px; margin-bottom:24px;
            position:relative; overflow:hidden;">
  <div style="position:absolute; top:0; left:0; right:0; height:2px;
              background:linear-gradient(90deg,{accent},{accent}88);"></div>
  <div style="font-size:0.7rem; color:{accent}; letter-spacing:0.12em;
              text-transform:uppercase; font-weight:700; margin-bottom:14px;">
    {_html.escape(title)}
  </div>
  {body}
</div>"""


# ── Public API ────────────────────────────────────────────────────────────────

def generate_html_report(
    uav_id: str,
    mission_name: str,
    mode: str,
    composite_history: list[float],
    alert_log: list[dict],
    final_rul_payload: Optional[dict],
    active_fault_type: Optional[str],
    mission_profile: str,
    duration_ticks: int,
    mission_start_time: Optional[float] = None,
) -> str:
    """
    Build a self-contained HTML mission report.

    Parameters
    ----------
    uav_id              : UAV identifier string
    mission_name        : Mission name string
    mode                : "Live" or "Replay"
    composite_history   : List of composite_score floats (one per tick)
    alert_log           : Output of generate_mock_alert_log() — list of alert dicts
    final_rul_payload   : Last §2A dict from MockRULEstimator.estimate(), or None
    active_fault_type   : The fault type string that was active, or None
    mission_profile     : Selected mission profile string
    duration_ticks      : Total number of ticks simulated
    mission_start_time  : Unix timestamp for mission start (default = now)

    Returns
    -------
    str — complete, self-contained HTML document ready for download.
    """
    now_ts = mission_start_time or time.time()
    now_dt = datetime.fromtimestamp(now_ts)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Derived values ────────────────────────────────────────────────────────
    final_composite = composite_history[-1] if composite_history else 0.0
    final_health    = max(0.0, min(100.0, 100.0 - final_composite * 100.0))
    health_color    = _PAL["green"] if final_health >= 70 else _PAL["amber"] if final_health >= 40 else _PAL["red"]
    health_label    = "Healthy" if final_health >= 70 else "Caution" if final_health >= 40 else "FAULT"

    avg_composite   = sum(composite_history) / len(composite_history) if composite_history else 0.0
    peak_composite  = max(composite_history) if composite_history else 0.0

    fault_count     = len(alert_log)
    mode_badge_clr  = _PAL["green"] if mode == "Live" else _PAL["amber"]

    # ── RUL section ───────────────────────────────────────────────────────────
    if final_rul_payload:
        rul_h    = final_rul_payload.get("rul_hours", 0)
        rul_lo   = final_rul_payload.get("confidence_lower", rul_h)
        rul_hi   = final_rul_payload.get("confidence_upper", rul_h)
        rul_tnd  = final_rul_payload.get("trend", "stable")
        rul_col  = _PAL["green"] if rul_h > 150 else _PAL["amber"] if rul_h > 50 else _PAL["red"]
        arr, arr_clr = _TREND_ARROW.get(rul_tnd, ("→", _PAL["amber"]))
        rul_body = f"""
<div style="display:flex; gap:40px; align-items:center; flex-wrap:wrap;">
  <div style="text-align:center;">
    <div style="font-size:3rem; font-weight:800; color:{rul_col}; line-height:1;">
      {rul_h:.0f}
      <span style="font-size:1.5rem; color:{arr_clr};">{arr}</span>
    </div>
    <div style="font-size:0.75rem; color:{_PAL['text']}; margin-top:4px;">hours remaining</div>
  </div>
  <div>
    <div style="font-size:0.82rem; color:{_PAL['text']}; line-height:1.8;">
      <b style="color:{_PAL['title']};">90% CI:</b> {rul_lo:.0f} – {rul_hi:.0f} h<br>
      <b style="color:{_PAL['title']};">Trend:</b>
        <span style="color:{arr_clr};">{rul_tnd.title()} {arr}</span><br>
      <b style="color:{_PAL['title']};">Model:</b> {_html.escape(final_rul_payload.get('model_id','—'))}
    </div>
  </div>
</div>"""
    else:
        rul_body = f"<p style='color:{_PAL['text']};'>RUL data unavailable.</p>"

    # ── Spark-line SVG ────────────────────────────────────────────────────────
    sparkline = _build_sparkline_svg(composite_history) if composite_history else ""

    # ── Sections ──────────────────────────────────────────────────────────────
    header_body = f"""
<div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:20px; flex-wrap:wrap;">
  <div>
    <div style="font-size:0.68rem; color:{_PAL['text']}; letter-spacing:0.1em; text-transform:uppercase;">UAV ID</div>
    <div style="font-size:1.1rem; font-weight:700; color:{_PAL['title']};">{_html.escape(uav_id)}</div>
  </div>
  <div>
    <div style="font-size:0.68rem; color:{_PAL['text']}; letter-spacing:0.1em; text-transform:uppercase;">Mission</div>
    <div style="font-size:1.1rem; font-weight:700; color:{_PAL['title']};">{_html.escape(mission_name)}</div>
  </div>
  <div>
    <div style="font-size:0.68rem; color:{_PAL['text']}; letter-spacing:0.1em; text-transform:uppercase;">Date / Time</div>
    <div style="font-size:0.9rem; font-weight:600; color:{_PAL['title']};">{now_dt.strftime('%Y-%m-%d %H:%M')}</div>
  </div>
  <div>
    <div style="font-size:0.68rem; color:{_PAL['text']}; letter-spacing:0.1em; text-transform:uppercase;">Profile</div>
    <div style="font-size:0.9rem; color:{_PAL['title']};">{_html.escape(mission_profile)}</div>
  </div>
  <div>
    <div style="font-size:0.68rem; color:{_PAL['text']}; letter-spacing:0.1em; text-transform:uppercase;">Mode</div>
    <div style="font-size:0.9rem; font-weight:700; color:{mode_badge_clr};">{mode}</div>
  </div>
  <div>
    <div style="font-size:0.68rem; color:{_PAL['text']}; letter-spacing:0.1em; text-transform:uppercase;">Duration</div>
    <div style="font-size:0.9rem; color:{_PAL['title']};">{duration_ticks} ticks</div>
  </div>
</div>
<div style="display:flex; gap:24px; margin-top:20px; flex-wrap:wrap;">
  <div style="background:rgba(0,0,0,0.3); border-radius:8px; padding:14px 20px; text-align:center; min-width:120px;">
    <div style="font-size:0.65rem; color:{_PAL['text']}; text-transform:uppercase; letter-spacing:0.1em;">Final Health</div>
    <div style="font-size:2rem; font-weight:800; color:{health_color};">{final_health:.0f}%</div>
    <div style="font-size:0.7rem; color:{health_color};">{health_label}</div>
  </div>
  <div style="background:rgba(0,0,0,0.3); border-radius:8px; padding:14px 20px; text-align:center; min-width:120px;">
    <div style="font-size:0.65rem; color:{_PAL['text']}; text-transform:uppercase; letter-spacing:0.1em;">Peak Score</div>
    <div style="font-size:2rem; font-weight:800; color:{_PAL['red']};">{peak_composite:.3f}</div>
    <div style="font-size:0.7rem; color:{_PAL['text']};">composite max</div>
  </div>
  <div style="background:rgba(0,0,0,0.3); border-radius:8px; padding:14px 20px; text-align:center; min-width:120px;">
    <div style="font-size:0.65rem; color:{_PAL['text']}; text-transform:uppercase; letter-spacing:0.1em;">Avg Score</div>
    <div style="font-size:2rem; font-weight:800; color:{_PAL['amber']};">{avg_composite:.3f}</div>
    <div style="font-size:0.7rem; color:{_PAL['text']};">composite mean</div>
  </div>
  <div style="background:rgba(0,0,0,0.3); border-radius:8px; padding:14px 20px; text-align:center; min-width:120px;">
    <div style="font-size:0.65rem; color:{_PAL['text']}; text-transform:uppercase; letter-spacing:0.1em;">Fault Events</div>
    <div style="font-size:2rem; font-weight:800; color:{'#ef4444' if fault_count > 0 else '#10b981'};">{fault_count}</div>
    <div style="font-size:0.7rem; color:{_PAL['text']};">alert{'s' if fault_count != 1 else ''} logged</div>
  </div>
</div>"""

    health_trend_body = f"""
<p style="font-size:0.78rem; color:{_PAL['text']}; margin-bottom:10px;">
  Composite score over mission (higher = more degradation).
  <span style="color:{_PAL['green']};">■</span> Healthy (&lt;0.10) &nbsp;
  <span style="color:{_PAL['amber']};">■</span> Caution (0.10–0.35) &nbsp;
  <span style="color:{_PAL['red']};">■</span> Fault (&gt;0.35)
</p>
{sparkline}"""

    fault_table_body = _build_fault_table(alert_log)
    recommendations_body = _build_recommendations(alert_log)

    # ── Assemble final HTML ───────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Mission Report — {_html.escape(uav_id)} — {_html.escape(mission_name)}</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet"/>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', sans-serif;
      background: {_PAL['bg']};
      color: {_PAL['text']};
      padding: 32px;
      max-width: 960px;
      margin: 0 auto;
    }}
    h1 {{ color: {_PAL['title']}; font-size: 1.6rem; font-weight: 800; letter-spacing: 0.02em; }}
    table {{ border-spacing: 0; }}
    tr:nth-child(even) {{ background: rgba(255,255,255,0.02); }}
    @media print {{
      body {{ background: white; color: #333; max-width: 100%; padding: 16px; }}
    }}
  </style>
</head>
<body>

<!-- ── Report title bar ───────────────────────────────────────────────────── -->
<div style="background:linear-gradient(135deg,rgba(59,130,246,0.15),rgba(6,182,212,0.08));
            border:1px solid rgba(59,130,246,0.3); border-radius:14px;
            padding:24px 28px; margin-bottom:28px; position:relative; overflow:hidden;">
  <div style="position:absolute; top:0; left:0; right:0; height:3px;
              background:linear-gradient(90deg,#3b82f6,#06b6d4,#10b981);"></div>
  <div style="font-size:0.7rem; color:{_PAL['blue']}; letter-spacing:0.15em;
              text-transform:uppercase; font-weight:700; margin-bottom:6px;">
    DRDO · SIH26054 · Digital Twin Dashboard
  </div>
  <h1>🛩 Mission Report</h1>
  <div style="font-size:0.78rem; color:{_PAL['text']}; margin-top:6px;">
    Generated: {generated_at} &nbsp;·&nbsp; Source: M5 Dashboard
  </div>
</div>

{_card("01 — Mission Overview", header_body, _PAL['blue'])}
{_card("02 — Health Trend (composite_score / tick)", health_trend_body, _PAL['cyan'])}
{_card("03 — Fault Event Log", fault_table_body, _PAL['red'])}
{_card("04 — Final RUL Estimate (§2A)", rul_body, _PAL['green'])}
{_card("05 — Maintenance Recommendations", recommendations_body, _PAL['amber'])}

<div style="margin-top:28px; font-size:0.72rem; color:rgba(148,163,184,0.5);
            text-align:center; border-top:1px solid rgba(59,130,246,0.1); padding-top:16px;">
  DRDO AI-Enabled Digital Twin for MALE UAV Aero Piston Engine · SIH26054 · M5 Dashboard
  &nbsp;·&nbsp; Report generated {generated_at}
</div>

</body>
</html>"""
