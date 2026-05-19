"""C8 — action bar (M-UI-E.5).

Two buttons at the bottom of P-05:
  - **Save as report** pushes the screening result into
    ``st.session_state["saved_analyses"]`` (a list, initialised on
    first save). Entry shape mirrors the planned P-10 row schema.
  - **Switch to Trend** is disabled until P-06 (Trend View) exists.

The save is half-real: it persists for the browser session via
Streamlit's session_state, but does NOT survive a page reload or a
sign-out. Full localStorage persistence per PLFS_v4 §14 lands in its
own milestone.

Authority: docs/Wireframes_All_v4.md §P-05 C8.
"""

# M-UI-E.5
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import streamlit as st


def render_c8_action_bar(payload: dict) -> None:
    """Render the action bar — Save as report + Switch to Trend."""
    with st.container(border=True):
        col_save, col_trend = st.columns(2)
        with col_save:
            if st.button(
                "Save as report",
                use_container_width=True,
                type="primary",
            ):
                _save_as_report(payload)
        with col_trend:
            st.button(
                "Switch to Trend",
                use_container_width=True,
                disabled=True,
                help=(
                    "Trend View (P-06) lands in a later milestone. "
                    "Until then, screening is the only mode."
                ),
            )


def _save_as_report(payload: dict) -> None:
    """Push the result onto ``st.session_state["saved_analyses"]``.

    Entry schema matches the v1.x P-10 list-view row shape (id, name,
    type, scope, date_saved, payload). Auto-generated name uses the
    AOI centre coordinates + a UTC timestamp.
    """
    if "saved_analyses" not in st.session_state:
        st.session_state["saved_analyses"] = []

    setup = st.session_state.get("screening_setup", {})
    centre = setup.get("centre", {})
    lat = centre.get("lat", 0.0)
    lon = centre.get("lon", 0.0)
    now = datetime.now(timezone.utc)

    entry = {
        "id":   str(uuid.uuid4()),
        "name": (
            f"Screening @ ({lat:.4f}, {lon:.4f}) "
            f"— {now.strftime('%Y-%m-%d %H:%M UTC')}"
        ),
        "type":  "screening",
        "scope": {
            "centre":    centre,
            "radius_km": setup.get("radius_km"),
        },
        "date_saved": now.isoformat(),
        "payload":    payload,
    }
    st.session_state["saved_analyses"].append(entry)

    st.toast(
        f"Saved as report — '{entry['name']}'.",
        icon="💾",
    )
