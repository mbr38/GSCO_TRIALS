"""P-06 — Per-indicator Trend View (M-TREND-A2).

A dedicated drill-down page reached from a screening (P-05) via a
"view trend →" affordance on a C4b indicator tile or the "View trend" button
in the single-indicator map, and from P-10 when a saved trend analysis is
opened. Renders the plot-first trend view for one series indicator:

- **Live** — computes the trend on open over the screening window (the
  screening's setup + result are still in session) and caches it.
- **Saved** — renders a re-opened ``type="trend"`` record from its stored
  per-day series, with no recompute (UT9).

The old P-06 "trend mode" wireframe is formally retired (decision-log U7 /
UT8); this page is the per-indicator drill-down, not a cross-indicator mode.

Streamlit page rules: ``set_page_config`` first, then the user-type guard,
then EE init (needed only for the live compute path), then the view imports.
"""

# M-TREND-A2
from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Trend View — GSCO", page_icon="📈", layout="wide")

from utils.state import require_user_type

require_user_type()

from utils.ee_init import require_earth_engine

from ui.components.persistent_nav import render_persistent_nav
from ui.components.trend_view import (
    LOADED_RECORD_KEY,
    clear_active_trend,
    render_active_trend,
    render_saved_trend,
)

render_persistent_nav()
st.title("Trend Analysis")

# --- Saved re-open path (from P-10): render from the stored series, no EE. ---
loaded = st.session_state.get(LOADED_RECORD_KEY)
if loaded is not None:
    if st.button("← Back to Saved Analyses", key="trend_back_saved"):
        st.session_state.pop(LOADED_RECORD_KEY, None)
        st.switch_page("pages/10_Saved_Analyses.py")
    render_saved_trend(loaded)
    st.stop()

# --- Live path (from a screening): needs the screening setup + result. ---
if st.button("← Back to results", key="trend_back_results"):
    clear_active_trend()
    st.switch_page("pages/05_Screening_Results.py")

setup = st.session_state.get("screening_setup")
state = st.session_state.get("page_state")
result = getattr(state, "result", None) if state is not None else None

if not setup or result is None:
    st.info(
        "No screening is loaded. Run a screening on **Inspect Setup → "
        "Screening Results**, then choose **view trend →** on an indicator "
        "to drill into its trend here."
    )
    st.stop()

# EE only needed for the live compute path.
require_earth_engine()
render_active_trend(setup, result)
