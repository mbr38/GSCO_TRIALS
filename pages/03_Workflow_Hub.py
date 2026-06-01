"""P-03 — Workflow Hub (M-P0103).

The user's home base after picking a scope on P-02. Three sections:
welcome + scope summary, two workflow cards (Inspect → P-04;
Prioritisation → P-07), three persistent-module cards
(Indicator Library → P-09, Saved Analyses → P-10, Reports → P-11).
All five destinations are live (the "placeholder" framing in earlier
revisions of this docstring is stale).

This page is a router — no engine calls, no EE init needed. The
``require_user_type`` guard is the only access gate.

Streamlit page numbering: ``pages/03_*`` slots P-03 between P-02
(``02_Scope_Setup``) and P-04 (``04_Inspect_Setup``) in the sidebar.

Streamlit page rules (CLAUDE.md §7): imports -> set_page_config ->
guards -> EE init -> EE-dependent imports.
"""

# M-P0103
from __future__ import annotations

import streamlit as st

from utils.state import require_user_type

st.set_page_config(
    page_title="Workflow Hub — GSCO",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_user_type()
# No EE init — P-03 is purely a router.

from ui.components.p03_hub import render_workflow_hub
from ui.components.persistent_nav import render_persistent_nav


render_persistent_nav()
st.divider()

st.title("Workflow Hub")
render_workflow_hub()
