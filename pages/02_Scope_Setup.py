"""P-02 — Scope Setup (M-P02).

The scope-setup page. User-type-branched: MNC users pick a demo supply
chain or "no scope"; Policy Maker users pick a country / administrative
region or "no scope". Two-step interaction: ModePick → Preview/Confirm.

Writes ``st.session_state["scope"]`` on confirm:
    - Supply chain: ``{"kind": "supply_chain", "data": <SupplyChain>}``
    - Region:       ``{"kind": "region",       "data": <Region>}``
    - None:         ``{"kind": "none",         "data": None}``

Then routes to P-03 (Workflow Hub) when it exists, or P-04 (Inspect
Setup) until then.

P-02 always enters at ModePick — per the locked design, last scope is
not remembered across visits. v1.x can revisit (see v1x_followups.md).

Streamlit page numbering: ``pages/02_*`` slots P-02 between the
existing P-02 placeholder (``01_scope_setup.py``, demo map) and P-04
(``04_Inspect_Setup.py``) in the alphabetical sidebar order. The
placeholder will be retired in a follow-up cleanup.

Streamlit page rules (CLAUDE.md §7): imports -> set_page_config ->
guards -> EE init -> EE-dependent imports.
"""

# M-P02
from __future__ import annotations

import streamlit as st

from utils.state import require_user_type
from utils.ee_init import require_earth_engine

st.set_page_config(
    page_title="Scope Setup — GSCO",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_user_type()
require_earth_engine()

from ui.components.p02_form import render_scope_setup
from ui.components.persistent_nav import render_persistent_nav


# M-P0103 — shared nav replaces the per-page helper.
render_persistent_nav()
st.divider()

st.title("Scope Setup")
st.caption(
    "Choose what you want to screen. You can change this any time "
    "from the **Change scope** link in the top nav."
)
render_scope_setup()
