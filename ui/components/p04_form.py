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

from ui.components.analysis_window_picker import (  # M-UI-A3
    WindowSelection,
    render_analysis_window_picker,
)
from ui.components.p04_indicator_registry import (
    ALL_INDICATOR_IDS,
    INDICATORS_BY_PILLAR,
    display_name,
)


# Fixed radius stops per Wireframes §P-04 C5 (resolved design choice 3).
_RADIUS_STOPS_KM: tuple[int, ...] = (1, 5, 10, 25, 50, 100)

# M-UI-A3: the 90-day default lives in engine/constants.py
# (SCREENING_WINDOW_DAYS_DEFAULT) and is consumed via the picker's
# profile fixture. The picker overrides this default per-screening
# when the user changes the window.


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_setup_form() -> None:
    """Top-level orchestrator.

    M-P04-ACTIVATE: branches on ``st.session_state["scope"]``:

    - ``scope.kind == "supply_chain"`` — scope header + node dropdown.
    - ``scope.kind == "region"``       — scope header + locked AOI.
    - ``scope.kind == "none"`` or unset — the original three-tab form
      (Free Coordinates active, Region/Supplier disabled).
    """
    scope = st.session_state.get("scope")
    if scope is None or scope.get("kind") == "none":
        _render_no_scope_form()
    elif scope["kind"] == "supply_chain":
        _render_supply_chain_scoped_form(scope["data"])
    elif scope["kind"] == "region":
        _render_region_scoped_form(scope["data"])
    else:
        # Defensive — unknown scope kind, fall through.
        _render_no_scope_form()


# M-P04-ACTIVATE
def _render_no_scope_form() -> None:
    """The original three-tab form. Free Coordinates active; Region
    and Supplier tabs render informational placeholders. Reached when
    no scope is set or ``scope.kind == "none"`` (ad-hoc fallback).
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

    Free Coordinates is the active path here. Region and Supplier
    selection live on P-02 (Scope Setup); when scope is set, the
    scope-aware forms render instead (see ``render_setup_form``).
    The tabs in this no-scope fallback exist so direct-entry users
    can still navigate to P-02 from inside P-04.
    """
    with st.container(border=True):
        st.markdown("### Location")
        # M-P02-POLISH — drop the "(P-02)" suffix from tab labels; P-02
        # now exists, the forward-reference label is no longer needed.
        tab_free, tab_region, tab_supplier = st.tabs(
            ["Free coordinates", "Region", "Supplier"]
        )

        centre: dict | None = None
        with tab_free:
            centre = _render_free_coordinates_tab()
        with tab_region:
            # M-P02-POLISH — placeholder text post-P-02; offers a route
            # to Scope Setup rather than just an apology.
            st.info(
                "Region selection is set up on the **Scope Setup** page "
                "(P-02). You currently have no scope loaded — use "
                "**Free coordinates** here, or go to Scope Setup to "
                "pick a region."
            )
            if st.button(
                "Go to Scope Setup",
                key="p04_noscope_to_p02_region",
            ):
                st.switch_page("pages/02_Scope_Setup.py")
        with tab_supplier:
            # M-P02-POLISH — same treatment for the Supplier tab.
            st.info(
                "Supplier selection requires a loaded supply chain. "
                "Pick one on the **Scope Setup** page (P-02), then "
                "return here — the picker will be live. For now, use "
                "**Free coordinates** to screen any individual location."
            )
            if st.button(
                "Go to Scope Setup",
                key="p04_noscope_to_p02_supplier",
            ):
                st.switch_page("pages/02_Scope_Setup.py")
    return centre


def _render_free_coordinates_tab() -> dict:
    """Search box + lat/lon number inputs.

    M-P04-Geocode: the search box queries Nominatim and shows up to 5
    top matches as buttons; clicking one fills the lat/lon inputs.
    Manual lat/lon entry still works — direct edits sync back into the
    same session-state defaults so they don't get overwritten on rerun.
    """
    # ── Geocode search row ────────────────────────────────────
    col_query, col_button = st.columns([4, 1])
    with col_query:
        query = st.text_input(
            "Search for a location",
            placeholder='e.g. "São Paulo, Brazil"',
            key="p04_geocode_query",
            label_visibility="collapsed",
        )
    with col_button:
        if st.button("Search", use_container_width=True):
            _run_geocode_search(query)

    _render_geocode_results()

    # ── Lat/lon inputs ────────────────────────────────────────
    # Defaults read from session if a geocode pick set them; otherwise
    # fall back to São Paulo for demo continuity.
    default_lat = st.session_state.get("p04_lat", -23.5505)
    default_lon = st.session_state.get("p04_lon", -46.6333)

    col_lat, col_lon = st.columns(2)
    with col_lat:
        lat = st.number_input(
            "Latitude",
            min_value=-90.0,
            max_value=90.0,
            value=default_lat,
            step=0.0001,
            format="%.4f",
            help="Decimal degrees; range −90 to 90.",
            key="p04_lat_input",
        )
    with col_lon:
        lon = st.number_input(
            "Longitude",
            min_value=-180.0,
            max_value=180.0,
            value=default_lon,
            step=0.0001,
            format="%.4f",
            help="Decimal degrees; range −180 to 180.",
            key="p04_lon_input",
        )
    # Sync the latest user-edited values back into the session defaults
    # so direct edits aren't overwritten on the next rerun.
    st.session_state["p04_lat"] = lat
    st.session_state["p04_lon"] = lon

    return {"lat": lat, "lon": lon}


# ---------------------------------------------------------------------------
# Geocode helpers (M-P04-Geocode)
# ---------------------------------------------------------------------------

def _run_geocode_search(query: str) -> None:
    """Run the geocode; stash results + error in session_state.

    Import the geocoder lazily so the form module doesn't pay the
    ``requests`` import cost on every P-04 render — only when the user
    actually hits Search.
    """
    from ui.components.geocoder import GeocodingError, geocode

    st.session_state.pop("p04_geocode_results", None)
    st.session_state.pop("p04_geocode_error",   None)

    if not query.strip():
        st.session_state["p04_geocode_error"] = "Please enter a place name."
        return

    with st.spinner("Searching…"):
        try:
            results = geocode(query)
        except GeocodingError as exc:
            st.session_state["p04_geocode_error"] = (
                f"Geocoding service unavailable: {exc}. "
                f"You can still enter lat/lon directly below."
            )
            return

    if not results:
        st.session_state["p04_geocode_error"] = (
            f"No matches found for '{query}'. Try a different query."
        )
        return

    st.session_state["p04_geocode_results"] = results


def _render_geocode_results() -> None:
    """Render the pending error message or the result button list."""
    error = st.session_state.get("p04_geocode_error")
    if error:
        st.info(error)
        return

    results = st.session_state.get("p04_geocode_results", [])
    if not results:
        return

    n = len(results)
    st.caption(f"Top {n} match{'es' if n != 1 else ''}. Click to use.")
    for i, result in enumerate(results):
        col_button, col_coords = st.columns([4, 2])
        with col_button:
            if st.button(
                result.display_name,
                key=f"p04_geocode_pick_{i}",
                use_container_width=True,
            ):
                _apply_geocode_pick(result)
        with col_coords:
            st.caption(f"{result.lat:.4f}, {result.lon:.4f}")


def _apply_geocode_pick(result) -> None:
    """Apply a picked geocode result to the lat/lon defaults.

    Pops the lat/lon widget keys so Streamlit re-reads ``value=`` on the
    next rerun rather than restoring the user's previous manual entry —
    same widget-key-refresh pattern the indicator reset uses (M-P04
    polish-2). Also clears the results list and search query so the
    picked location is unambiguously the active one.
    """
    st.session_state["p04_lat"] = result.lat
    st.session_state["p04_lon"] = result.lon
    st.session_state.pop("p04_geocode_results", None)
    st.session_state.pop("p04_geocode_query",   None)
    st.session_state.pop("p04_lat_input",       None)
    st.session_state.pop("p04_lon_input",       None)
    st.rerun()


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


def _pillar_all_selected(
    pillar_ids: list[str] | tuple[str, ...],
    selected:   set[str],
) -> bool:
    """M-DEMO-POLISH: true iff every indicator in the pillar is selected.

    Pure function — extracted from ``_render_pillar_indicators`` so the
    pillar-toggle state can be unit-tested without Streamlit.
    """
    return all(ind in selected for ind in pillar_ids)


def _render_pillar_indicators(pillar: str, label: str) -> None:
    """One pillar's collapsible checkbox grid."""
    pillar_ids = INDICATORS_BY_PILLAR[pillar]
    selected   = st.session_state["p04_selected_indicators"]
    # M-P04 polish-2 — generation versions each checkbox key.
    generation = st.session_state["p04_indicator_generation"]
    n_total    = len(pillar_ids)
    n_selected = sum(1 for ind in pillar_ids if ind in selected)
    all_in_pillar_selected = _pillar_all_selected(pillar_ids, selected)

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
        # M-DEMO-POLISH: pillar-level select-all toggle. Streamlit
        # checkboxes don't support an indeterminate state, so the
        # toggle is unchecked whenever the pillar's selection is a
        # strict subset — the honest representation. Toggling drives
        # the same generation-counter pattern as the global reset
        # buttons so the per-indicator widgets below refresh cleanly.
        new_all = st.checkbox(
            f"**Select all {label}**",
            value=all_in_pillar_selected,
            key=f"p04_pillar_all_{pillar}_v{generation}",
        )
        if new_all and not all_in_pillar_selected:
            selected.update(pillar_ids)
            st.session_state["p04_indicator_generation"] += 1
            st.rerun()
        elif not new_all and all_in_pillar_selected:
            for ind in pillar_ids:
                selected.discard(ind)
            st.session_state["p04_indicator_generation"] += 1
            st.rerun()

        st.divider()

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
    """Summary line + validation + window picker + run buttons.

    M-UI-A3: the analysis-window picker renders inside this section so
    every scope-aware form (no-scope / supply-chain / region) gets it
    automatically. Run is disabled if the picker reports validation
    errors (returns None).
    """
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

        if centre is not None and n_indicators == 0:
            st.warning(
                "At least one indicator must be selected. Use the "
                "**Reset to all** button above to restore the default."
            )

        # M-UI-A3 — user-configurable analysis window.
        window = render_analysis_window_picker(
            profile_name="screening",
            key_prefix="p04_window",
            aoi_buffer_km=float(radius_km) if centre is not None else None,
            saved_window=_pre_filled_saved_window(),
        )

        # Run is enabled only when centre / indicators / window are all OK.
        can_run = (
            centre is not None
            and n_indicators >= 1
            and window is not None
        )

        col_screening, col_trend = st.columns(2)
        with col_screening:
            if st.button(
                "Run Screening",
                type="primary",
                disabled=not can_run,
                use_container_width=True,
            ):
                _commit_and_navigate(centre, radius_km, indicators, window)
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


def _pre_filled_saved_window() -> tuple[str, str] | None:
    """WP11: when the user landed on P-04 after loading a saved analysis
    (which writes ``screening_setup`` into session state), surface that
    saved analysis's window in the picker so the user sees what was
    originally run and can decide whether to keep it or change.

    Returns None on first visit (no prior setup) so the picker uses its
    profile default.
    """
    setup = st.session_state.get("screening_setup")
    if not isinstance(setup, dict):
        return None
    tr = setup.get("time_range")
    if not (isinstance(tr, (list, tuple)) and len(tr) == 2):
        return None
    return (str(tr[0]), str(tr[1]))


# ---------------------------------------------------------------------------
# M-P04-ACTIVATE — scope-aware forms
# ---------------------------------------------------------------------------

def _render_scope_header(label: str, sublabel: str) -> None:
    """Header strip showing the loaded scope + a "Change scope" link.

    Rendered at the top of the supply-chain and region scoped forms.
    The link routes back to P-02 and clears its local stage state so
    the user lands on a fresh Mode Pick.
    """
    with st.container(border=True):
        col_meta, col_change = st.columns([4, 1])
        with col_meta:
            st.markdown(f"### {label}")
            st.caption(sublabel)
        with col_change:
            if st.button(
                "Change scope",
                use_container_width=True,
                help="Pick a different scope on the Scope Setup page (P-02).",
            ):
                st.session_state.pop("p02_stage",         None)
                st.session_state.pop("p02_pending_scope", None)
                st.switch_page("pages/02_Scope_Setup.py")


def _render_supply_chain_scoped_form(chain) -> None:
    """P-04 form for a Supply Chain scope: header → node picker →
    radius slider → indicators → run. Ad-hoc escape link below.
    """
    _render_scope_header(
        label=chain.name,
        sublabel=(
            f"{chain.industry} · {len(chain.nodes)} nodes · {chain.country}"
        ),
    )

    centre = _render_node_picker(chain)
    if centre is None:
        return

    radius_km  = _render_radius_section()
    indicators = _render_indicator_section()
    _render_run_section(centre, radius_km, indicators)
    _render_ad_hoc_link(centre)


def _render_node_picker(chain) -> dict | None:
    """Dropdown of nodes in the loaded chain. Returns the picked node's
    ``{lat, lon, node_id, node_name}``, or ``None`` if the chain is empty
    (defensive — shouldn't happen with curated demo data).

    M-P10-POLISH: also exposes ``node_id`` and ``node_name`` so the run
    commit can stash them on ``centre_metadata`` for the save-name
    builder to read.
    """
    if not chain.nodes:
        st.error(
            "This supply chain has no nodes. Change scope or use free "
            "coordinates instead."
        )
        return None

    with st.container(border=True):
        st.markdown("### Node")
        labels = [f"{n.name} ({n.tier})" for n in chain.nodes]
        pick_idx = st.selectbox(
            "Pick a node to screen",
            options=range(len(chain.nodes)),
            format_func=lambda i: labels[i],
            key="p04_node_pick",
        )
        node = chain.nodes[pick_idx]
        st.caption(
            f"Coordinates: ({node.lat:.4f}, {node.lon:.4f})"
            + (f" · {node.notes}" if node.notes else "")
        )
    return {
        "lat":       node.lat,
        "lon":       node.lon,
        "node_id":   node.id,    # M-P10-POLISH
        "node_name": node.name,  # M-P10-POLISH
    }


def _render_region_scoped_form(region) -> None:
    """P-04 form for a Region scope: header → locked centroid/radius
    display → indicators → run. Ad-hoc escape link below.

    The radius is dictated by the region polygon and not user-adjustable
    — that's the whole point of the Region mode. The "Use free coords"
    link is the override path for users who want a tighter buffer.
    """
    _render_scope_header(
        label=f"{region.name}, {region.country}",
        sublabel=(
            f"Centroid: ({region.centroid_lat:.4f}, "
            f"{region.centroid_lon:.4f})"
        ),
    )

    _render_locked_region_aoi(region)
    centre    = {"lat": region.centroid_lat, "lon": region.centroid_lon}
    radius_km = region.radius_km

    indicators = _render_indicator_section()
    _render_run_section(centre, radius_km, indicators)
    _render_ad_hoc_link(centre)


def _render_locked_region_aoi(region) -> None:
    """Read-only display of the region's centroid + buffer."""
    with st.container(border=True):
        st.markdown("### Screening area")
        col_centroid, col_radius = st.columns(2)
        with col_centroid:
            st.metric(
                "Centroid",
                f"{region.centroid_lat:.4f}, {region.centroid_lon:.4f}",
            )
        with col_radius:
            st.metric(
                "Buffer",
                f"{region.radius_km} km",
                delta=("capped" if region.is_capped else None),
                delta_color="off",
            )
        if region.is_capped:
            st.caption(
                f"This region's natural radius is "
                f"{region.natural_radius_km} km — larger than the "
                f"{region.radius_km} km representative-buffer cap. "
                f"The screening covers a representative portion centred "
                f"on the centroid."
            )
        else:
            st.caption(
                "The buffer is sized to match the region's area; "
                "screening covers the whole region."
            )


def _render_ad_hoc_link(centre: dict) -> None:
    """Below-scope link to fall back to the no-scope (three-tab) form.

    Sets ``scope.kind = "none"`` explicitly (rather than clearing the
    key) so the user lands consistently in no-scope mode on subsequent
    P-04 visits within the same session. Seeds ``p04_lat`` / ``p04_lon``
    so the free-coords form opens pre-filled with the current centre.
    """
    st.write("")
    if st.button(
        "Use free coordinates instead",
        help=(
            "Drop the scope binding and edit lat/lon freely. The current "
            "centre will be pre-filled."
        ),
    ):
        st.session_state["p04_lat"] = centre["lat"]
        st.session_state["p04_lon"] = centre["lon"]
        st.session_state["scope"]   = {"kind": "none", "data": None}
        st.rerun()


# ---------------------------------------------------------------------------
# Run commit
# ---------------------------------------------------------------------------

def _source_for_scope(scope: dict | None) -> str:
    """Build the ``centre_metadata.source`` string from the active scope.

    P-05's C1 header surfaces this; making it scope-aware means the
    result page reads e.g. "Source: P-04 region scope · Pará, Brazil"
    instead of a generic label.
    """
    if scope is None or scope.get("kind") == "none":
        return "P-04 free coordinates"
    kind = scope.get("kind")
    data = scope.get("data")
    if kind == "supply_chain" and data is not None:
        return f"P-04 supply-chain scope · {data.name}"
    if kind == "region" and data is not None:
        return f"P-04 region scope · {data.name}, {data.country}"
    return "P-04 setup"


def _commit_and_navigate(
    centre:     dict,
    radius_km:  int,
    indicators: set[str],
    window:     WindowSelection,
) -> None:
    """Write ``screening_setup`` in the shape P-05 reads, then navigate.

    M-P04-ACTIVATE: ``centre_metadata.source`` reflects the active scope.
    M-P10-POLISH: scope-specific identifiers (node id/name, region
    name/country) thread into ``centre_metadata`` so the save-name
    builder can produce human-readable names. The ``centre`` field
    itself stays clean as ``{lat, lon}``.
    M-UI-A3: ``time_range`` now comes from the user's window picker
    selection rather than a hard-coded 90-day window.
    """
    scope = st.session_state.get("scope")
    source = _source_for_scope(scope)

    centre_metadata: dict = {"source": source}
    # M-P10-POLISH — supply-chain saves carry node_id + node_name.
    if "node_id" in centre or "node_name" in centre:
        centre_metadata["node_id"]   = centre.get("node_id")
        centre_metadata["node_name"] = centre.get("node_name")
    # M-P10-POLISH — region saves carry region_name + country.
    if scope is not None and scope.get("kind") == "region":
        region = scope.get("data")
        if region is not None:
            centre_metadata["region_name"] = region.name
            centre_metadata["country"]     = region.country

    start_iso, end_iso = window.as_iso_tuple()
    st.session_state["screening_setup"] = {
        # Strip auxiliary fields from centre so it stays {lat, lon} —
        # downstream code (P-05 C1 header, engine ScreeningRun) keys on
        # the clean shape.
        "centre":          {"lat": centre["lat"], "lon": centre["lon"]},
        "radius_km":       radius_km,
        "time_range":      [start_iso, end_iso],
        "indicators":      sorted(indicators),
        "mode":            "screening",
        "centre_metadata": centre_metadata,
    }
    # Drop any leftover P-05 page_state so the screening re-enters
    # S1_Computing with a fresh run_id.
    st.session_state.pop("page_state", None)
    st.switch_page("pages/05_Screening_Results.py")
