"""
pages/6_settings.py — Settings
================================
UAV Engine Twin · DRDO SIH26054
"""

import streamlit as st
from utils.styles import inject_global_styles, render_mission_header, render_sidebar_nav, render_page_title, section_title
from utils.session import init_session, get, set_val

st.set_page_config(page_title="Settings — UAV Engine Twin", page_icon="⚙️", layout="wide")
init_session()
inject_global_styles()

with st.sidebar:
    render_sidebar_nav(active="settings")

render_mission_header(mode=get("mode"), mission_id="ISR-042")
render_page_title("Settings", "System configuration, UAV identity, and data source settings")

col1, col2 = st.columns(2, gap="large")

with col1:
    section_title("✈️ UAV IDENTITY")
    st.markdown('<div class="dt-card" style="padding:20px;">', unsafe_allow_html=True)
    uav_id = st.text_input("UAV ID",       value=get("uav_id"),       key="settings_uav_id")
    mission = st.text_input("Mission Name", value=get("mission_name"), key="settings_mission")
    set_val("uav_id",      uav_id)
    set_val("mission_name", mission)

    st.markdown('<div style="margin-top:10px;"></div>', unsafe_allow_html=True)
    section_title("⚡ DATA SOURCE")
    mode = st.radio("Source Mode", ["Live", "Replay"],
                    index=0 if get("mode") == "Live" else 1, key="settings_mode")
    set_val("mode", mode)

    if mode == "Replay":
        replay_file = st.file_uploader("Upload Mission Log CSV", type=["csv"], key="settings_replay")
        if replay_file:
            set_val("replay_file", replay_file)
            st.success(f"✅ Loaded: `{replay_file.name}`")

    st.markdown("</div>", unsafe_allow_html=True)

    if st.button("🔄 Reset All Engine State", key="settings_reset", use_container_width=True):
        for key in ["overview_engine", "dt_engine", "telem_engine", "diag_engine",
                    "ov_history", "dt_history", "telem_history", "diag_history"]:
            if key in st.session_state:
                del st.session_state[key]
        st.success("✅ All engine state cleared. Navigate to any page to restart.")

with col2:
    section_title("🎯 MISSION PROFILE")
    st.markdown('<div class="dt-card" style="padding:20px;">', unsafe_allow_html=True)
    profile = st.selectbox("Profile", [
        "ISR Patrol", "Long-Endurance Transit",
        "High-Altitude Loiter", "Combat Air Patrol",
    ], key="settings_profile")
    set_val("mission_profile", profile)

    st.markdown('<div style="margin-top:16px;"></div>', unsafe_allow_html=True)
    section_title("🌍 ENVIRONMENT SCENARIO")
    altitude = st.slider("Altitude (m)", 0, 8000, 1000, 100, key="settings_alt")
    temp     = st.slider("Ambient Temp (°C)", -20, 50, 25, 1, key="settings_temp")
    throttle = st.slider("Throttle Demand (%)", 30, 100, 70, 5, key="settings_throttle")

    set_val("op_scenario_params", {
        "altitude_m":           altitude,
        "ambient_temp_c":       temp,
        "throttle_demand_pct":  throttle,
    })

    st.markdown("</div>", unsafe_allow_html=True)

    section_title("ℹ️ SYSTEM INFO")
    st.markdown("""
    <div class="dt-card" style="padding:16px;">
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:0.75rem;">
            <div style="color:#64748b;">Dashboard Version</div>
            <div style="color:#93c5fd; font-family:monospace;">v2.0 · SIH26054</div>
            <div style="color:#64748b;">Engine Model</div>
            <div style="color:#93c5fd; font-family:monospace;">MALE UAV Piston</div>
            <div style="color:#64748b;">AI Model</div>
            <div style="color:#93c5fd; font-family:monospace;">mock_ensemble_v1</div>
            <div style="color:#64748b;">Organisation</div>
            <div style="color:#93c5fd; font-family:monospace;">DRDO · M4 Team</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
