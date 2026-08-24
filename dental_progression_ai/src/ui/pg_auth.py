import re
import os
import io
import base64
import datetime
import jwt
import qrcode
import streamlit as st
from database.doctors import DoctorManager
from database.connection import db
from security.session import SessionSecurityManager

# Initialize Managers
doctor_mgr = DoctorManager()
session_sec = SessionSecurityManager()

# Load secret key for JWT
SECRET_KEY = os.environ.get("SECRET_KEY", "periovision_default_secure_secret_key_32_bytes_!!!!!")

def generate_jwt(doctor):
    payload = {
        "doctor_id": str(doctor["doctor_id"]),
        "email": doctor["email"],
        "role": doctor.get("role", "doctor"),
        "iat": datetime.datetime.now(datetime.timezone.utc),
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=30)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def generate_refresh_token(doctor):
    payload = {
        "doctor_id": str(doctor["doctor_id"]),
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7),
        "type": "refresh"
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    db["refresh_tokens"].insert_one({
        "token": token,
        "doctor_id": str(doctor["doctor_id"]),
        "used": False,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    })
    return token

def require_auth():
    if "token" not in st.session_state or "doctor" not in st.session_state:
        st.session_state.logged_in = False
        st.rerun()

def render_login():
    st.markdown("<h2 style='text-align: center;'>🔐 Clinical Login</h2>", unsafe_allow_html=True)
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign In", use_container_width=True):
            try:
                doctor = doctor_mgr.authenticate_doctor(email, password)
                if doctor:
                    st.session_state.doctor = doctor
                    st.session_state.token = generate_jwt(doctor)
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("Invalid credentials")
            except Exception as e:
                st.error(str(e))

def render_register():
    st.markdown("<h2 style='text-align: center;'>🏥 Register Clinical Account</h2>", unsafe_allow_html=True)
    with st.form("reg_form"):
        name = st.text_input("Full Name")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Create Account", use_container_width=True):
            try:
                doctor_mgr.register_doctor(name, email, password)
                st.success("Registration successful! Please login.")
            except Exception as e:
                st.error(str(e))
