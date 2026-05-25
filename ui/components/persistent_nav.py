"""Persistent navigation strip (M-P0103).

Shared across every authenticated page. Renders the brand mark
(GSCO logo) on the left, then the user-type chip, the loaded-scope
chip with a "Change scope" link, and the sign-out button. Replaces
the per-page ``_render_nav`` helpers that pages 02, 04, 05 (and the
scratch page) inlined before this milestone.

The scope-chip label is built by ``_scope_chip_label``, a pure
function that takes the M-P02 scope dict and returns the
``(label, button_label)`` pair. Extracted so the wording can be
unit-tested without standing up Streamlit.

Authority: docs/Wireframes_All_v4.md Appendix B; M-P0103 design
decisions.
"""

# M-P0103
from __future__ import annotations

from pathlib import Path

import streamlit as st

from utils.state import sign_out

# Brand-mark asset. Three .parent hops to reach the repo root:
# ui/components/persistent_nav.py -> ui/components -> ui -> <repo root>
_LOGO_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "gsco_logo.png"
_LOGO_WIDTH_PX = 120  # tune via visual diff; aspect ~2.23:1 -> ~54px tall


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_persistent_nav() -> None:
    """Standard top nav: brand mark, user-type chip, scope chip, sign-out."""
    col_brand, col_user, col_scope, col_signout = st.columns([1, 2, 5, 1])
    with col_brand:
        _render_brand_mark()
    with col_user:
        _render_user_type_chip()
    with col_scope:
        _render_scope_chip()
    with col_signout:
        if st.button(
            "Sign out",
            use_container_width=True,
            key="nav_signout",
        ):
            sign_out()
            st.switch_page("app.py")


# ---------------------------------------------------------------------------
# Brand mark
# ---------------------------------------------------------------------------

def _render_brand_mark() -> None:
    """GSCO logo, leftmost in the nav per Wireframes Appendix B.

    Falls back to a "GSCO" caption if the asset is missing so the nav
    keeps rendering during local dev before the PNG is dropped in.
    """
    if _LOGO_PATH.exists():
        st.image(str(_LOGO_PATH), width=_LOGO_WIDTH_PX)
    else:
        st.caption("**GSCO**")


# ---------------------------------------------------------------------------
# Chips
# ---------------------------------------------------------------------------

def _render_user_type_chip() -> None:
    """The "Signed in as X · Session …" caption."""
    label      = st.session_state.get("user_type_label", "—")
    session_id = st.session_state.get("session_id",      "—")
    st.caption(f"Signed in as **{label}**  ·  Session `{session_id}`")


def _render_scope_chip() -> None:
    """Loaded-scope display + Change-scope link.

    Reads ``st.session_state["scope"]`` (the M-P02 shape) and renders
    the matching label + button. The button always routes to P-02
    after clearing P-02-local stage state so the user lands fresh on
    Mode Pick (not mid-Preview from a previous visit).
    """
    label, button_label = _scope_chip_label(st.session_state.get("scope"))
    col_label, col_button = st.columns([4, 1])
    with col_label:
        st.caption(label)
    with col_button:
        if st.button(
            button_label,
            use_container_width=True,
            key="nav_change_scope",
        ):
            st.session_state.pop("p02_stage",         None)
            st.session_state.pop("p02_pending_scope", None)
            st.switch_page("pages/02_Scope_Setup.py")


def _scope_chip_label(scope: dict | None) -> tuple[str, str]:
    """Return ``(chip_label, button_label)`` for the given scope dict.

    Pure function; testable without Streamlit. Four branches:

    - ``None`` or ``{"kind": "none"}``  → "Scope: not set" / "Pick scope"
    - ``{"kind": "supply_chain"}``      → "Scope: <name>"        / "Change"
    - ``{"kind": "region"}``            → "Scope: <name>, <country>" / "Change"
    - Anything else                     → defensive fallback "Scope: —"
    """
    if scope is None or scope.get("kind") == "none":
        return ("Scope: not set", "Pick scope")
    kind = scope.get("kind")
    data = scope.get("data")
    if kind == "supply_chain" and data is not None:
        return (f"Scope: {data.name}", "Change")
    if kind == "region" and data is not None:
        return (f"Scope: {data.name}, {data.country}", "Change")
    return ("Scope: —", "Pick scope")
