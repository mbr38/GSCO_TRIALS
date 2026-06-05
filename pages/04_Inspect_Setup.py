"""P-04 — Inspect — Setup (M-P04).

Configures a single-supplier screening: centre point, radius, indicators.
Writes ``st.session_state["screening_setup"]`` in the shape P-05 already
reads and navigates via ``st.switch_page``.

v1 scope (M-P04, M-P04-ACTIVATE):
  - **Centre input:** scope-driven. With a supply-chain scope, pick a
    node; with a region scope, the centroid+radius are locked; with no
    scope, the Free Coordinates tab is active (with a geocoder) and the
    Region/Supplier tabs are informational links back to P-02.
  - **Indicators:** all 19 pre-selected by default; user deselects.
    Per-pillar collapsible groups, "Reset to all" link.
  - **Time range:** the screening-window picker is shown (default
    90 days, user-configurable per run — M-UI-A3 retired the earlier
    "hidden in screening mode" rule H4).
  - **Run Screening:** primary, enabled when ≥1 indicator + centre.
    Trend is a per-indicator drill-down launched from P-05
    ("view trend →"), not a P-04 run mode (M-TREND-A2).

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

from utils.state import require_user_type
from utils.ee_init import require_earth_engine

st.set_page_config(
    page_title="Inspect — Setup — GSCO",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_user_type()
require_earth_engine()

from ui.components.p04_form import render_setup_form
from ui.components.persistent_nav import render_persistent_nav
from ui.components.page_tutorial import render_tutorial_trigger


# M-P0103 — shared nav replaces the per-page helper.
render_persistent_nav()
st.divider()

# M-TUTORIAL-A1 — manual "Show me around" tour for this setup page.
render_tutorial_trigger("P-04")

st.title("Inspect — Setup")
st.caption(
    "Configure a single-supplier screening: pick a location, a radius, "
    "and the indicators you want. The result lands on the Screening "
    "Results page (P-05)."
)
render_setup_form()
