"""P-08 save action (M-P08.4).

Bundles the current ``prioritisation_state`` into a ``saved_analyses``
entry with ``type="prioritisation"``. One row per batch run.

Schema parallels the M-P10 screening entry; ``type`` discriminates so
P-10's row-rendering helpers can dispatch.
"""

# M-P08.4
from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone

import streamlit as st

from ui.prioritisation_state import (
    PrioritisationState,
    selected_pillars,
)


def save_prioritisation_as_report(state: PrioritisationState) -> None:
    """Push the current prioritisation_state to saved_analyses.

    Surface a toast on success; an early-exit warning toast when there
    are no completed results to save.
    """
    if not state.supplier_results:
        st.toast("Nothing to save — no suppliers completed.", icon="⚠️")
        return

    entry = _build_save_entry(state)
    st.session_state.setdefault("saved_analyses", []).append(entry)
    st.toast(
        f"✓ Saved as **{entry['name']}**. "
        f"View on Saved Analyses (P-10).",
        icon="💾",
    )


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
