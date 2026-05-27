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
    initial_sidebar_state="expanded",
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
from ui.components.c_partial_caveat import render_partial_caveat  # M-PARTIAL-CAVEAT
from ui.components.indicator_detail import render_indicator_detail
from ui.components.indicator_info import render_indicator_dialog_if_requested  # M-UI-A2
from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS  # M-HIDE-SUMMARY
from ui.components.persistent_nav import render_persistent_nav
from ui.page_state import PageState, classify_result, detect_e1_reason  # M-RING-UX


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
    # M-E1-INDICATOR-AWARE: thread the user's selection into the
    # classifier so a single-indicator or subset run with real data
    # doesn't route to E1 just because pillar aggregates went None
    # under M-FOLLOWUP-FALLBACK strict-None.
    return PageState(
        name=classify_result(result, setup["indicators"]),
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

    M-P08.4: when ``p05_drill_origin == "prioritisation"`` the page is
    being viewed from a P-08 batch drill-in — render a back link above
    the title so the user can return to the prioritisation results
    without losing the batch state. Direct navigation paths (Inspect
    workflow, P-10 screening saves) don't set the flag and don't see it.
    """
    # M-P08.4
    if st.session_state.get("p05_drill_origin") == "prioritisation":
        if st.button(
            "← Back to prioritisation results",
            key="p05_back_to_p08",
        ):
            st.session_state.pop("p05_drill_origin", None)
            st.switch_page("pages/08_Prioritisation_Results.py")

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
    render_partial_caveat(selected)  # M-PARTIAL-CAVEAT
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
    """E1_AllFailed — error banner (C10 placeholder for now) + retry.

    M-RING-UX: inspects the payload via ``detect_e1_reason`` to pick a
    methodology-aware error message. The orchestrator-exception case
    (``state.error`` populated, ``state.result is None``) keeps the
    generic "Screening failed: <error>" message.
    """
    st.title("Screening Results")
    setup = st.session_state.get("screening_setup")
    if setup:
        _render_c1_header(setup, state.result)

    # M-RING-UX — branch on detected cause when we have a payload.
    if state.error:
        # Orchestrator raised — no payload to inspect; keep the existing
        # generic-failure message.
        st.error(f"Screening failed. {state.error}", icon="⚠️")
    else:
        reason = detect_e1_reason(state.result)
        if reason == "ring_empty":
            st.error(
                "**Screening completed but produced no scores.** Every "
                "indicator was skipped because the surrounding-area "
                "data needed to compute scores wasn't available — "
                "likely because the AOI is too large or the region has "
                "sparse satellite coverage (common in the Amazon, "
                "polar areas, or remote oceans).",
                icon="⚠️",
            )
            st.info(
                "**What you can try:**\n\n"
                "- Use a smaller buffer (≤ 50 km recommended for Air indicators).\n"
                "- Try a different region with better satellite coverage.\n"
                "- Use Free Coordinates mode and screen specific "
                "suppliers rather than the whole region."
            )
        elif reason == "no_data_at_all":
            st.error(
                "**Screening failed.** No usable satellite data was "
                "found for this AOI in the screening window. This may "
                "be due to persistent cloud cover, an AOI over water, "
                "or an asset coverage gap.",
                icon="⚠️",
            )
        else:
            st.error(
                "Screening failed. All pillars returned no data.",
                icon="⚠️",
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

    # M-E1-DEBUG: expose the payload for debugging. Even on E1, the engine
    # has computed something — per-indicator None values, _failures, and
    # _provenance.<x>.skipped_reason fields tell us *why* the screening
    # failed. Hiding the payload makes demo-day "why is this empty?"
    # moments much harder to diagnose. Mirrors the expander S2 already
    # has at the bottom of _render_multi_indicator_view.
    if state.result:
        with st.expander("Debug: raw payload"):
            st.json(state.result)


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

# M-P0103 — shared nav replaces the per-page helper.
render_persistent_nav()
st.divider()

# M-UI-A2 — open the indicator-detail dialog if a Learn-more button was
# clicked on the previous render. Pops the session-state flag so the
# dialog fires once per click; subsequent reruns (e.g. user expanding an
# accordion inside the modal) don't re-trigger it.
render_indicator_dialog_if_requested()

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
