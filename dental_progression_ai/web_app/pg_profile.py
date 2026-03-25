"""My Profile page with 2FA setup (Google Authenticator compatible)."""
import sys as _sys, os as _os
_wd = _os.path.dirname(_os.path.abspath(__file__))
for _p in [_os.path.dirname(_wd), _wd]:
    if _p not in _sys.path: _sys.path.insert(0, _p)
import streamlit as st
import pyotp
import qrcode
from io import BytesIO
from PIL import Image
from ui_styles import page_header


def render_profile(doctor, doctor_mgr, audit_log):
    st.markdown(page_header("⚙️ My Profile", "Manage your account and security settings"), unsafe_allow_html=True)

    curr = doctor_mgr.get_doctor(doctor["doctor_id"]) or doctor

    tab_info, tab_2fa = st.tabs(["👨‍⚕️ Account Details", "🔐 Two-Factor Auth (Google Authenticator)"])

    with tab_info:
        with st.container(border=True):
            c1, c2 = st.columns(2)
            with c1:
                st.metric("Full Name",      curr.get("name", "—"))
                st.metric("Email",          curr.get("email", "—"))
                st.metric("Doctor ID",      str(curr.get("doctor_id", "—")))
                st.metric("Role",           curr.get("role", "doctor").capitalize())
            with c2:
                st.metric("License No.",    curr.get("license_number", "—"))
                st.metric("Clinic",         curr.get("clinic") or "Not set")
                st.metric("City",           curr.get("city") or "Not set")
                st.metric("Member Since",   curr.get("created_date", "—"))
            st.metric("Last Login",         curr.get("last_login", "—"))

        st.markdown("---")
        with st.container(border=True):
            st.markdown("#### ✏️ Update Profile")
            with st.form("profile_form"):
                up_name   = st.text_input("Full Name",   value=curr.get("name", ""))
                up_clinic = st.text_input("Clinic Name", value=curr.get("clinic") or "")
                up_city   = st.text_input("City",        value=curr.get("city") or "")
                if st.form_submit_button("💾 Save Changes", use_container_width=True):
                    doctor_mgr.update_profile(doctor["doctor_id"], name=up_name, clinic=up_clinic, city=up_city)
                    st.session_state.doctor["name"]   = up_name
                    st.session_state.doctor["clinic"] = up_clinic
                    st.session_state.doctor["city"]   = up_city
                    audit_log.log(doctor["doctor_id"], "PROFILE_UPDATE", "Doctor updated profile")
                    st.success("✅ Profile updated!")
                    st.rerun()

    with tab_2fa:
        st.markdown("""
        <div style="background:rgba(56, 189, 248, 0.1); border-left:4px solid var(--neon-blue); border-radius:0 12px 12px 0; padding:20px; margin-bottom:24px; backdrop-filter:blur(10px);">
            <div style="color:var(--neon-blue); font-weight:700; font-size:1.1rem; margin-bottom:8px;">🔐 Quantum Security (2FA)</div>
            <div style="font-size:0.95rem; color:var(--text-muted); line-height:1.5;">
                Enhance your account security with Time-based One-Time Passwords. 
                Compatible with <b>Google Authenticator</b>, Authy, and Microsoft Authenticator.
            </div>
        </div>""", unsafe_allow_html=True)

        is_enabled = curr.get("totp_enabled", False)
        has_secret = curr.get("totp_secret") is not None

        if is_enabled:
            st.success("✅ Two-Factor Authentication is **ACTIVE** on your account.")
            if st.button("🗑️ Disable 2FA", type="secondary", use_container_width=True, key="disable_2fa"):
                doctor_mgr.disable_totp(doctor["doctor_id"])
                audit_log.log(doctor["doctor_id"], "2FA_DISABLED", "Doctor disabled 2FA", level="WARNING")
                st.warning("⚠️ 2FA has been disabled. Your account is less secure.")
                st.rerun()
        else:
            if not has_secret:
                if st.button("🔐 Set Up Google Authenticator", use_container_width=True, key="setup_2fa"):
                    secret = doctor_mgr.generate_totp_secret(doctor["doctor_id"])
                    st.session_state["totp_setup_secret"] = secret
                    st.rerun()

            secret = st.session_state.get("totp_setup_secret") or curr.get("totp_secret")
            if secret and not is_enabled:
                uri = pyotp.TOTP(secret).provisioning_uri(
                    name=curr.get("email", "doctor"), issuer_name="PerioVision AI")

                # Generate QR code
                qr = qrcode.make(uri)
                buf = BytesIO()
                qr.save(buf, format="PNG")
                buf.seek(0)

                st.markdown("#### 📱 Scan this QR Code")
                _, qc, _ = st.columns([1, 1.2, 1])
                with qc:
                    st.image(buf, caption="Scan with Google Authenticator / Authy", use_container_width=True)

                with st.expander("🔑 Manual Entry Key (if QR scan fails)"):
                    st.code(secret, language=None)
                    st.caption("Enter this key manually in your authenticator app.")

                st.markdown("#### ✅ Verify & Activate")
                with st.form("verify_2fa_form"):
                    code = st.text_input("Enter the 6-digit code from your app", max_chars=6, placeholder="000000")
                    verified = st.form_submit_button("✅ Activate 2FA", use_container_width=True)

                if verified:
                    totp = pyotp.TOTP(secret)
                    if totp.verify(code, valid_window=1):
                        doctor_mgr.enable_totp(doctor["doctor_id"])
                        st.session_state.pop("totp_setup_secret", None)
                        audit_log.log(doctor["doctor_id"], "2FA_ENABLED", "Doctor activated 2FA")
                        st.success("🎉 Two-Factor Authentication is now ACTIVE!")
                        st.rerun()
                    else:
                        st.error("❌ Invalid code. Make sure your device time is synced and try again.")
