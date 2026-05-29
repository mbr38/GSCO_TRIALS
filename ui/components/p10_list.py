"""P-10 Saved Analyses renderers (M-P10).

List view of saved screenings with Open / Delete / Export JSON actions.
Delete uses ``st.dialog`` for confirmation (Streamlit 1.36+).

Public surface is ``render_saved_analyses``; the per-row helpers and the
dialog are private. The action handlers (``_open_save``,
``_apply_delete``, ``_format_row_caption``) are extracted so they can be
unit-tested without Streamlit.

Authority: docs/Wireframes_All_v4.md §P-10.
"""

# M-P10
from __future__ import annotations

import json

import streamlit as st

from ui.components.trend_record import trend_search_indicator


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_saved_analyses() -> None:
    """Top-level renderer for P-10."""
    saves = st.session_state.get("saved_analyses", [])
    if not saves:
        _render_empty_state()
        return

    # M-UX-A1 (2.7) — free-text search above the list. Client-side
    # filter-on-rerun (UX7): the saved-analyses list is small (<500 in
    # v1.x), so a pure in-memory substring scan is instant and needs no
    # query layer or debounce machinery (matches the P-09 search pattern).
    query = st.text_input(
        "Search saved analyses",
        placeholder="Search by name, supplier, or location…",
        key="p10_search",
        label_visibility="collapsed",
    )

    matches = _filter_saves(saves, query)

    if not matches:
        # UX5 / test-plan 6.2 — non-matching input shows an empty state.
        st.caption(
            f"No saved analyses match “{query.strip()}”. "
            f"Clear the search to see all {len(saves)}."
        )
        return

    n = len(matches)
    if query.strip():
        st.caption(
            f"{n} of {len(saves)} saved analys{'is' if n == 1 else 'es'} "
            f"match “{query.strip()}”."
        )
    else:
        st.caption(
            f"{n} saved analys{'is' if n == 1 else 'es'}. "
            f"Saves persist for the duration of your session — use Export "
            f"JSON to keep a permanent copy."
        )
    st.divider()
    for save in matches:
        _render_save_row(save)


# ---------------------------------------------------------------------------
# Search (pure, testable) — M-UX-A1 (2.7)
# ---------------------------------------------------------------------------

def _save_search_fields(save: dict) -> list[str]:
    """Return the three searchable strings for a save (UX4).

    Name + supplier (``centre_metadata.node_name``) + location
    (``centre_metadata.source``). Defensive ``.get`` chains: prioritisation
    entries and older/stub saves may lack ``centre_metadata``, in which case
    only the name participates. Missing fields contribute nothing rather
    than raising.
    """
    setup  = save.get("screening_setup") or save.get("prioritisation_setup") or {}
    centre = setup.get("centre_metadata") or {}
    return [
        str(save.get("name") or ""),
        str(centre.get("node_name") or ""),
        str(centre.get("source") or ""),
        # M-TREND-A2 (UT9): trend saves also match on their indicator id +
        # display name; empty for screening / prioritisation records.
        trend_search_indicator(save),
    ]


def _matches_search(save: dict, query: str) -> bool:
    """True if ``query`` (case-insensitive substring) appears in any of the
    save's searchable fields (UX5 — OR-combined). Leading/trailing
    whitespace is stripped; an empty query matches everything."""
    q = query.strip().lower()
    if not q:
        return True
    return any(q in field.lower() for field in _save_search_fields(save))


def _filter_saves(saves: list[dict], query: str) -> list[dict]:
    """Filter the saves list by the search query, preserving order.

    Empty / whitespace-only query returns the full list unchanged (UX6).
    """
    return [s for s in saves if _matches_search(s, query)]


# ---------------------------------------------------------------------------
# Row rendering
# ---------------------------------------------------------------------------

def _render_empty_state() -> None:
    """Shown when saved_analyses is empty."""
    st.info(
        "No saved analyses yet. From a screening result, click "
        "**Save as report** to add it here."
    )


def _render_save_row(save: dict) -> None:
    """One row in the list: meta + three action buttons."""
    save_id = save["id"]
    with st.container(border=True):
        col_meta, col_actions = st.columns([3, 2])
        with col_meta:
            st.markdown(f"**{save['name']}**")
            st.caption(_format_row_caption(save))
        with col_actions:
            col_open, col_delete, col_export = st.columns(3)
            with col_open:
                if st.button(
                    "Open", use_container_width=True,
                    key=f"p10_open_{save_id}",
                ):
                    _open_save(save)
            with col_delete:
                if st.button(
                    "Delete", use_container_width=True,
                    key=f"p10_delete_{save_id}",
                ):
                    _delete_dialog(save_id, save["name"])
            with col_export:
                _render_export_button(save)


def _format_row_caption(save: dict) -> str:
    """Build the per-row meta caption.

    Pure function — testable without Streamlit. Falls back to dashes when
    any field is missing (covers stub seed entries cleanly).

    M-P08.4: dispatches on ``type`` so prioritisation entries get a
    batch-level caption. Default ``"screening"`` preserves the M-P10
    shape for entries written before the type field existed.
    """
    if save.get("type") == "prioritisation":
        return _format_prioritisation_caption(save)
    if save.get("type") == "trend":
        return _format_trend_caption(save)
    setup = save.get("screening_setup") or {}
    centre = setup.get("centre") or {}
    lat = centre.get("lat")
    lon = centre.get("lon")
    radius_km = setup.get("radius_km", "—")
    coord_str = (
        f"{lat:.4f}, {lon:.4f}"
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float))
        else "—"
    )
    n_indicators = len(setup.get("indicators", []))
    date_str = (save.get("date_saved") or "")[:10] or "—"
    window_str = _format_window_segment(setup.get("time_range"))  # M-UI-A3
    return (
        f"Centre: {coord_str} · Buffer: {radius_km} km · "
        f"Indicators: {n_indicators} · {window_str} · Saved: {date_str}"
    )


# M-TREND-A2
def _format_trend_caption(save: dict) -> str:
    """Per-row caption for ``type=="trend"`` entries."""
    result = save.get("trend_result") or {}
    bucket = result.get("significance_bucket") or "—"
    cov = result.get("coverage") or {}
    n = cov.get("n_valid_days", "—")
    indicator = save.get("display_name") or save.get("indicator_id") or "—"
    date_str = (save.get("date_saved") or "")[:10] or "—"
    return (
        f"Trend · {indicator} · {bucket} · {n} valid days · {date_str}"
    )


# M-P08.4
def _format_prioritisation_caption(save: dict) -> str:
    """Per-row caption for ``type=="prioritisation"`` entries."""
    summary = save.get("summary") or {}
    setup   = save.get("prioritisation_setup") or {}
    n_total = summary.get("n_total", 0)
    radius  = setup.get("radius_km", "—")
    date_str = (save.get("date_saved") or "")[:10] or "—"
    window_str = _format_window_segment(setup.get("time_range"))  # M-UI-A3
    return (
        f"Prioritisation · {n_total} suppliers · "
        f"{radius} km buffer · {window_str} · {date_str}"
    )


# M-UI-A3
def _format_window_segment(time_range) -> str:
    """Format ``time_range`` for the per-row caption.

    Returns ``"Window: N days (start → end)"`` when both ends parse,
    or ``"Window: —"`` when missing / malformed (covers older saves
    written before the picker existed). Pure helper for testability.
    """
    if not (isinstance(time_range, (list, tuple)) and len(time_range) == 2):
        return "Window: —"
    start_s, end_s = str(time_range[0]), str(time_range[1])
    try:
        from datetime import date
        days = (date.fromisoformat(end_s) - date.fromisoformat(start_s)).days
    except (ValueError, TypeError):
        return "Window: —"
    return f"Window: {days} d ({start_s} → {end_s})"


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _open_save(save: dict) -> None:
    """Hydrate session state from the saved entry and route to its page.

    M-P08.4: dispatches on ``type`` — prioritisation entries route to
    P-08, screening entries (the original M-P10 path, also the
    default) route to P-05. Stub seeds (missing setup or payload)
    still short-circuit with a UI error.
    """
    if save.get("type") == "prioritisation":
        _open_prioritisation(save)
        return
    if save.get("type") == "trend":
        # M-TREND-A2 (UT9): re-open a saved trend on the dedicated P-06 page;
        # it renders from the stored per-day series with no recompute.
        st.session_state["loaded_trend_record"] = save
        st.switch_page("pages/06_Trend_View.py")
        return
    setup = save.get("screening_setup")
    payload = save.get("payload")
    if not setup or not payload:
        st.error(
            "This save is missing data — likely a stub. Generate the "
            "real seed file via the demo prep workflow."
        )
        return
    from ui.page_state import PageState
    st.session_state["screening_setup"] = setup
    st.session_state["page_state"] = PageState(
        name="S2_Results",
        run_id=f"opened-{save['id']}",
        result=payload,
        failures=payload.get("_failures"),
    )
    st.switch_page("pages/05_Screening_Results.py")


# M-P08.4
def _open_prioritisation(save: dict) -> None:
    """Rehydrate ``prioritisation_state`` from a saved entry, route to P-08.

    Defensive: a stub or partly-populated entry without supplier_results
    still opens; the page renders an empty results table rather than
    crashing.
    """
    from ui.prioritisation_state import (
        PrioritisationState,
        PrioritisationStateKind,
        SupplierResult,
    )

    setup = save.get("prioritisation_setup")
    if not setup:
        st.error(
            "This save is missing setup data — can't reopen the batch."
        )
        return

    supplier_results = [
        SupplierResult(**r) for r in (save.get("supplier_results") or [])
    ]
    summary = save.get("summary") or {}

    state = PrioritisationState(
        kind=PrioritisationStateKind.S3_RESULTS,
        setup=setup,
        supplier_results=supplier_results,
        completed_count=summary.get("n_total", len(supplier_results)),
        total_count=summary.get("n_total", len(supplier_results)),
        cancelled=summary.get("n_cancelled", 0) > 0,
    )
    st.session_state["prioritisation_state"] = state
    st.session_state["prioritisation_setup"] = setup
    st.switch_page("pages/08_Prioritisation_Results.py")


def _apply_delete(saves: list[dict], save_id: str) -> list[dict]:
    """Return a new list with the matching id removed.

    Pure function — testable without Streamlit. Preserves order.
    """
    return [s for s in saves if s.get("id") != save_id]


@st.dialog("Confirm delete")
def _delete_dialog(save_id: str, save_name: str) -> None:
    """Modal dialog for delete confirmation. Streamlit 1.36+."""
    st.markdown(f"Delete **{save_name}**?")
    st.caption("This cannot be undone.")
    col_cancel, col_confirm = st.columns(2)
    with col_cancel:
        if st.button("Cancel", use_container_width=True):
            st.rerun()
    with col_confirm:
        if st.button(
            "Delete", type="primary", use_container_width=True,
        ):
            saves = st.session_state.get("saved_analyses", [])
            st.session_state["saved_analyses"] = _apply_delete(saves, save_id)
            st.toast(f"Deleted '{save_name}'.", icon="🗑️")
            st.rerun()


def _render_export_button(save: dict) -> None:
    """Render the Export JSON button. Streamlit's ``download_button``
    handles the file-save dialog browser-side.
    """
    blob = json.dumps(save, indent=2, sort_keys=True, default=str)
    st.download_button(
        "Export JSON",
        data=blob,
        file_name=f"{save['id']}.json",
        mime="application/json",
        use_container_width=True,
        key=f"p10_export_{save['id']}",
    )
