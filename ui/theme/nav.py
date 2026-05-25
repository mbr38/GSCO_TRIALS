"""Persistent top nav — used on P-02..P-11 (not on P-01 landing).

Layout (per Wireframes Appendix B):
    [ brand mark | scope chip ]  [ module links ]  [ user-type chip | sign out ]

The three module links are rendered via ``streamlit-option-menu`` so we
get a single horizontal control with built-in selection state, then
restyled to match the reference site (transparent container,
muted text, accent-green selection).

Page keys passed to ``render_top_nav`` and returned on click:
    "P-09" -> Indicator Library
    "P-10" -> Saved Analyses
    "P-11" -> Reports
"""

from __future__ import annotations

import html
from typing import Optional

import streamlit as st
from streamlit_option_menu import option_menu

from .tokens import COLORS, FONTS

# Public mapping: page key -> (label, icon). The order here is the
# left-to-right order in the rendered nav.
NAV_ITEMS: list[tuple[str, str, str]] = [
    ("P-09", "Indicator Library", "book"),
    ("P-10", "Saved Analyses", "folder"),
    ("P-11", "Reports", "file-earmark-text"),
]

_LABEL_TO_KEY = {label: key for key, label, _ in NAV_ITEMS}


def _clear_session() -> None:
    """Sign-out hook — wipes session state. Pages should pick up the
    cleared state on rerun and redirect back to P-01."""
    st.session_state.clear()


def _chip(text: str, color: str = COLORS["text_secondary"]) -> str:
    return (
        f"<span style=\""
        f"display: inline-block;"
        f"padding: 0.25rem 0.6rem;"
        f"border: 1px solid {COLORS['card_border']};"
        f"border-radius: 999px;"
        f"font-family: {FONTS['sans_body']};"
        f"font-size: 0.75rem;"
        f"color: {color};"
        f"background: {COLORS['card_bg']};"
        f"\">{html.escape(text)}</span>"
    )


def render_top_nav(
    active_page: str,
    scope_name: Optional[str],
    user_type: Optional[str],
) -> Optional[str]:
    """Render the persistent top nav. Returns the page-key the user
    clicked (one of "P-09" / "P-10" / "P-11"), or ``None`` if the
    selection did not change this rerun.
    """
    default_index = 0
    for i, (key, _label, _icon) in enumerate(NAV_ITEMS):
        if key == active_page:
            default_index = i
            break

    labels = [label for _, label, _ in NAV_ITEMS]
    icons = [icon for _, _, icon in NAV_ITEMS]

    col_brand, col_menu, col_right = st.columns([2, 4, 2])

    with col_brand:
        brand_html = (
            f"<div style=\""
            f"display: flex; align-items: center; gap: 0.75rem;"
            f"font-family: {FONTS['serif_display']};"
            f"font-size: 1.15rem;"
            f"color: {COLORS['text_primary']};"
            f"\">"
            f"<span style=\"color: {COLORS['accent_green']};\">◉</span>"
            f"GSCO"
        )
        if scope_name:
            brand_html += f"<span style=\"margin-left: 0.5rem;\">{_chip(scope_name)}</span>"
        brand_html += "</div>"
        st.markdown(brand_html, unsafe_allow_html=True)

    with col_menu:
        selected_label = option_menu(
            menu_title=None,
            options=labels,
            icons=icons,
            orientation="horizontal",
            default_index=default_index,
            styles={
                "container": {
                    "background-color": "transparent",
                    "padding": "0",
                    "margin": "0",
                },
                "icon": {"color": COLORS["text_secondary"], "font-size": "14px"},
                "nav-link": {
                    "color": COLORS["text_secondary"],
                    "font-family": FONTS["sans_body"],
                    "font-size": "14px",
                    "background-color": "transparent",
                    "padding": "0.5rem 1rem",
                    "margin": "0 0.25rem",
                    "--hover-color": "rgba(123, 195, 66, 0.06)",
                },
                "nav-link-selected": {
                    "background-color": "transparent",
                    "color": COLORS["accent_green"],
                    "font-weight": "600",
                },
            },
        )

    with col_right:
        chips = []
        if user_type:
            chips.append(_chip(user_type, color=COLORS["accent_green"]))
        right_html = (
            "<div style=\"display: flex; justify-content: flex-end; align-items: center; gap: 0.5rem;\">"
            + "".join(chips)
            + "</div>"
        )
        st.markdown(right_html, unsafe_allow_html=True)
        if st.button("Sign out", key="_gsco_signout", type="secondary"):
            _clear_session()
            st.rerun()

    st.markdown("<hr/>", unsafe_allow_html=True)

    new_key = _LABEL_TO_KEY.get(selected_label)
    if new_key and new_key != active_page:
        return new_key
    return None
