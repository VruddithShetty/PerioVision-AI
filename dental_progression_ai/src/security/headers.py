import streamlit as st

def inject_security_headers():
    """
    Injects HTTP-equivalent security headers and UI-level protection scripts.
    """
    # UI Protection removed as it is merely security theater.
    # True data protection is handled by server-side RBAC and encryption.

    # Security Meta Tags
    headers_html = """
    <head>
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data:; font-src 'self' https://fonts.gstatic.com; frame-ancestors 'none';">
    <meta http-equiv="X-Frame-Options" content="DENY">
    <meta http-equiv="X-Content-Type-Options" content="nosniff">
    <meta http-equiv="Referrer-Policy" content="strict-origin-when-cross-origin">
    </head>
    """
    st.markdown(headers_html, unsafe_allow_html=True)

    # Hide Streamlit UI elements
    st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)
