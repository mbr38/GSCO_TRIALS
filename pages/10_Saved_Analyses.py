"""P-10 — Saved Analyses (M-P10).

List view of ``st.session_state["saved_analyses"]`` with per-row
Open / Delete / Export JSON actions. Seeded with two demo entries from
``demo/saved_analyses/*.json`` on cold session entry (see
``demo/saved_analyses/__init__.py``).

Streamlit page numbering. The file is ``pages/10_*`` so the sidebar
slot matches the P-number from Wireframes_All_v4 §P-10.

Authority: docs/Wireframes_All_v4.md §P-10.
"""

# M-P10
from __future__ import annotations

import streamlit as st

from utils.state import require_user_type

st.set_page_config(
    page_title="Saved Analyses — GSCO",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_user_type()
# No EE init — P-10 is a pure session-state list view.

from ui.components.p10_list import render_saved_analyses
from ui.components.persistent_nav import render_persistent_nav

render_persistent_nav()
st.divider()

st.title("Saved Analyses")
render_saved_analyses()
