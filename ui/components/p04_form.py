"""P-04 setup form (M-P04).

Single editable form composing the four sections of the Inspect Setup
page (centre / radius / indicators / run). The form's submit handler
writes ``st.session_state["screening_setup"]`` in the same shape P-05
already reads, then navigates via ``st.switch_page``.

Authority: docs/Wireframes_All_v4.md §P-04, docs/PLFS_v4.md §P-04.
"""

# M-P04
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from ui.components.p04_indicator_registry import (
    ALL_INDICATOR_IDS,
    INDICATORS_BY_PILLAR,
    display_name,
)


# Fixed radius stops per Wireframes §P-04 C5 (resolved design choice 3).
_RADIUS_STOPS_KM: tuple[int, ...] = (1, 5, 10, 25, 50, 100)

# 90-day window per Wireframes §P-04 C7 + Indicators_Computation §0.5.
# Time-range UI lands with P-06; for screening we always use the latest
# valid 90-day composite.
_SCREENING_WINDOW_DAYS: int = 90


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_setup_form() -> None:
    """Compose the four form sections and the run buttons.

    Each helper renders its own bordered container so the page reads as
    four discrete blocks.
    """
    centre     = _render_centre_section()
    radius_km  = _render_radius_section()
    indicators = _render_indicator_section()
    _render_run_section(centre, radius_km, indicators)


# ---------------------------------------------------------------------------
# Centre section (C1–C3)
# ---------------------------------------------------------------------------

def _render_centre_section() -> dict | None:
    """Centre-mode tabs + Free-Coordinates input.

    v1: only Free Coordinates is wired. Region and Supplier tabs render
    explanatory info because both require a ``supplyChain`` object from
    P-02 — see v1x_followups.md.
    """
    with st.container(border=True):
        st.markdown("### Location")
        tab_free, tab_region, tab_supplier = st.tabs(
            ["Free coordinates", "Region (P-02)", "Supplier (P-02)"]
        )

        centre: dict | None = None
        with tab_free:
            centre = _render_free_coordinates_tab()
        with tab_region:
            st.info(
                "Region selection requires a loaded scope. Scope setup "
                "(P-02) lands in a later milestone. Use **Free "
                "coordinates** for now."
            )
        with tab_supplier:
            st.info(
                "Supplier selection requires a loaded supply chain. "
                "Scope setup (P-02) lands in a later milestone."
            )
    return centre


def _render_free_coordinates_tab() -> dict:
    """Lat/lon number inputs. Defaults to São Paulo for demo continuity
    with the scratch-page bridge.
    """
    col_lat, col_lon = st.columns(2)
    with col_lat:
        lat = st.number_input(
            "Latitude",
            min_value=-90.0,
            max_value=90.0,
            value=-23.5505,
            step=0.0001,
            format="%.4f",
            help="Decimal degrees; range −90 to 90.",
        )
    with col_lon:
        lon = st.number_input(
            "Longitude",
            min_value=-180.0,
            max_value=180.0,
            value=-46.6333,
            step=0.0001,
            format="%.4f",
            help="Decimal degrees; range −180 to 180.",
        )
    return {"lat": lat, "lon": lon}


# ---------------------------------------------------------------------------
# Radius section (C5)
# ---------------------------------------------------------------------------

def _render_radius_section() -> int:
    """Buffer-radius selector. Six fixed stops; default 5 km."""
    with st.container(border=True):
        st.markdown("### Buffer radius")
        radius_km = st.select_slider(
            "Radius (km)",
            options=_RADIUS_STOPS_KM,
            value=5,
            help=(
                "Smaller buffers give per-facility detail; larger "
                "buffers capture regional context. Some indicators "
                "(notably CAMS PM₁₀/₂.₅ at ~44 km native pixel) need "
                "at least 25 km to produce a value."
            ),
        )
        st.caption(
            f"Screening will inspect a **{radius_km} km radius** around "
            f"the centre."
        )
    return radius_km


# ---------------------------------------------------------------------------
# Indicator section (C6)
# ---------------------------------------------------------------------------

def _render_indicator_section() -> set[str]:
    """Per-pillar collapsible groups; all 19 pre-selected by default."""
    # Initialise selection on first render so toggles persist across
    # Streamlit reruns within the same session.
    if "p04_selected_indicators" not in st.session_state:
        st.session_state["p04_selected_indicators"] = set(ALL_INDICATOR_IDS)
    # M-P04 polish-2 — generation counter appended to each checkbox key.
    # Reset/Deselect bumps this; Streamlit honours value= only on a
    # fresh key, so versioning the keys is how we force a visual reset.
    if "p04_indicator_generation" not in st.session_state:
        st.session_state["p04_indicator_generation"] = 0

    with st.container(border=True):
        # M-P04 polish — two-button selection control. Wider header
        # column for the prose, narrower one split between the buttons.
        header_cols = st.columns([3, 2])
        with header_cols[0]:
            st.markdown("### Indicators")
            st.caption(
                "All indicators are selected by default. Deselect any "
                "you don't need; a single-indicator selection produces "
                "the focused map view."
            )
        with header_cols[1]:
            col_reset, col_deselect = st.columns(2)
            with col_reset:
                if st.button("Reset to all", use_container_width=True):
                    _reset_indicators(to_all=True)
                    st.rerun()
            with col_deselect:
                if st.button("Deselect all", use_container_width=True):
                    _reset_indicators(to_all=False)
                    st.rerun()

        for pillar, label in [
            ("air",    "Air Pollution"),
            ("ghg",    "GHG emissions"),
            ("nature", "Nature/Land"),
        ]:
            _render_pillar_indicators(pillar, label)

    return st.session_state["p04_selected_indicators"]


def _reset_indicators(to_all: bool) -> None:
    """M-P04 polish-2 — restore the indicator selection.

    Bumps ``p04_indicator_generation`` so the checkbox keys on the next
    rerun are fresh strings (``p04_ind_<id>_v<N+1>``). Streamlit honours
    the ``value=`` parameter only on a key it hasn't seen before, so
    versioning the keys is the reliable way to force a visual reset.
    Mutating existing widget-key entries directly works inconsistently
    across rerun-cycle timings.
    """
    st.session_state["p04_selected_indicators"] = (
        set(ALL_INDICATOR_IDS) if to_all else set()
    )
    st.session_state["p04_indicator_generation"] += 1


def _render_pillar_indicators(pillar: str, label: str) -> None:
    """One pillar's collapsible checkbox grid."""
    pillar_ids = INDICATORS_BY_PILLAR[pillar]
    selected   = st.session_state["p04_selected_indicators"]
    # M-P04 polish-2 — generation versions each checkbox key.
    generation = st.session_state["p04_indicator_generation"]
    n_total    = len(pillar_ids)
    n_selected = sum(1 for ind in pillar_ids if ind in selected)

    # M-P04 polish — keep expanders open across rerun. Default to True
    # on first render since indicators are pre-selected and the user
    # likely wants them visible; subsequent renders honour whatever
    # state Streamlit reports for the widget.
    expander_key = f"p04_expanded_{pillar}"
    if expander_key not in st.session_state:
        st.session_state[expander_key] = True

    with st.expander(
        f"{label} ({n_selected} / {n_total} selected)",
        expanded=st.session_state[expander_key],
    ):
        cols = st.columns(3)
        for i, indicator_id in enumerate(pillar_ids):
            col = cols[i % 3]
            with col:
                checked = indicator_id in selected
                new_checked = st.checkbox(
                    display_name(indicator_id),
                    value=checked,
                    key=f"p04_ind_{indicator_id}_v{generation}",
                )
                if new_checked and indicator_id not in selected:
                    selected.add(indicator_id)
                elif not new_checked and indicator_id in selected:
                    selected.discard(indicator_id)


# ---------------------------------------------------------------------------
# Run section (C8–C9)
# ---------------------------------------------------------------------------

def _render_run_section(
    centre:     dict | None,
    radius_km:  int,
    indicators: set[str],
) -> None:
    """Summary line + validation + the two run buttons."""
    with st.container(border=True):
        st.markdown("### Run")

        n_indicators = len(indicators)
        if centre is None:
            st.warning("Pick a centre point above to enable Run.")
        else:
            st.markdown(
                f"**Centre.** {centre['lat']:.4f}, {centre['lon']:.4f}"
                f" &nbsp;&nbsp; **Buffer.** {radius_km} km radius"
                f" &nbsp;&nbsp; **Indicators.** {n_indicators}"
            )

        can_run = centre is not None and n_indicators >= 1
        if centre is not None and n_indicators == 0:
            st.warning(
                "At least one indicator must be selected. Use the "
                "**Reset to all** button above to restore the default."
            )

        col_screening, col_trend = st.columns(2)
        with col_screening:
            if st.button(
                "Run Screening",
                type="primary",
                disabled=not can_run,
                use_container_width=True,
            ):
                _commit_and_navigate(centre, radius_km, indicators)
        with col_trend:
            st.button(
                "Run Trend",
                disabled=True,
                use_container_width=True,
                help=(
                    "Trend View (P-06) lands in a later milestone. "
                    "Until then, screening is the only mode."
                ),
            )


def _commit_and_navigate(
    centre:     dict,
    radius_km:  int,
    indicators: set[str],
) -> None:
    """Write ``screening_setup`` in the shape P-05 reads, then navigate."""
    today = date.today()
    start = today - timedelta(days=_SCREENING_WINDOW_DAYS)
    st.session_state["screening_setup"] = {
        "centre":          centre,
        "radius_km":       radius_km,
        "time_range":      [start.isoformat(), today.isoformat()],
        "indicators":      sorted(indicators),
        "mode":            "screening",
        "centre_metadata": {"source": "P-04 setup"},
    }
    # Drop any leftover P-05 page_state so the screening re-enters
    # S1_Computing with a fresh run_id.
    st.session_state.pop("page_state", None)
    st.switch_page("pages/05_Screening_Results.py")
