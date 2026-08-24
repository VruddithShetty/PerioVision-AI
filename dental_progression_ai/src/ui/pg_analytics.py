import streamlit as st
from ui.styles import page_header

def render_analytics(doctor):
    st.markdown(page_header("📊 Clinical Analytics", "AI-driven progression insights"), unsafe_allow_html=True)
    st.info("Select a patient to view longitudinal bone loss trends.")
