"""
Session-state helpers.

Streamlit re-runs the script on every interaction. Session state is the
canonical place to keep values that need to persist across reruns.
"""

import streamlit as st


def init_session() -> None:
    """Initialise default session-state keys if they don't already exist."""
    defaults = {
        "user_type": None,         # "policy_maker" or "mnc"
        "user_type_label": None,   # display name, e.g. "Policy Maker"
        "supply_chain": None,      # populated by P-02
        "session_id": None,        # random id for the demo (no real auth)
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


def set_user_type(user_type: str, label: str) -> None:
    """Set the user type and a fresh session id."""
    import uuid

    st.session_state.user_type = user_type
    st.session_state.user_type_label = label
    st.session_state.session_id = str(uuid.uuid4())[:8]


def sign_out() -> None:
    """Clear session state — returns the user to the landing page."""
    st.session_state.clear()
    init_session()


def require_user_type():
    """Guard for inner pages — bounce to landing if no user type is set."""
    if st.session_state.get("user_type") is None:
        st.warning("Please pick a user type on the landing page first.")
        st.page_link("app.py", label="← Back to landing", icon="🏠")
        st.stop()
