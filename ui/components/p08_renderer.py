"""P-08 renderer (M-P08.1).

Dispatches to the four state renderers. S2_Running drives the batch
executor inline — the executor's progress callback updates the UI
via direct st.empty() container writes, so the user sees rows
accumulate as each supplier completes.
"""

# M-P08.1
from __future__ import annotations

import streamlit as st

from engine.prioritisation_executor import run_batch
# M-P08.2-FIX
from ui.components.p08_ranked_table import (
    render_rank_by_selector,
    render_ranked_table,
)
# M-P08.3
from ui.components.p08_risk_matrix import render_risk_matrix
# M-P08.4
from ui.components.p08_save_action import (
    render_p08_save_banner,
    save_prioritisation_as_report,
)
from ui.prioritisation_state import (
    PrioritisationState,
    PrioritisationStateKind,
    SupplierResult,
    selected_pillars,
)


# M-P08.1: pillar order in displayed columns — locked.
_PILLAR_COLS: tuple[tuple[str, str, str], ...] = (
    ("air",    "Air",    "air.audit_followup_priority"),
    ("ghg",    "GHG",    "ghg.audit_followup_priority"),
    ("nature", "Nature", "nature.followup_priority"),
)


def render_p08(state: PrioritisationState) -> None:
    kind = state.kind
    if kind == PrioritisationStateKind.E1_FAILED:
        _render_e1_failed(state)
    elif kind == PrioritisationStateKind.S2_RUNNING:
        _render_s2_running(state)
    elif kind == PrioritisationStateKind.S3_RESULTS:
        _render_s3_results(state)
    else:
        st.error(f"Unknown prioritisation state: {kind}", icon="⚠️")


# ──────────────────────────────────────────────────────────────────
# E1 — couldn't start
# ──────────────────────────────────────────────────────────────────

def _render_e1_failed(state: PrioritisationState) -> None:
    if state.error:
        st.error(
            f"**Prioritisation failed.** {state.error}",
            icon="⚠️",
        )
    else:
        st.error(
            "**Prioritisation can't start.** No batch setup is loaded. "
            "Go to **Prioritisation Setup (P-07)** to configure a batch.",
            icon="⚠️",
        )
    if st.button("Go to P-07 Setup", type="primary"):
        st.switch_page("pages/07_Prioritisation_Setup.py")


# ──────────────────────────────────────────────────────────────────
# S2 — running
# ──────────────────────────────────────────────────────────────────

def _render_s2_running(state: PrioritisationState) -> None:
    setup = state.setup
    n_total = len(setup["suppliers"])

    # Header strip: setup summary.
    _render_setup_summary(setup)

    # Cancel button.
    col_cancel, _ = st.columns([1, 5])
    with col_cancel:
        if st.button(
            "✋ Cancel batch", type="secondary", use_container_width=True,
        ):
            state.cancelled = True
            st.toast("Cancelling at next supplier boundary...", icon="✋")

    # Progress bar + status.
    progress_container = st.empty()
    status_container   = st.empty()

    # Live results table.
    st.markdown("### Results")
    # M-P08.2-FIX: render the rank-by selector ONCE, outside the redraw
    # container — same widget key on every re-render would crash.
    rank_by = render_rank_by_selector(state)

    results_container = st.empty()
    # M-P08.4-FIX: selection OFF during S2_Running. The progress
    # callback re-renders the table on every supplier completion;
    # registering selection_mode's widget key twice would crash.
    with results_container.container():
        render_ranked_table(state, rank_by, enable_selection=False)

    # If executor hasn't run yet for this state, run it now.
    # The executor blocks until done; the callback updates containers.
    if state.completed_count == 0:
        def on_progress(latest: SupplierResult, done: int, total: int) -> None:
            progress_container.progress(
                done / total,
                text=f"Completed {done} of {total} suppliers",
            )
            status_container.info(
                f"Last completed: **{latest.name}** ({latest.status})",
                icon="📋",
            )
            # M-P08.2-FIX: table redraws use the rank_by from the
            # selector above; the selector itself is NOT re-rendered.
            # M-P08.4-FIX: same enable_selection=False as the initial
            # render — this is the redraw that would have crashed.
            with results_container.container():
                render_ranked_table(state, rank_by, enable_selection=False)

        try:
            run_batch(state, setup, on_progress)
        except Exception as exc:  # noqa: BLE001
            # Catastrophic executor failure (shouldn't happen — per-
            # supplier errors are caught inside run_batch).
            state.kind  = PrioritisationStateKind.E1_FAILED
            state.error = f"Batch executor crashed: {exc}"

        st.rerun()  # Force a clean rerun so S3 view renders.
    else:
        # State already has results — mid-execution between Streamlit
        # reruns. Just show the current snapshot.
        progress_container.progress(
            state.completed_count / n_total,
            text=(
                f"Completed {state.completed_count} of {n_total} suppliers"
            ),
        )


# ──────────────────────────────────────────────────────────────────
# S3 — results
# ──────────────────────────────────────────────────────────────────

def _render_s3_results(state: PrioritisationState) -> None:
    setup = state.setup
    _render_setup_summary(setup)

    n_success   = sum(1 for r in state.supplier_results if r.status == "success")
    n_partial   = sum(1 for r in state.supplier_results if r.status == "partial")
    n_failed    = sum(1 for r in state.supplier_results if r.status == "failed")
    n_cancelled = sum(1 for r in state.supplier_results if r.status == "cancelled")
    total       = len(state.supplier_results)

    if state.cancelled and n_cancelled > 0:
        st.warning(
            f"**Batch cancelled** after {total - n_cancelled} of {total} "
            f"suppliers. {n_cancelled} unprocessed.",
            icon="✋",
        )
    else:
        st.success(
            f"**Batch complete.** {n_success} succeeded, "
            f"{n_partial} partial, {n_failed} failed.",
            icon="✅",
        )

    st.markdown("### Results")
    # M-P08.3: two-tab structure per Wireframes §P-08. Ranking is the
    # default view; Risk matrix renders lazily on tab activation.
    tab_ranking, tab_matrix = st.tabs(["📋 Ranking", "📊 Risk matrix"])

    with tab_ranking:
        # M-P08.2-FIX: selector once, then table.
        # M-P08.4-FIX: selection ON in S3 — the table renders exactly
        # once per page run here, so the widget key is safe and the
        # row-click drill-in into P-05 is wired.
        rank_by = render_rank_by_selector(state)
        render_ranked_table(state, rank_by, enable_selection=True)

    with tab_matrix:
        render_risk_matrix(state)

    # Action bar lives BELOW the tabs so it applies to either view.
    col_save, col_rerun = st.columns([1, 1])
    with col_save:
        # M-P08.4: working save action — pushes the whole batch into
        # saved_analyses as a single entry with type="prioritisation".
        if st.button(
            "💾 Save as report",
            type="primary",
            use_container_width=True,
            key="p08_save_button",
        ):
            save_prioritisation_as_report(state)
    with col_rerun:
        if st.button(
            "🔄 New prioritisation",
            use_container_width=True,
        ):
            st.session_state.pop("prioritisation_state", None)
            st.session_state.pop("prioritisation_setup", None)
            st.switch_page("pages/07_Prioritisation_Setup.py")

    # M-P11.4: post-save banner with "Open in Reports". Renders only
    # when a save just happened (sentinel set in session_state).
    render_p08_save_banner()


# ──────────────────────────────────────────────────────────────────
# Shared bits
# ──────────────────────────────────────────────────────────────────

def _render_setup_summary(setup: dict) -> None:
    """One-line setup summary for the page header."""
    pillars       = selected_pillars(setup)
    n_suppliers   = len(setup["suppliers"])
    n_indicators  = len(setup["indicators"])
    radius_km     = setup["radius_km"]
    pillar_labels = ", ".join(
        label for pillar, label, _ in _PILLAR_COLS if pillar in pillars
    ) or "none"
    st.caption(
        f"**Suppliers.** {n_suppliers} "
        f"&nbsp;&nbsp; **Buffer.** {radius_km} km "
        f"&nbsp;&nbsp; **Pillars.** {pillar_labels} "
        f"&nbsp;&nbsp; **Indicators.** {n_indicators}",
        unsafe_allow_html=True,
    )


