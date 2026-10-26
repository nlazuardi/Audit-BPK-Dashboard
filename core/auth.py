"""Gerbang password bersama. Password disimpan di secrets.toml sebagai APP_PASSWORD."""
import hmac

import streamlit as st


def cek_password() -> bool:
    if st.session_state.get("masuk"):
        return True
    if "APP_PASSWORD" not in st.secrets:
        st.error("APP_PASSWORD belum diisi di secrets.toml, jadi dashboard dikunci.")
        return False

    st.markdown("### Monitoring Audit BPK")
    with st.form("login"):
        pw = st.text_input("Password", type="password")
        kirim = st.form_submit_button("Masuk")
    if kirim:
        if hmac.compare_digest(pw.encode(), str(st.secrets["APP_PASSWORD"]).encode()):
            st.session_state["masuk"] = True
            st.rerun()
        st.error("Password salah")
    return False
