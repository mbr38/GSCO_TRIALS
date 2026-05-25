"""Card primitives — reference-faithful feature cards.

The reference site styles all feature cards identically regardless of the
icon color. The only per-card differentiator is the icon glyph and its
``color``. No glow, shadow, or filter — confirmed via MCP measurement.

Two public functions:
    render_card(title, body, icon, accent)            -> None
    render_workflow_card(title, body, button_label,   -> bool
                         key, icon, accent)
"""

from __future__ import annotations

import html

import streamlit as st

from .tokens import CARD, COLORS, FONTS, TYPE_SCALE

_ACCENT_COLORS = {
    "green": COLORS["accent_green"],
    "cyan": COLORS["accent_cyan"],
}


def _accent_color(accent: str) -> str:
    try:
        return _ACCENT_COLORS[accent]
    except KeyError as exc:
        raise ValueError(
            f"accent must be one of {sorted(_ACCENT_COLORS)}; got {accent!r}"
        ) from exc


def _card_html(title: str, body: str, icon: str, accent_hex: str) -> str:
    icon_size = TYPE_SCALE["icon"]["size"]
    body_font = TYPE_SCALE["body"]
    return f"""
<div style="
    background: {CARD['bg']};
    border: {CARD['border']};
    border-radius: {CARD['radius']};
    padding: {CARD['padding']};
">
    <div style="
        font-size: {icon_size};
        color: {accent_hex};
        margin-bottom: 1rem;
        line-height: 1;
    ">{html.escape(icon)}</div>
    <h3 style="
        font-family: {FONTS['serif_display']};
        font-weight: 400;
        color: {COLORS['text_primary']};
        margin: 0 0 0.5rem 0;
        font-size: 1.4rem;
    ">{html.escape(title)}</h3>
    <p style="
        font-family: {body_font['family']};
        font-size: {body_font['size']};
        font-weight: {body_font['weight']};
        color: {COLORS['text_secondary']};
        margin: 0;
        line-height: 1.5;
    ">{html.escape(body)}</p>
</div>
"""


def render_card(
    title: str,
    body: str,
    icon: str = "◉",
    accent: str = "green",
) -> None:
    """Render a single feature card — text only, no interactive element.

    ``accent`` selects the icon color: ``"green"`` (#7bc342) or
    ``"cyan"`` (#0bbab0). Card chrome is identical regardless of accent.
    """
    accent_hex = _accent_color(accent)
    st.markdown(_card_html(title, body, icon, accent_hex), unsafe_allow_html=True)


def render_workflow_card(
    title: str,
    body: str,
    button_label: str,
    key: str,
    icon: str = "◉",
    accent: str = "green",
) -> bool:
    """Render a card with a CTA button beneath it.

    Used by P-01 (user-type selection) and P-03 (Inspect vs Prioritisation).
    The button picks up the theme's default primary gradient.

    Returns ``True`` if the button was clicked on this rerun, else ``False``.
    """
    accent_hex = _accent_color(accent)
    with st.container():
        st.markdown(_card_html(title, body, icon, accent_hex), unsafe_allow_html=True)
        st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)
        return st.button(button_label, key=key, use_container_width=True)
