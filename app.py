"""
GSCO Demo — Entry point (P-01 Landing).

Run with: streamlit run app.py
"""

import streamlit as st

from demo.saved_analyses import seed_saved_analyses
from utils.state import init_session, set_user_type

# ----------------------------------------------------------------------------
# Page config — must be the first Streamlit call.
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="GSCO Environmental Tool",
    page_icon="🌍",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Initialise session state on first run.
init_session()

# M-P10 — seed demo saves on cold session entry. Idempotent; no-op once
# the list has any entries (whether seeded or user-added).
seed_saved_analyses(st.session_state)

# ----------------------------------------------------------------------------
# If a user type is already set (e.g. user came back), offer to continue.
# ----------------------------------------------------------------------------
if st.session_state.user_type is not None:
    st.success(
        f"You are currently signed in as **{st.session_state.user_type_label}**."
    )
    col_continue, col_switch = st.columns(2)
    with col_continue:
        if st.button("Continue to scope set-up", type="primary", use_container_width=True):
            st.switch_page("pages/02_Scope_Setup.py")  # M-P02-POLISH
    with col_switch:
        if st.button("Sign out and start over", use_container_width=True):
            st.session_state.clear()
            init_session()
            st.rerun()
    st.stop()

# ----------------------------------------------------------------------------
# P-01 — User-type selection (State S1).
# ----------------------------------------------------------------------------
st.title("GSCO Environmental Monitoring & Decision-Support Tool")

st.markdown(
    """
    A geospatial decision-support tool for monitoring environmental conditions
    across supply chains. Built on Earth Engine, designed for two audiences.
    """
)

st.divider()

st.subheader("Who's using the tool today?")
st.caption("Pick the role that matches what you're doing in this session.")

# Two user-type cards rendered as side-by-side columns.
col_policy, col_mnc = st.columns(2, gap="medium")

with col_policy:
    with st.container(border=True):
        st.markdown("### Policy Maker")
        st.markdown(
            """
            Monitor environmental conditions across regions and named supply chains.
            Connect to the GSCO catalogue or upload your own regions.
            """
        )
        policy_selected = st.button(
            "Continue as Policy Maker",
            key="btn_policy",
            type="primary",
            use_container_width=True,
        )

with col_mnc:
    with st.container(border=True):
        st.markdown("### MNC")
        st.markdown(
            """
            Screen and prioritise environmental conditions across your suppliers.
            Upload your supplier list and run targeted analyses.
            """
        )
        mnc_selected = st.button(
            "Continue as MNC",
            key="btn_mnc",
            type="primary",
            use_container_width=True,
        )

# ----------------------------------------------------------------------------
# Handle the selection — set user type and route to P-02.
# ----------------------------------------------------------------------------
if policy_selected:
    set_user_type("policy_maker", "Policy Maker")
    st.switch_page("pages/02_Scope_Setup.py")  # M-P02-POLISH

if mnc_selected:
    set_user_type("mnc", "MNC")
    st.switch_page("pages/02_Scope_Setup.py")  # M-P02-POLISH

# ----------------------------------------------------------------------------
# Footer.
# ----------------------------------------------------------------------------
st.divider()
st.caption(
    "Demo build — authentication deferred."
)

import time
import logging
import ee

logger = logging.getLogger("ee_timing")
logger.setLevel(logging.INFO)
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[ee_timing] %(message)s"))
    logger.addHandler(h)

_original_getInfo = ee.ComputedObject.getInfo

def _timed_getInfo(self, *args, **kwargs):
    label = type(self).__name__
    t0 = time.perf_counter()
    try:
        result = _original_getInfo(self, *args, **kwargs)
        elapsed = time.perf_counter() - t0
        logger.info(f"{label}.getInfo()  {elapsed:6.2f}s  OK")
        return result
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        logger.info(f"{label}.getInfo()  {elapsed:6.2f}s  FAILED: {exc}")
        raise

ee.ComputedObject.getInfo = _timed_getInfo