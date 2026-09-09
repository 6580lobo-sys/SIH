"""
pages/4_simulation_lab.py — Simulation Lab (stub)
==================================================
UAV Engine Twin · DRDO SIH26054
"""

import streamlit as st
from utils.styles import inject_global_styles, render_mission_header, render_sidebar_nav, render_page_title
from utils.session import init_session, get

st.set_page_config(page_title="Simulation Lab — UAV Engine Twin", page_icon="🔬", layout="wide")
init_session()
inject_global_styles()

with st.sidebar:
    render_sidebar_nav(active="simulation")

render_mission_header(mode=get("mode"), mission_id="ISR-042")
render_page_title("Simulation Lab", "Scenario-based engine simulation and fault injection experiments")

st.markdown("""
<div style="display:flex; flex-direction:column; align-items:center; justify-content:center;
            padding:80px 40px; text-align:center;">
    <div style="font-size:4rem; margin-bottom:20px; opacity:0.4;">🔬</div>
    <div style="font-size:1.4rem; font-weight:700; color:#f1f5f9; margin-bottom:10px;">
        Simulation Lab
    </div>
    <div style="font-size:0.9rem; color:#4b5e7a; max-width:480px; line-height:1.7; margin-bottom:28px;">
        Run controlled fault injection experiments, compare degradation scenarios,
        and validate prognostics models in a safe offline environment.
    </div>
    <div style="display:flex; gap:12px; flex-wrap:wrap; justify-content:center;">
        <div style="background:rgba(59,130,246,0.08); border:1px solid rgba(59,130,246,0.2);
                    border-radius:8px; padding:14px 24px; min-width:160px;">
            <div style="font-size:0.65rem; color:#64748b; font-weight:700; letter-spacing:0.12em;
                        text-transform:uppercase; margin-bottom:6px;">Planned Features</div>
            <div style="font-size:0.8rem; color:#94a3b8; line-height:1.8;">
                • Monte Carlo fault simulation<br>
                • RUL prediction comparison<br>
                • Degradation scenario builder<br>
                • Batch mission replay
            </div>
        </div>
    </div>
    <div style="margin-top:32px; padding:10px 20px; background:rgba(6,182,212,0.08);
                border:1px solid rgba(6,182,212,0.2); border-radius:6px;">
        <span style="font-size:0.78rem; color:#06b6d4; font-weight:600; letter-spacing:0.08em;">
            🚀 COMING IN NEXT FIRMWARE UPDATE
        </span>
    </div>
</div>
""", unsafe_allow_html=True)
