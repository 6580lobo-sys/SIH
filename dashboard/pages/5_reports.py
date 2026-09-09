"""
pages/5_reports.py — Reports (stub + download)
===============================================
UAV Engine Twin · DRDO SIH26054
"""

import datetime
import streamlit as st
from utils.styles import inject_global_styles, render_mission_header, render_sidebar_nav, render_page_title, section_title
from utils.session import init_session, get
from utils.connector import get_engine

st.set_page_config(page_title="Reports — UAV Engine Twin", page_icon="📋", layout="wide")
init_session()
inject_global_styles()

with st.sidebar:
    render_sidebar_nav(active="reports")

mode = get("mode")
render_mission_header(mode=mode, mission_id="ISR-042")
render_page_title("Reports", "Generate and download mission health reports")

section_title("📥 REPORT GENERATION")

col1, col2 = st.columns([1.4, 1], gap="large")

with col1:
    st.markdown("""
    <div class="dt-card" style="padding:24px;">
        <div style="font-size:0.68rem; font-weight:700; letter-spacing:0.14em; color:#4b5e7a;
                    text-transform:uppercase; margin-bottom:16px;">Report Configuration</div>
    """, unsafe_allow_html=True)

    uav_id_in  = st.text_input("UAV ID",       value=get("uav_id")       or "UAV-07",   key="rpt_uav")
    mission_in = st.text_input("Mission Name", value=get("mission_name") or "ISR-042",  key="rpt_mission")
    rpt_type   = st.selectbox("Report Type", [
        "Full Mission Report",
        "Engine Health Summary",
        "Fault Incident Report",
        "RUL Trend Analysis",
    ], key="rpt_type")

    st.markdown("</div>", unsafe_allow_html=True)

    if st.button("📥 Generate Report →", key="rpt_gen", type="primary", use_container_width=True):
        try:
            from utils.report import generate_html_report
            engine = get_engine(mode=mode)
            report_html = generate_html_report(
                uav_id=uav_id_in,
                mission_name=mission_in,
                mode=mode,
                tick_history=[],
                rul_history=[],
                classification_history=[],
                alerts=[],
            )
            ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                label="📄 Download HTML Report",
                data=report_html,
                file_name=f"uav_report_{ts}.html",
                mime="text/html",
                key="rpt_download",
            )
            st.success("✅ Report generated successfully!")
        except Exception as e:
            st.error(f"Report generation error: {e}")

with col2:
    st.markdown("""
    <div class="dt-card" style="padding:20px;">
        <div style="font-size:0.68rem; font-weight:700; letter-spacing:0.14em; color:#4b5e7a;
                    text-transform:uppercase; margin-bottom:14px;">Report Contents</div>
        <div style="font-size:0.8rem; color:#94a3b8; line-height:2.0;">
            ✅ &nbsp; Mission metadata (UAV ID, dates)<br>
            ✅ &nbsp; Engine health timeline<br>
            ✅ &nbsp; RUL trend & confidence bounds<br>
            ✅ &nbsp; Fault events & classification<br>
            ✅ &nbsp; Dominant channel evidence<br>
            ✅ &nbsp; Maintenance recommendations<br>
            ✅ &nbsp; Digital twin residual analysis
        </div>
    </div>
    """, unsafe_allow_html=True)
