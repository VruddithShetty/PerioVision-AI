"""Login and Register screens — premium design."""
import sys as _sys, os as _os
_wd = _os.path.dirname(_os.path.abspath(__file__))
for _p in [_os.path.dirname(_wd), _wd]:
    if _p not in _sys.path: _sys.path.insert(0, _p)

import streamlit as st


def render_login(doctor_mgr, audit_log):
    # Centered 3D Card layout
    st.markdown("""
    <div style="height:10vh"></div>
    """, unsafe_allow_html=True)

    left, center, right = st.columns([1, 1.8, 1])
    with center:
        # Glassmorphic Login Panel
        st.markdown("""
        <div style="
            background: var(--glass-bg);
            backdrop-filter: blur(25px) saturate(200%);
            border-radius: var(--radius-lg);
            padding: 50px 40px;
            border: 1px solid var(--glass-border);
            box-shadow: 0 30px 60px rgba(0,0,0,0.6);
            text-align: center;
            position: relative;
            overflow: hidden;
        ">
            <div style="position:absolute; top:0; left:0; right:0; height:4px; background:var(--accent);"></div>
            <div style="
                width: 100px; height: 100px;
                background: var(--accent);
                border-radius: 24px;
                display: inline-flex; align-items: center; justify-content: center;
                font-size: 3rem;
                margin-bottom: 24px;
                box-shadow: var(--accent-glow);
                transform: rotate(-5deg);
            ">🔑</div>
            <h1 style="margin:0 0 10px; font-size:2.8rem !important; letter-spacing: -1.5px;">Quantum <span style="color:var(--neon-blue); -webkit-text-fill-color: var(--neon-blue);">Access</span></h1>
            <p style="color:var(--text-muted); font-weight:500; font-size:1rem; margin-bottom:30px;">Initialize PerioVision AI Neural Core</p>
        </div>
        """, unsafe_allow_html=True)

        # Input Fields
        st.text_input("📧 NEURAL ID (Email)", placeholder="doctor@clinical.ai", key="login_email")
        st.text_input("🔐 SECURITY KEY (Password)", type="password", key="login_pass")
        st.markdown("<div style='height:15px'></div>", unsafe_allow_html=True)
        
        # Using columns for the submit button to center it
        _, b_col, _ = st.columns([1, 2, 1])
        with b_col:
            login_btn = st.button("ENTER SYSTEM", use_container_width=True, type="primary")

        if login_btn:
            # Safely get values from session state
            email = st.session_state.get("login_email", "")
            password = st.session_state.get("login_pass", "")
            
            if email and password:
                doctor = doctor_mgr.authenticate(email, password)
                if doctor:
                    if doctor.get("totp_enabled"):
                        st.session_state.pending_2fa = doctor
                        st.session_state.auth_mode = "2fa"
                        st.rerun()
                    else:
                        st.session_state.logged_in = True
                        st.session_state.doctor = doctor
                        audit_log.log(doctor["doctor_id"], "LOGIN", f"Dr. {doctor['name']} entry")
                        st.rerun()
                else:
                    st.error("ACCESS DENIED: Credentials Invalid")
            else:
                st.warning("FIELD REQUIREMENT: Neural ID and Security Key are mandatory")

        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
        st.write("---")
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("NEW ACCOUNT", use_container_width=True, type="secondary"):
                st.session_state.auth_mode = "register"
                st.rerun()
        with c2:
            st.button("RECOVERY", use_container_width=True, type="secondary", disabled=True)


def render_register(doctor_mgr):
    st.markdown("<div style='height:5vh'></div>", unsafe_allow_html=True)
    _, col, _ = st.columns([0.6, 2, 0.6])
    with col:
        st.markdown("""
        <div style="background:var(--glass-bg); padding:40px; border-radius:var(--radius-lg); border:1px solid var(--glass-border); box-shadow:0 30px 60px rgba(0,0,0,0.6);">
            <h2 style="margin:0 0 20px; text-align:center;">Register <span style="color:var(--neon-purple); -webkit-text-fill-color: var(--neon-purple);">New Provider</span></h2>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("#### 🛸 PERSONAL METRICS")
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("FULL LEGAL NAME", key="reg_name")
            email = st.text_input("ENCRYPTION ID (Email)", key="reg_email")
            lic_no = st.text_input("LICENSE AUTH", key="reg_lic")
        with c2:
            clinic = st.text_input("CLINIC/VAULT NAME", key="reg_clinic")
            city = st.text_input("HQ CITY", key="reg_city")
            pwd = st.text_input("PASSWORD", type="password", key="reg_pwd")
        
        st.markdown("<br>", unsafe_allow_html=True)
        reg_btn = st.button("INITIALIZE ACCOUNT", use_container_width=True, type="primary")

        if reg_btn:
            if all([name, email, pwd, lic_no]):
                new_id = doctor_mgr.get_next_doctor_id()
                doctor_mgr.register_doctor(new_id, name, email, pwd, lic_no, clinic, city)
                st.success("PROTOCOL INITIALIZED. PLEASE SIGN IN.")
                st.session_state.auth_mode = "login"
                st.rerun()
            else:
                st.error("MISSING PARAMS: Ensure all mandatory metrics are entered.")

        if st.button("RETURN TO ACCESS", type="secondary", use_container_width=True):
            st.session_state.auth_mode = "login"
            st.rerun()


def render_2fa(doctor_mgr, audit_log):
    doctor = st.session_state.get("pending_2fa", {})
    st.markdown("<div style='height:10vh'></div>", unsafe_allow_html=True)
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown(f"""
        <div style="background:var(--glass-bg); padding:50px 40px; border-radius:var(--radius-lg); border:1px solid var(--glass-border); box-shadow:0 30px 60px rgba(0,0,0,0.6); text-align:center;">
            <div style="font-size:3.5rem; margin-bottom:20px;">🛡️</div>
            <h2 style="margin:0 0 10px;">Quantum <span style="color:var(--neon-purple); -webkit-text-fill-color: var(--neon-purple);">Verification</span></h2>
            <p style="color:var(--text-muted); margin-bottom:30px;">Initialize biometric handshake (Enter 6-digit TOTP)</p>
        </div>
        """, unsafe_allow_html=True)

        with st.form("totp_form"):
            code = st.text_input("🔢 NEURAL CODE (6-Digits)", max_chars=6, placeholder="000000")
            verify_btn = st.form_submit_button("VALIDATE & ENTER", use_container_width=True)

        if verify_btn:
            if doctor_mgr.verify_totp(doctor["doctor_id"], code):
                st.session_state.logged_in = True
                st.session_state.doctor = doctor
                st.session_state.pop("pending_2fa", None)
                audit_log.log(doctor["doctor_id"], "2FA_SUCCESS", "Handshake accepted")
                st.rerun()
            else:
                st.error("HANDSHAKE REJECTED: Invalid Code")

        if st.button("← ABORT TO ACCESS", type="secondary", use_container_width=True):
            st.session_state.auth_mode = "login"
            st.session_state.pop("pending_2fa", None)
            st.rerun()
