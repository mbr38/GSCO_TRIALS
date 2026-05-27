"""Indicator-name popover trigger + P-09 card modal (M-UI-A2).

Shared affordance used by the P-05 multi-indicator surfaces (C4b tile
grid, C5 drilldown rows, C5c Nature sub-section headers). Each indicator
name on P-05 is itself the popover trigger: clicking the bold name
opens a popover with the indicator's two-sentence ``tooltip_summary``
plus a "Learn more →" button. The button opens the indicator's P-09
library card as an ``st.dialog`` modal, preserving the underlying P-05
state.

Design (revised after the initial M-UI-A2 implementation):

  - First implementation: separate ⓘ button next to each name. Worked
    semantically but the popover button's chunky default styling didn't
    fit in tight tile contexts (drifted to the bottom of stretched
    tiles, crowded the name in six-column rows).

  - Current implementation: the name itself IS the trigger. The popover
    button is styled via ``ui/theme/theme.py`` to look like plain bold
    text with cursor:pointer + hover-underline + accent-green colour
    shift, so users see a clickable bold name without a separate
    affordance element competing for attention. The popover body and
    Learn-more behaviour are unchanged.

  - HS3 (popover, not hover) still holds — the popover opens on click
    rather than hover, so the affordance works identically on desktop
    and touch.
  - HS5/HS6: "Learn more →" opens the full P-09 card in an ``st.dialog``
    overlay; closing the modal returns to the unchanged P-05 view.
  - HS12: when the indicator has no ``tooltip_summary``, the name
    renders as plain bold markdown (no popover trigger), so the silent
    fallback preserves the original-shape rendering.

The Learn-more button writes the indicator id to ``st.session_state``
and calls ``st.rerun()``. On the next render, the page-level
``render_indicator_dialog_if_requested`` reads and pops the flag, then
fires the dialog. Routing through session state avoids calling
``st.dialog`` from inside a popover container, which is fragile in
v1.57.
"""

# M-UI-A2
from __future__ import annotations

import streamlit as st


# Lazy imports for ``demo.indicator_library`` and ``ui.components.p09_library``
# below break a circular-import cycle: ``demo.indicator_library`` imports
# the C5 drilldown's formula tuples, and the C5 drilldown imports this
# module's ``render_indicator_name_with_info``. Importing the demo loader
# at function-call time keeps the cycle from biting at module-import time.

_DIALOG_SESSION_KEY: str = "_indicator_dialog_to_open"


# ---------------------------------------------------------------------------
# Dialog (wraps the P-09 card render)
# ---------------------------------------------------------------------------

@st.dialog("Indicator details", width="large")
def _show_indicator_dialog(indicator_id: str) -> None:
    """Render the P-09 indicator card inside an st.dialog modal.

    Reuses ``ui.components.p09_library._render_card`` so the modal content
    is byte-identical to the standalone P-09 card view (HS6: "no abbreviated
    modal-specific content"). Imported lazily to avoid a circular import
    between p09_library and this module.
    """
    from demo.indicator_library import load_library
    from ui.components.p09_library import _render_card

    library = load_library()
    card = library.get(indicator_id)
    if card is None:
        st.error(f"No library entry for indicator '{indicator_id}'.")
        return
    _render_card(card)


def render_indicator_dialog_if_requested() -> None:
    """Open the indicator dialog if a Learn-more button set the flag.

    Call this once near the top of any page that hosts indicator info
    popovers. Pops the session-state flag so the dialog opens exactly
    once per click — subsequent reruns (e.g. user expanding an accordion
    inside the dialog) don't re-trigger it.
    """
    indicator_id = st.session_state.pop(_DIALOG_SESSION_KEY, None)
    if indicator_id:
        _show_indicator_dialog(indicator_id)


# ---------------------------------------------------------------------------
# Name-as-popover-trigger helper
# ---------------------------------------------------------------------------

def render_indicator_name_with_info(
    display_name: str,
    indicator_id: str,
    *,
    key_prefix: str,
    trailing_html: str | None = None,
) -> None:
    """Render the indicator name as a clickable popover trigger.

    The name is rendered via ``st.popover(label=display_name, ...)``;
    Streamlit's default button styling is stripped in
    ``ui/theme/theme.py`` so the trigger reads as plain bold text with a
    pointer cursor and a hover-underline + accent-colour shift. Clicking
    opens a popover containing the indicator's two-sentence summary and
    a "Learn more →" button that opens the full P-09 card modal.

    When the indicator has no ``tooltip_summary`` in the library, the
    name renders as plain bold markdown (HS12 silent fallback) so
    affordance-less indicators don't acquire a misleading click-cursor.

    Parameters
    ----------
    display_name
        User-facing label (e.g. ``"NO₂"``, ``"Biodiversity exposure"``).
    indicator_id
        Canonical library key for the indicator (e.g. ``"air.no2.score"``,
        ``"nature.kba.proximity_score"``).
    key_prefix
        Unique-per-site prefix used to make the Learn-more button's
        Streamlit key globally unique. The same ``indicator_id`` can be
        rendered at multiple sites (C4b tile + C5a row); two buttons
        with the same key would collide. Pick a short site tag per call
        site, e.g. ``"c4b"``, ``"c5_air"``, ``"c5_ghg"``,
        ``"c5_nature_biodiversity"``.
    trailing_html
        Optional inline-HTML snippet rendered to the right of the
        clickable name (e.g. the C4b confidence-dot glyph). Uses
        ``float:right`` on a span inside the same markdown line in the
        no-summary path; in the popover-trigger path the trigger and
        the trailing HTML sit in adjacent columns so the popover button
        doesn't conflict with the floated span.
    """
    # Lazy import — see module-level note on the circular-import cycle.
    from demo.indicator_library import tooltip_summary_for

    summary = tooltip_summary_for(indicator_id)

    # HS12 silent fallback. Preserve the original-shape rendering as
    # closely as possible so the no-summary case doesn't reshuffle the
    # surrounding layout. The C4b tile's floated trailing glyph is the
    # original shape callers relied on; reproduce it here.
    if summary is None:
        if trailing_html:
            st.markdown(
                f"**{display_name}**"
                f"<span style='float:right;font-size:1.1em;'>{trailing_html}</span>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f"**{display_name}**")
        return

    if trailing_html:
        # [4, 2] split gives the trailing slot enough room for short
        # text badges ("Failed", "—") in addition to single-glyph
        # confidence dots. A [5, 1] split (the earlier ratio) cropped
        # the "Failed" badge mid-word inside narrow C4b tiles.
        name_col, trail_col = st.columns([4, 2])
        with name_col:
            _render_name_popover(
                display_name, indicator_id, key_prefix, summary,
            )
        with trail_col:
            st.markdown(
                f"<div style='text-align:right;font-size:1.1em;"
                f"white-space:nowrap;'>{trailing_html}</div>",
                unsafe_allow_html=True,
            )
    else:
        _render_name_popover(
            display_name, indicator_id, key_prefix, summary,
        )


def _render_name_popover(
    display_name: str,
    indicator_id: str,
    key_prefix:   str,
    summary:      str,
) -> None:
    """Inner popover render — name is the label, body is summary + Learn more.

    ``use_container_width=False`` keeps the trigger sized to the label
    text rather than stretching to fill its column; combined with the
    theme CSS that strips the button chrome, the trigger reads as
    inline bold text.
    """
    with st.popover(display_name, use_container_width=False):
        st.markdown(summary)
        if st.button(
            "Learn more →",
            key=f"_learn_more_{key_prefix}_{indicator_id}",
            use_container_width=True,
        ):
            st.session_state[_DIALOG_SESSION_KEY] = indicator_id
            st.rerun()
