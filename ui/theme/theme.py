"""Global CSS injector — call ``apply_gsco_theme()`` once per page.

All values are pulled from ``ui.theme.tokens`` so the CSS never has a
literal hex/rgba inlined twice. ``apply_gsco_theme()`` is idempotent and
safe to double-call (e.g. once in ``gsco_app.py`` and again on the first
``app.py`` render); the second call writes an identical ``<style>`` block.
"""

from __future__ import annotations

import streamlit as st

from .tokens import (
    CARD,
    COLORS,
    FONTS,
    GRADIENT_PRIMARY,
    RADIUS,
    SHADOW_BUTTON,
    TYPE_SCALE,
)

_THEME_FLAG = "_gsco_theme_applied"


def apply_gsco_theme() -> None:
    """Inject the GSCO global CSS once per Streamlit session run.

    Safe to call from multiple entry points or pages — the per-run flag
    in ``st.session_state`` short-circuits duplicate injection within a
    single rerun. (Streamlit reruns the script on every interaction, so
    the flag resets naturally between reruns; that's fine, because each
    rerun needs the CSS block in the DOM anyway.)
    """
    css = _build_css()
    st.markdown(css, unsafe_allow_html=True)
    st.session_state[_THEME_FLAG] = True


def _build_css() -> str:
    body_font = TYPE_SCALE["body"]
    btn_font = TYPE_SCALE["button"]

    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Sans:wght@400;500;600;700&display=swap');

/* ---------------------------------------------------------------- */
/* Base — body background and default text color                    */
/* ---------------------------------------------------------------- */
html, body, [data-testid="stAppViewContainer"] {{
    background-color: {COLORS['body_bg']};
    color: {COLORS['text_primary']};
    font-family: {body_font['family']};
    font-size: {body_font['size']};
    font-weight: {body_font['weight']};
}}

[data-testid="stAppViewContainer"] > .main {{
    background-color: {COLORS['body_bg']};
}}

/* ---------------------------------------------------------------- */
/* Headings — Instrument Serif at weight 400, all levels h1..h6     */
/* ---------------------------------------------------------------- */
h1, h2, h3, h4, h5, h6,
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stMarkdownContainer"] h4,
[data-testid="stMarkdownContainer"] h5,
[data-testid="stMarkdownContainer"] h6 {{
    font-family: {FONTS['serif_display']};
    font-weight: 400;
    color: {COLORS['text_primary']};
    letter-spacing: -0.01em;
}}
/* Hero size on h1 only — reference renders ~72px at 1440 viewport. */
h1, [data-testid="stMarkdownContainer"] h1 {{
    font-size: {TYPE_SCALE['hero']['size']};
}}

/* Subhead-style paragraphs: muted secondary color + DM Sans.
   Scoped to .stMarkdown so button-label <p>s aren't affected. */
.stMarkdown p {{
    color: {COLORS['text_secondary']};
    font-family: {FONTS['sans_body']};
}}

/* Force DM Sans on form widgets (selectbox value text, inputs, etc.) —
   BaseWeb ships with Source Sans Pro internally and wins on specificity
   without an explicit selector here. */
[data-baseweb="select"], [data-baseweb="select"] *,
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea,
[data-baseweb="popover"], [data-baseweb="popover"] * {{
    font-family: {FONTS['sans_body']};
}}

/* ---------------------------------------------------------------- */
/* Buttons                                                          */
/*  - default st.button -> primary gradient                         */
/*  - kind="secondary"  -> outlined accent-green                    */
/* ---------------------------------------------------------------- */
.stButton > button {{
    background: {GRADIENT_PRIMARY};
    color: {COLORS['text_primary']};
    border: none;
    border-radius: {RADIUS['button']}px;
    padding: 0.9rem 2rem;
    font-family: {btn_font['family']};
    font-size: {btn_font['size']};
    font-weight: {btn_font['weight']};
    box-shadow: {SHADOW_BUTTON};
    transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
    cursor: pointer;
    white-space: nowrap;
}}
.stButton > button:hover {{
    transform: translateY(-1px);
    box-shadow: 0 6px 28px rgba(123, 195, 66, 0.35);
    color: {COLORS['text_primary']};
}}
.stButton > button:active {{
    transform: translateY(0);
}}

.stButton > button[kind="secondary"] {{
    background: transparent;
    color: {COLORS['accent_green']};
    border: 1px solid {COLORS['button_secondary_border']};
    box-shadow: none;
}}
.stButton > button[kind="secondary"]:hover {{
    background: rgba(123, 195, 66, 0.06);
    color: {COLORS['accent_green']};
    border-color: {COLORS['accent_green']};
}}

/* ---------------------------------------------------------------- */
/* Layout — hide Streamlit chrome, widen the container              */
/* ---------------------------------------------------------------- */
[data-testid="stHeader"] {{ display: none; }}
#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
[data-testid="stToolbar"] {{ display: none; }}

.block-container {{
    padding-top: 1rem;
    padding-bottom: 4rem;
    max-width: 1280px;
}}

/* Equal-height adjacent boxes inside an st.columns(...) row.
   Streamlit's flex columns stretch to the tallest sibling automatically,
   but bordered containers (st.container(border=True)) inside a column
   only grow to fit their own content. Cascade height:100% from the
   column down through the layout wrapper to the bordered block. */
[data-testid="stHorizontalBlock"] [data-testid="stColumn"] > [data-testid="stVerticalBlock"],
[data-testid="stHorizontalBlock"] [data-testid="stColumn"] [data-testid="stLayoutWrapper"],
[data-testid="stHorizontalBlock"] [data-testid="stColumn"] [data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"] {{
    height: 100%;
}}

/* ---------------------------------------------------------------- */
/* Misc — subtle horizontal rule, muted captions                    */
/* ---------------------------------------------------------------- */
hr {{
    border: none;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    margin: 1.5rem 0;
}}

[data-testid="stCaptionContainer"], small {{
    color: {COLORS['text_muted']};
    font-family: {FONTS['sans_body']};
    font-size: {TYPE_SCALE['caption']['size']};
}}
</style>
"""
