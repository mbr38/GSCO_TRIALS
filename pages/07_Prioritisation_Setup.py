"""P-07 — Prioritisation — Setup (M-P07).

Setup page for batch screening across multiple suppliers. Three input
modes:
  - Supply chain mode: when a scope is loaded, pick from its nodes
    (all by default, user can deselect any).
  - Ad hoc list mode: paste 'name, lat, lon' per line.
  - Country supplier database: disabled (v1.x).

Writes ``st.session_state.prioritisation_setup`` and navigates to P-08.
The 20-supplier cap is enforced at this page; warnings are surfaced
before the user hits Run.
"""

# M-P07
from __future__ import annotations

import streamlit as st

from utils.state import require_user_type
from utils.ee_init import require_earth_engine

st.set_page_config(
    page_title="Prioritisation Setup — GSCO",
    page_icon="📋",
    layout="wide",
)

require_user_type()
require_earth_engine()

from ui.components.persistent_nav import render_persistent_nav
from ui.components.p07_form import render_prioritisation_setup

render_persistent_nav()
st.divider()

st.title("Prioritisation — Setup")
st.caption(
    "Batch-screen up to 20 suppliers in one run. Results land on the "
    "Prioritisation Results page (P-08) ranked by audit priority."
)
render_prioritisation_setup()
