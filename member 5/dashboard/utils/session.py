"""
utils/session.py
----------------
Centralised Streamlit session-state initialisation and accessors.
All pages call init_session() on load to ensure keys exist.
"""

import streamlit as st

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULTS = {
    # Identity
    "uav_id": "UAV-DRDO-001",
    "mission_name": "OPERATION SKYWATCH",

    # Source mode: "Live" | "Replay"
    "mode": "Live",

    # Replay file path (set when user uploads a CSV)
    "replay_file": None,

    # Running flag — controls tick loop in Live mode
    "running": False,

    # Per-tick history accumulator (list of residual dicts)
    "tick_history": [],

    # Latest payloads from M1 (populated by the data connector)
    "latest_residual": None,       # {timestamp, residuals, composite_score}
    "latest_signature": None,      # {feature_vector, dominant_channels, severity, fault_detected}
    "latest_predicted": None,      # {timestamp, rpm, cht, ...}
    "latest_actual": None,         # {timestamp, rpm, cht, ...}

    # Latest RUL from M2 (separate stream — data contract §2A)
    "latest_rul": None,            # full §2A dict or None
    "rul_history": [],             # list of §2A dicts (for trend chart)

    # Latest fault classification from M3/M4 (data contract §4A)
    "latest_classification": None, # full §4A dict or None
    "classification_history": [],  # list of §4A dicts (for alert panel)

    # Alert log
    "alerts": [],                  # list of alert dicts

    # Mission profile selection (for USP #2 scoring)
    "mission_profile": "ISR Patrol",

    # Block E — Environmental scenario parameters (Operator View sliders)
    "op_scenario_params": {
        "altitude_m":          1000,
        "ambient_temp_c":      25,
        "throttle_demand_pct": 70,
    },

    # Mission timing (for report generation — Step 13)
    "mission_start_time": None,  # set when engine first runs
    "replay_finished":    False,    # True after Replay-mode session ends

    # Per-tick records for history trend view (Step 15)
    # List of {tick, composite_score, health_pct, rul_hours, ci_lo, ci_hi, fault_active}
    "trend_df_records": [],
}


def init_session():
    """Ensure all session keys exist with their defaults. Safe to call multiple times."""
    for key, value in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value


def get(key: str):
    return st.session_state.get(key, DEFAULTS.get(key))


def set_val(key: str, value):
    st.session_state[key] = value


def push_tick(residual_dict: dict):
    """Append a residual tick to history (capped at 500 for memory)."""
    hist = st.session_state.get("tick_history", [])
    hist.append(residual_dict)
    if len(hist) > 500:
        hist = hist[-500:]
    st.session_state["tick_history"] = hist


def push_alert(alert_dict: dict):
    """Append a new alert entry."""
    alerts = st.session_state.get("alerts", [])
    alerts.insert(0, alert_dict)          # newest first
    if len(alerts) > 100:
        alerts = alerts[:100]
    st.session_state["alerts"] = alerts


def push_rul(rul_dict: dict):
    """Append a full §2A RUL payload to history (capped at 500)."""
    hist = st.session_state.get("rul_history", [])
    hist.append(rul_dict)
    if len(hist) > 500:
        hist = hist[-500:]
    st.session_state["rul_history"] = hist
    st.session_state["latest_rul"] = rul_dict


def push_classification(cls_dict: dict):
    """Append a §4A classification payload to history (capped at 100, deduped by fault_id)."""
    hist = st.session_state.get("classification_history", [])
    # Dedup: if the last entry has the same fault_id, update it instead of appending
    if hist and hist[0].get("fault_id") == cls_dict.get("fault_id"):
        hist[0] = cls_dict
    else:
        hist.insert(0, cls_dict)  # newest first
    if len(hist) > 100:
        hist = hist[:100]
    st.session_state["classification_history"] = hist
    st.session_state["latest_classification"] = cls_dict


def clear_session_data():
    """Reset all live data accumulators (keep identity + mode settings)."""
    st.session_state["tick_history"] = []
    st.session_state["alerts"] = []
    st.session_state["rul_history"] = []
    st.session_state["classification_history"] = []
    st.session_state["latest_residual"] = None
    st.session_state["latest_signature"] = None
    st.session_state["latest_predicted"] = None
    st.session_state["latest_actual"] = None
    st.session_state["latest_rul"] = None
    st.session_state["latest_classification"] = None
    st.session_state["running"] = False

