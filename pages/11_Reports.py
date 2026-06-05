"""P-11 — Reports (M-P11.1).

The Reports page. A five-template registry ships in v1 (M-REPORT-A1):
``general``, ``mnc_ghg`` (ESRS E1), ``mnc_air`` (ESRS E2),
``mnc_nature`` (ESRS E4), and ``trend`` — filtered by user type and by
each template's ``accepted_source_types``. Source picker reads from
``st.session_state["saved_analyses"]``.

All three states are live: S1 (template + source pick), S2 (live HTML
preview), S3 (export: PDF / CSV / JSON). The "stubbed S2/S3" framing in
earlier revisions of this docstring is stale. Genuine remaining stubs
are content-level only: ESRS per-indicator datapoint codes and the
policy/action/target sub-sections render as labelled out-of-scope stubs
(see ``ui/components/p11_esrs.py``).

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
