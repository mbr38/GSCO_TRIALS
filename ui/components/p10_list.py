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


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_saved_analyses() -> None:
    """Top-level renderer for P-10."""
    saves = st.session_state.get("saved_analyses", [])
    if not saves:
        _render_empty_state()
        return

    st.caption(
        f"{len(saves)} saved analys{'is' if len(saves) == 1 else 'es'}. "
        f"Saves persist for the duration of your session — use Export "
        f"JSON to keep a permanent copy."
    )
    st.divider()
    for save in saves:
        _render_save_row(save)


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
    """
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
    return (
        f"Centre: {coord_str} · Buffer: {radius_km} km · "
        f"Indicators: {n_indicators} · Saved: {date_str}"
    )


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _open_save(save: dict) -> None:
    """Hydrate session state from the saved entry and route to P-05.

    Stub seeds (missing setup or payload) short-circuit with a UI error
    — Phase 2 demo prep replaces the stubs with real screening data.
    """
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
