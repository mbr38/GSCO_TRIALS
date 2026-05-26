"""P-08 Prioritisation Results page (M-P08.1).

Drives the sequential batch executor and renders the four-state
machine in ``ui/prioritisation_state.py``. The page reads
``st.session_state["prioritisation_setup"]`` (written by P-07) and
holds the live state in ``st.session_state["prioritisation_state"]``.

Streamlit page rules (CLAUDE.md §7): imports -> set_page_config ->
guards -> EE init -> EE-dependent imports.
"""

# M-P08.1
from __future__ import annotations

import streamlit as st

from utils.state import require_user_type
from utils.ee_init import require_earth_engine

st.set_page_config(
    page_title="Prioritisation Results — GSCO",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_user_type()
require_earth_engine()

from ui.components.persistent_nav import render_persistent_nav
from ui.components.p08_renderer import render_p08
from ui.prioritisation_state import (
    PrioritisationState,
    classify,
)

render_persistent_nav()
st.divider()

setup = st.session_state.get("prioritisation_setup")
state: PrioritisationState | None = st.session_state.get(
    "prioritisation_state"
)

# Initialise state if absent (user landed fresh from P-07).
if state is None:
    state = PrioritisationState(kind=classify(setup), setup=setup)
    st.session_state["prioritisation_state"] = state

st.title("Prioritisation — Results")
render_p08(state)
