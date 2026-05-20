"""P-05 — Screening Results (M-UI-E.1 scaffold).

First real result page. Renders the screening outcome after the engine
has run. State machine (Wireframes_All_v4 §P-05):

    S1_Computing  — engine is running, show spinner
    S2_Results    — full success, render all components
    S2_Partial    — some indicators failed, show C9 banner + results
    E1_AllFailed  — all pillars failed, show C10 banner + retry

Input hand-off (M-UI-E.1 — scratch-page bridge):
    P-05 reads ``st.session_state.screening_setup``. When P-04 lands
    (post-M-UI-E.6), this becomes the formal hand-off. Until then,
    the scratch page (pages/99_engine_scratch.py) sets the key directly
    via a "Run on P-05" button.

This milestone delivers Component C1 (analysis header card) and the
state machine. C2 through C10 are placeholders pinned to their target
milestones — see ``docs/Wireframes_All_v4.md`` §P-05.

Streamlit page numbering. The file is ``pages/05_*`` so the sidebar
ordering matches the P-number; P-05 in the wireframes == sidebar slot 5.

Streamlit page rules (CLAUDE.md §7): imports -> set_page_config -> guards
-> EE init -> EE-dependent imports.
"""

# M-UI-E.1
from __future__ import annotations

import uuid

import streamlit as st

from utils.state import require_user_type
from utils.ee_init import require_earth_engine

st.set_page_config(
    page_title="Screening Results — GSCO",
    page_icon="🧭",
    layout="wide",
)

require_user_type()
require_earth_engine()

from engine.orchestrator import ScreeningRun
from ui.components.c3_summary import render_c3_summary
from ui.components.c4a_indicator_map import render_c4a_indicator_map
from ui.components.c4b_kpi_grid import render_c4b_kpi_grid
from ui.components.c5_drilldown import render_c5_drilldowns
from ui.components.c6_confidence_panel import render_c6_confidence_panel
from ui.components.c7_verbal_summary import render_c7_verbal_summary
from ui.components.c8_action_bar import render_c8_action_bar
from ui.components.c9_partial_banner import render_c9_partial_banner
from ui.components.indicator_detail import render_indicator_detail
from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS  # M-HIDE-SUMMARY
from ui.components.persistent_nav import render_persistent_nav
from ui.page_state import PageState, classify_result


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _get_or_init_state() -> PageState | None:
    """Return the current ``PageState`` or ``None`` if no setup is present.

    - No setup at all -> ``None`` (caller renders the empty state).
    - Setup present, no page_state yet -> fresh ``S1_Computing``.
    - Setup + existing page_state -> hand back the existing state
      (idempotent across Streamlit re-runs via ``run_id``).
    """
    setup = st.session_state.get("screening_setup")
    if setup is None:
        return None
    state = st.session_state.get("page_state")
    if state is None:
        state = PageState(name="S1_Computing", run_id=str(uuid.uuid4()))
        st.session_state["page_state"] = state
    return state


def _run_engine_and_transition(state: PageState) -> PageState:
    """Run the engine, classify the result, and return the next state.

    Translates the UI-facing ``screening_setup`` shape into the engine's
    ``ScreeningRun`` constructor args. Any exception escaping the engine
    is treated as a hard failure -> ``E1_AllFailed``.
    """
    setup = st.session_state["screening_setup"]
    aoi = {
        "centre":    setup["centre"],
        "radius_km": setup["radius_km"],
    }
    try:
        result = ScreeningRun(
            aoi=aoi,
            selected_indicators=set(setup["indicators"]),
            time_range=tuple(setup["time_range"]),
            ee_client=None,
            centre_metadata=setup.get("centre_metadata", {}),
        ).run()
    except Exception as exc:  # noqa: BLE001 — surface anything as E1.
        return PageState(
            name="E1_AllFailed",
            run_id=state.run_id,
            error=str(exc),
        )
    return PageState(
        name=classify_result(result),
        run_id=state.run_id,
        result=result,
        failures=result.get("_failures"),
    )


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------

def _render_c1_header(setup: dict, result: dict | None) -> None:
    """C1 — Analysis header card.

    Top-of-page metadata block. Appears in every non-empty state.
    Wireframes §P-05 C1: location + coordinates, AOI summary, time
    range, indicator list, computation timestamp.
    """
    centre = setup["centre"]
    coords = f"{centre['lat']:.4f}, {centre['lon']:.4f}"
    time_range = setup["time_range"]
    indicators = list(setup["indicators"])
    computed_at = (
        result.get("_meta", {}).get("computed_at") if result else "—"
    )
    centre_source = setup.get("centre_metadata", {}).get("source", "—")

    with st.container(border=True):
        st.markdown("### Analysis")
        col1, col2 = st.columns([2, 3])
        with col1:
            st.markdown(f"**Location.** {coords}")
            st.markdown(f"**Source.** {centre_source}")
            st.markdown(f"**Buffer.** {setup['radius_km']} km radius")
        with col2:
            st.markdown(
                f"**Time range.** {time_range[0]} → {time_range[1]}"
            )
            st.markdown(f"**Indicators.** {len(indicators)} selected")
            st.markdown(f"**Computed.** {computed_at}")
        with st.expander("Indicator list"):
            for ind in sorted(indicators):
                st.markdown(f"- `{ind}`")


def _render_placeholder(component_id: str, milestone: str) -> None:
    """Placeholder for a component landing in a later milestone."""
    with st.container(border=True):
        st.caption(f"[{component_id} — landing in {milestone}]")


# ---------------------------------------------------------------------------
# State renderers
# ---------------------------------------------------------------------------

def _render_no_setup() -> None:
    """Empty state — no screening configured yet."""
    st.title("Screening Results")
    st.info(
        "No screening configured. Configure a run on the **Screening "
        "Setup** page (P-04, landing in a later milestone), or use the "
        "**engine scratch page** for now."
    )
    if st.button("Go to scratch page"):
        st.switch_page("pages/99_engine_scratch.py")


def _render_s1_computing() -> None:
    """S1 — spinner while the engine runs. Transitions on completion."""
    st.title("Screening Results")
    with st.spinner("Running screening — this takes ~30–60 seconds…"):
        state = st.session_state["page_state"]
        new_state = _run_engine_and_transition(state)
        st.session_state["page_state"] = new_state
    st.rerun()


def _render_s2(state: PageState) -> None:
    """S2_Results and S2_Partial render identically — the C9 banner
    decides for itself whether anything is missing (covers both explicit
    `_failures` entries and silent `skipped_reason` provenance markers),
    so the orchestrator's partial/full distinction doesn't need to be
    re-encoded in the page layout.

    M-UI-E.6: branches on indicator count. A single-indicator selection
    renders the lean inspection variant (header → map → detail → save)
    because the multi-indicator aggregates (C3 chips, C4b grid, C5
    drill-downs, C6, C7) all depend on pillar aggregates that don't
    exist when only one indicator was selected.
    """
    setup  = st.session_state["screening_setup"]
    result = state.result

    if len(setup.get("indicators", [])) == 1:
        _render_single_indicator_view(setup, result)
    else:
        _render_multi_indicator_view(setup, result)


def _render_multi_indicator_view(setup: dict, result: dict) -> None:
    """Multi-indicator screening view (M-UI-E.1 through .5)."""
    # M-P04 polish — pass the user's selection through to C4b/C9 so
    # deselected indicators don't render as failures.
    selected = set(setup.get("indicators", []))

    st.title("Screening Results")
    _render_c1_header(setup, result)
    render_c9_partial_banner(result, selected)
    render_c3_summary(result)
    render_c4b_kpi_grid(result, selected)
    render_c5_drilldowns(result)
    render_c6_confidence_panel(result)
    # M-HIDE-SUMMARY: only render C7 when the user ran the full canonical
    # indicator set. Subsets break the verbal summary templates'
    # breadth-of-coverage assumptions ("across the monitored pollutants"
    # is misleading when most weren't actually selected). Set equality —
    # not just count — guards against the edge case of 19 non-canonical
    # IDs or the canonical set growing in a later milestone.
    if selected == set(ALL_INDICATOR_IDS):
        render_c7_verbal_summary(result)
    render_c8_action_bar(result)

    with st.expander("Debug: raw payload"):
        st.json(result)


# M-UI-E.6
def _render_single_indicator_view(setup: dict, result: dict) -> None:
    """Lean single-indicator variant — header + map + detail + save.

    C3 / C4b / C5 / C6 / C7 are intentionally omitted because they
    visualise pillar-level aggregates that don't apply when only one
    indicator was selected.
    """
    indicator_id = next(iter(setup["indicators"]))
    # M-P04 polish — selection-aware C9 (banner fires only if the one
    # indicator the user picked is itself missing).
    selected = set(setup.get("indicators", []))

    st.title("Indicator Inspection")
    _render_c1_header(setup, result)
    render_c9_partial_banner(result, selected)
    render_c4a_indicator_map(indicator_id, setup, result)
    render_indicator_detail(indicator_id, result)
    render_c8_action_bar(result)

    with st.expander("Debug: raw payload"):
        st.json(result)


def _render_e1_all_failed(state: PageState) -> None:
    """E1_AllFailed — error banner (C10 placeholder for now) + retry."""
    st.title("Screening Results")
    setup = st.session_state.get("screening_setup")
    if setup:
        _render_c1_header(setup, state.result)
    st.error(
        "Screening failed. "
        + (state.error or "All pillars returned no data.")
    )
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Retry", use_container_width=True):
            # Drop the failed page_state; keep screening_setup so the
            # next render re-enters S1_Computing with the same inputs.
            st.session_state.pop("page_state", None)
            st.rerun()
    with col_b:
        if st.button("Back to scratch page", use_container_width=True):
            st.switch_page("pages/99_engine_scratch.py")


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

# M-P0103 — shared nav replaces the per-page helper.
render_persistent_nav()
st.divider()

state = _get_or_init_state()
if state is None:
    _render_no_setup()
elif state.name == "S1_Computing":
    _render_s1_computing()
elif state.name == "S2_Results":
    _render_s2(state)
elif state.name == "S2_Partial":
    _render_s2(state)
elif state.name == "E1_AllFailed":
    _render_e1_all_failed(state)
