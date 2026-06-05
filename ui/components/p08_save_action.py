"""P-08 save action (M-P08.4 / M-P11.4).

Bundles the current ``prioritisation_state`` into a ``saved_analyses``
entry with ``type="prioritisation"``. One row per batch run.

Schema parallels the M-P10 screening entry; ``type`` discriminates so
P-10's row-rendering helpers can dispatch.

M-P11.4: after a successful save, ``render_p08_save_banner`` (called
by the P-08 renderer after the action bar) surfaces a sticky banner
with an "Open in Reports" button that pre-populates P-11 with the
just-saved source and routes there.
"""

# M-P08.4
from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone

import streamlit as st

from ui.p11_state import route_to_p11_with_source
from ui.prioritisation_state import (
    PrioritisationState,
    selected_pillars,
)


# M-P11.4: sentinel — survives the rerun triggered by the save click
# so the banner re-renders until the user navigates away.
_SAVE_BANNER_KEY = "p08_last_saved_for_p11"


def save_prioritisation_as_report(state: PrioritisationState) -> None:
    """Push the current prioritisation_state to saved_analyses.

    Surface a toast on success; an early-exit warning toast when there
    are no completed results to save.
    """
    if not state.supplier_results:
        st.toast("Nothing to save — no suppliers completed.")
        return

    entry = _build_save_entry(state)
    st.session_state.setdefault("saved_analyses", []).append(entry)
    # M-P11.4: stash the just-saved entry so the banner renders on
    # the next pass through the page.
    st.session_state[_SAVE_BANNER_KEY] = {
        "id":   entry["id"],
        "name": entry["name"],
    }
    st.toast(
        f"Saved as **{entry['name']}**. "
        f"View on Saved Analyses (P-10).",
    )


# M-P11.4
def render_p08_save_banner() -> None:
    """Render the post-save banner on P-08 if a save just happened.

    Called once per page render from the P-08 results renderer, below
    the action bar. The sentinel is consumed when the user clicks
    "Open in Reports" so the banner doesn't reappear after navigation.
    """
    pending = st.session_state.get(_SAVE_BANNER_KEY)
    if not pending:
        return
    st.success(f"Saved as **{pending['name']}**.")
    if st.button(
        "Open in Reports",
        key=f"p08_open_in_reports_{pending['id']}",
        use_container_width=True,
    ):
        route_to_p11_with_source(st.session_state, pending["id"])
        st.session_state.pop(_SAVE_BANNER_KEY, None)
        st.switch_page("pages/11_Reports.py")


def _build_save_entry(state: PrioritisationState) -> dict:
    """Construct the saved_analyses entry from prioritisation_state.

    Pure function — testable without Streamlit.
    """
    pillars     = selected_pillars(state.setup)
    pillar_str  = ", ".join(sorted(pillars)) if pillars else "none"
    n_suppliers = len(state.supplier_results)
    today       = datetime.now(timezone.utc)

    name = (
        f"Prioritisation — {n_suppliers} suppliers ({pillar_str}) "
        f"— {today.strftime('%Y-%m-%d %H:%M UTC')}"
    )

    summary = {
        "n_total":     n_suppliers,
        "n_success":   sum(1 for r in state.supplier_results if r.status == "success"),
        "n_partial":   sum(1 for r in state.supplier_results if r.status == "partial"),
        "n_failed":    sum(1 for r in state.supplier_results if r.status == "failed"),
        "n_cancelled": sum(1 for r in state.supplier_results if r.status == "cancelled"),
    }

    return {
        "id":                   str(uuid.uuid4()),
        "name":                 name,
        "type":                 "prioritisation",
        "prioritisation_setup": state.setup,
        "date_saved":           today.isoformat(),
        "supplier_results":     [
            dataclasses.asdict(r) for r in state.supplier_results
        ],
        "summary":              summary,
    }
