"""P-09 — Indicator Library (M-P09).

Static reference page. Pillar tabs with sub-section accordion; per-card
definition + decision relevance + limitations + ESG alignment.

Streamlit page rules (CLAUDE.md §7): imports → set_page_config →
guards → page body. No EE init — this is a router/reference page,
same pattern as P-03.

Streamlit page numbering: ``pages/09_*`` slots P-09 between P-08
(Prioritisation Results) and P-10 (Saved Analyses) in the sidebar.
"""

# M-P09
from __future__ import annotations

import streamlit as st

from utils.state import require_user_type

st.set_page_config(
    page_title="Indicator Library — GSCO",
    page_icon="📚",
    layout="wide",
)

require_user_type()
# No require_earth_engine — reference-only page.

from ui.components.persistent_nav import render_persistent_nav
from ui.components.p09_library import render_indicator_library


render_persistent_nav()
st.divider()

st.title("Indicator Library")
st.caption(
    "Reference catalogue of every indicator the tool can compute. "
    "Browse by pillar; each card shows definition, decision relevance, "
    "data source, and regulatory alignment."
)
render_indicator_library()
