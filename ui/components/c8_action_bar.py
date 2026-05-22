"""C8 — action bar (M-UI-E.5 / M-P11.4).

Two buttons at the bottom of P-05:
  - **Save as report** pushes the screening result into
    ``st.session_state["saved_analyses"]`` (a list, initialised on
    first save). Entry shape mirrors the planned P-10 row schema.
    M-P11.4: after a successful save, a sticky banner surfaces with
    an "Open in Reports" button that routes to P-11 with the
    just-saved source pre-selected.
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

from ui.p11_state import route_to_p11_with_source


# M-P11.4: sentinel key on session_state that survives the rerun.
_SAVE_BANNER_KEY = "c8_last_saved_for_p11"


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

        # M-P11.4: post-save banner. Rendered whenever the sentinel
        # is set, so it survives reruns until the user clicks Open
        # in Reports (which routes away) or runs a fresh screening.
        _render_post_save_banner()


# M-P11.4
def _render_post_save_banner() -> None:
    pending = st.session_state.get(_SAVE_BANNER_KEY)
    if not pending:
        return
    st.success(
        f"Saved as **{pending['name']}**.",
        icon="💾",
    )
    if st.button(
        "📄 Open in Reports",
        key=f"c8_open_in_reports_{pending['id']}",
        use_container_width=True,
    ):
        route_to_p11_with_source(st.session_state, pending["id"])
        st.session_state.pop(_SAVE_BANNER_KEY, None)
        st.switch_page("pages/11_Reports.py")


def _save_as_report(payload: dict) -> None:
    """Push the result onto ``st.session_state["saved_analyses"]``.

    Entry schema matches the P-10 list-view row shape (id, name, type,
    screening_setup, date_saved, payload). The display name is built by
    ``_build_save_name`` from the active scope + setup metadata so
    supply-chain and region saves get readable names — see that
    function's docstring for the precedence rules.

    M-P10: the entry stores the full ``screening_setup`` (not just a
    scope subset) so P-10's Open action can hydrate session state and
    re-render P-05 with no information loss.

    M-P10-POLISH: the UUID is generated per-call (verified) and the
    name builder reads the loaded scope + ``centre_metadata`` to
    produce human-readable names.
    """
    if "saved_analyses" not in st.session_state:
        st.session_state["saved_analyses"] = []

    setup = st.session_state.get("screening_setup", {})
    scope = st.session_state.get("scope")
    now = datetime.now(timezone.utc)

    entry = {
        "id":              str(uuid.uuid4()),  # M-P10-POLISH: per-call.
        "name":            _build_save_name(setup, scope, now),
        "type":            "screening",
        "screening_setup": setup,  # M-P10: full setup, not just scope.
        "date_saved":      now.isoformat(),
        "payload":         payload,
    }
    st.session_state["saved_analyses"].append(entry)

    # M-P11.4: stash the just-saved entry so the post-save banner
    # (rendered on the next rerun) can offer "Open in Reports".
    st.session_state[_SAVE_BANNER_KEY] = {
        "id":   entry["id"],
        "name": entry["name"],
    }
    st.toast(
        f"Saved as report — '{entry['name']}'.",
        icon="💾",
    )


# M-P10-POLISH
def _build_save_name(
    setup: dict,
    scope: dict | None,
    now:   datetime,
) -> str:
    """Build a human-readable save name from loaded scope + setup.

    Precedence:

    1. **Supply chain** scope with a node name on ``centre_metadata`` →
       "<node name> — <chain name>".
    2. **Region** scope with a region name + country on
       ``centre_metadata`` → "<region>, <country> — Region screening".
    3. **Fallback** (no scope, ``scope.kind == "none"``, missing
       metadata, or any unexpected shape) → the original coordinate +
       timestamp format.

    Pure function — testable without Streamlit. The ``now`` argument is
    passed in so tests can pin a deterministic timestamp.
    """
    metadata = setup.get("centre_metadata") or {}

    if scope and scope.get("kind") == "supply_chain":
        node_name  = metadata.get("node_name")
        chain_data = scope.get("data")
        if node_name and chain_data is not None:
            return f"{node_name} — {chain_data.name}"

    if scope and scope.get("kind") == "region":
        region_name = metadata.get("region_name")
        country     = metadata.get("country")
        if region_name and country:
            return f"{region_name}, {country} — Region screening"

    # Fallback: coordinate + UTC timestamp.
    centre = setup.get("centre") or {}
    lat = centre.get("lat", 0.0)
    lon = centre.get("lon", 0.0)
    return (
        f"Screening @ ({lat:.4f}, {lon:.4f}) "
        f"— {now.strftime('%Y-%m-%d %H:%M UTC')}"
    )
