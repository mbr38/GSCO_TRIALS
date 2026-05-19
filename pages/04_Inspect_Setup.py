"""P-04 — Inspect — Setup (M-P04).

Configures a single-supplier screening: centre point, radius, indicators.
Writes ``st.session_state["screening_setup"]`` in the shape P-05 already
reads and navigates via ``st.switch_page``.

v1 scope (M-P04):
  - **Centre input:** Free Coordinates only. Region and Supplier tabs
    are shown but disabled until P-02 (scope setup) lands.
  - **Indicators:** all 19 pre-selected by default; user deselects.
    Per-pillar collapsible groups, "Reset to all" link.
  - **Time range:** hidden in screening mode (Wireframes §P-04 C7);
    lands with P-06. Screening defaults to the latest 90-day window.
  - **Run Screening:** primary, enabled when ≥1 indicator + centre.
  - **Run Trend:** disabled until P-06.

State machine collapses to a single editable form — there's no
intermediate "review" state in v1, since the form's summary line is
visible at all times.

Streamlit page numbering: ``pages/04_*`` keeps P-04 in slot 4 of the
sidebar (alphabetical ordering), between P-02 (``01_scope_setup``) and
P-05 (``05_Screening_Results``).

Streamlit page rules (CLAUDE.md §7): imports -> set_page_config ->
guards -> EE init -> EE-dependent imports.
"""

# M-P04
from __future__ import annotations

import streamlit as st

from utils.state import require_user_type, sign_out
from utils.ee_init import require_earth_engine

st.set_page_config(
    page_title="Inspect — Setup — GSCO",
    page_icon="🎯",
    layout="wide",
)

require_user_type()
require_earth_engine()

from ui.components.p04_form import render_setup_form


# ---------------------------------------------------------------------------
# Page chrome
# ---------------------------------------------------------------------------

def _render_nav() -> None:
    """Top nav bar — same chrome as P-05 and pages/01_scope_setup."""
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


_render_nav()
st.divider()

st.title("Inspect — Setup")
st.caption(
    "Configure a single-supplier screening: pick a location, a radius, "
    "and the indicators you want. The result lands on the Screening "
    "Results page (P-05)."
)
render_setup_form()
