"""
P-02 Scope set-up (placeholder for the demo).

This page currently only renders a small geemap map so we can verify that
the Streamlit + geemap integration works end-to-end. The full scope-setup
flow comes in a later iteration.
"""

import streamlit as st

from utils.state import require_user_type, sign_out
from utils.ee_init import require_earth_engine

require_user_type()
require_earth_engine()                  # ← add EE guard before importing geemap

import geemap.foliumap as geemap        # ← use geemap instead
# ----------------------------------------------------------------------------
# Guard: this page requires a user type to be set on the landing page.
# ----------------------------------------------------------------------------
require_user_type()

st.set_page_config(
    page_title="Scope set-up — GSCO",
    page_icon="🌍",
    layout="wide",
)

# ----------------------------------------------------------------------------
# Persistent navigation.
# Demo version: minimal top bar with user-type chip and Sign out.
# ----------------------------------------------------------------------------
nav_left, nav_right = st.columns([4, 1])
with nav_left:
    st.caption(
        f"Signed in as **{st.session_state.user_type_label}**  ·  "
        f"Session `{st.session_state.session_id}`"
    )
with nav_right:
    if st.button("Sign out", use_container_width=True):
        sign_out()
        st.switch_page("app.py")

st.divider()

# ----------------------------------------------------------------------------
# Page body.
# ----------------------------------------------------------------------------
st.title("Scope set-up")

st.info(
    "Demo placeholder. Full scope-setup (GSCO catalogue, upload, manual entry) "
    "comes in a later iteration. For now this page proves the multi-page flow "
    "works and that geemap renders inside Streamlit."
)

# ----------------------------------------------------------------------------
# Tiny map demo.
# ----------------------------------------------------------------------------
st.subheader("Map test — Geemap inside Streamlit")
st.caption(
    "If you see an interactive map with a satellite basemap and a marker at "
    "Cambridge, UK, the stack is working."
)

# Build the map once per session and cache it in session state, so
# Streamlit re-runs don't reset the map's pan/zoom state.
if "demo_map" not in st.session_state:
    m = geemap.Map(
        center=[52.205, 0.119],   # Cambridge, UK
        zoom=12,
        draw_control=False,
        measure_control=False,
        fullscreen_control=False,
        attribution_control=True,
    )
    m.add_basemap("SATELLITE")
    m.add_marker(
        location=[52.205, 0.119],
        popup="Cambridge, UK — sample marker",
    )
    st.session_state.demo_map = m

st.session_state.demo_map.to_streamlit(height=500)

# ----------------------------------------------------------------------------
# Next steps.
# ----------------------------------------------------------------------------
st.divider()
st.markdown(
    """
    **What this proves**

    - Streamlit multi-page navigation routes from the landing page here.
    - User-type state survives the page transition.
    - Geemap renders inline with a satellite basemap and a marker.
    - The sign-out flow clears state and returns to landing.

    **Next iteration**

    Replace this map demo with the real scope-setup UI: a mode toggle
    (GSCO catalogue / upload / manual entry), an upload widget, a preview
    map of the loaded chain, and a Confirm button that routes to P-03.
    """
)
