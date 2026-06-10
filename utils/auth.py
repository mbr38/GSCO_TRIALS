"""
Lightweight password gate for the deployed demo.

The gate is **opt-in via secrets**: it only activates when an `APP_PASSWORD`
secret is present (as it will be on Streamlit Community Cloud). Locally there is
normally no secrets file, so `require_password()` is a no-op and the existing
local run experience is unchanged.

This is a simple shared-password gate suitable for gating a demo and its Earth
Engine quota — not a real user-authentication system.
"""

import hmac
import streamlit as st


def _configured_password():
    """Return the configured APP_PASSWORD, or None if no secret is set.

    Reads defensively so a missing local secrets file means "no gate".
    """
    try:
        if "APP_PASSWORD" in st.secrets:
            return st.secrets["APP_PASSWORD"]
    except Exception:
        return None
    return None


def require_password() -> None:
    """Block the app until the correct password is entered.

    No-op when `APP_PASSWORD` is not configured (i.e. local development).
    Call once at the top of the entry point, before rendering pages.
    """
    password = _configured_password()
    if not password:
        return  # gate disabled (local dev / no secret configured)

    if st.session_state.get("_password_ok"):
        return  # already unlocked this session

    st.title("GSCO Environmental Decision-Support Demo")
    st.caption("This demo is password protected.")

    entered = st.text_input("Password", type="password")
    if entered:
        # Constant-time comparison to avoid leaking length/prefix via timing.
        if hmac.compare_digest(str(entered), str(password)):
            st.session_state["_password_ok"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.stop()
