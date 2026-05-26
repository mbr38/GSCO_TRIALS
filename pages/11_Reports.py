"""P-11 — Reports (M-P11.1).

Scaffold for the Reports page. Two templates ship in v1 (Policy
audit / Supplier audit, filtered by user type per Wireframes §P-11).
Source picker reads from ``st.session_state["saved_analyses"]``,
filtered to entries whose ``type`` is in the chosen template's
``accepted_source_types``.

S1_TemplateAndSource is the only state wired up here. S2 / S3 are
stubbed with placeholder messages; they land in M-P11.2 (preview),
M-P11.3 (PDF export), and M-P11.4 (CSV/JSON + Save-as-report
wiring from P-05 / P-08).

Streamlit page rules (CLAUDE.md §7): imports → set_page_config →
guards → page body. No EE init — same router-only pattern as P-03
and P-09.
"""

# M-P11.1
from __future__ import annotations

import streamlit as st

from utils.state import require_user_type

st.set_page_config(
    page_title="Reports — GSCO",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_user_type()
# No require_earth_engine — reports are reference/derived content.

from ui.components.persistent_nav import render_persistent_nav
from ui.components.p11_renderer import render_p11


render_persistent_nav()
st.divider()

st.title("Reports")
st.caption(
    "Build a report from one or more saved analyses. Templates are "
    "filtered by your user type; sources are filtered to compatible "
    "saved-analysis types."
)
render_p11()
