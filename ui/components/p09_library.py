"""P-09 Indicator Library renderer (M-P09).

Pillar tabs with sub-section accordion. Page-level search bar +
single-select ESG-framework filter.
"""

# M-P09
from __future__ import annotations

import streamlit as st

from demo.indicator_library import (
    IndicatorCardContent,
    get_esg_caveat,
    load_library,
)


# M-P09-COMPOSITES: fourth tab for cross-pillar / composite entries.
_PILLAR_LABELS: tuple[tuple[str, str], ...] = (
    ("air",       "💨 Air Pollution"),
    ("ghg",       "🔥 GHG Emissions"),
    ("nature",    "🌿 Nature / Land"),
    ("composite", "📊 Composite / Cross-pillar"),
)

_SUB_SECTION_LABELS: dict[str, str] = {
    "single_value":    "Single values",
    "component_score": "Component scores",
    "aggregate":       "Decision aggregates",
}


def render_indicator_library() -> None:
    library    = load_library()
    esg_caveat = get_esg_caveat()

    if esg_caveat:
        st.info(esg_caveat, icon="ℹ️")

    search_query = st.text_input(
        "Search indicators",
        placeholder=(
            "Search by name or definition "
            "(e.g. \"methane\", \"KBA\", \"EUDR\")…"
        ),
        key="p09_search",
    )

    esg_terms = ["(all)"] + _collect_esg_terms(library)
    esg_filter = st.selectbox(
        "Filter by regulatory framework (optional)",
        options=esg_terms,
        index=0,
        key="p09_esg_filter",
    )

    tabs = st.tabs([label for _, label in _PILLAR_LABELS])
    for tab, (pillar_id, _) in zip(tabs, _PILLAR_LABELS):
        with tab:
            pillar_cards = _filter_cards(
                library, pillar_id, search_query, esg_filter,
            )
            if not pillar_cards:
                st.info(
                    "No indicators match the current filter.",
                    icon="🔍",
                )
                continue
            _render_pillar_tab(pillar_cards)


# ──────────────────────────────────────────────────────────────────
# Filtering (pure, testable)
# ──────────────────────────────────────────────────────────────────

def _filter_cards(
    library:      dict[str, IndicatorCardContent],
    pillar_id:    str,
    search_query: str,
    esg_filter:   str,
) -> list[IndicatorCardContent]:
    """Apply search + ESG filter to a pillar's cards.

    Both filters compose as AND. Search is case-insensitive and
    matches against any of the four narrative fields (name, definition,
    decision relevance, ESG alignment) so a user typing "EUDR" finds
    indicators flagged for EUDR even when the framework is only named
    in the alignment field. The ESG filter is a stricter substring
    match against the alignment string alone.
    """
    pillar_cards = [c for c in library.values() if c.pillar == pillar_id]

    if search_query:
        q = search_query.lower()
        pillar_cards = [
            c for c in pillar_cards
            if q in c.display_name.lower()
            or q in c.definition.lower()
            or q in c.decision_relevance.lower()
            or q in c.esg_alignment.lower()
        ]

    if esg_filter and esg_filter != "(all)":
        pillar_cards = [
            c for c in pillar_cards
            if esg_filter.lower() in c.esg_alignment.lower()
        ]

    return pillar_cards


def _collect_esg_terms(
    library: dict[str, IndicatorCardContent],
) -> list[str]:
    """Build the dropdown's ESG framework list.

    Splits each entry's ``esg_alignment`` string on ``;`` and collects
    unique terms across all indicators. Sorted alphabetically.
    """
    terms: set[str] = set()
    for c in library.values():
        for part in c.esg_alignment.split(";"):
            part = part.strip()
            if part and part != "—":
                terms.add(part)
    return sorted(terms)


# ──────────────────────────────────────────────────────────────────
# Rendering
# ──────────────────────────────────────────────────────────────────

def _render_pillar_tab(cards: list[IndicatorCardContent]) -> None:
    """Render cards grouped by sub_section accordion."""
    by_sub_section: dict[str, list[IndicatorCardContent]] = {}
    for c in cards:
        by_sub_section.setdefault(c.sub_section, []).append(c)

    for sub_section_key, label in _SUB_SECTION_LABELS.items():
        items = by_sub_section.get(sub_section_key, [])
        if not items:
            continue
        with st.expander(f"**{label}** ({len(items)})", expanded=True):
            for card in items:
                _render_card(card)
                st.divider()


def _render_card(card: IndicatorCardContent) -> None:
    """Render one indicator's card. M-P09-COMPOSITES: dispatches the
    right-column metadata variant based on ``kind``."""
    st.markdown(f"### {card.display_name}")
    st.caption(f"`{card.indicator_id}`")

    col_left, col_right = st.columns([2, 1])
    with col_left:
        st.markdown("**Definition**")
        st.markdown(card.definition)

        st.markdown("**Decision relevance**")
        st.markdown(card.decision_relevance)

        st.markdown("**Limitations**")
        st.markdown(card.limitations)

        st.markdown("**Regulatory / ESG alignment**")
        st.markdown(card.esg_alignment)

    with col_right:
        if card.kind == "derived":
            _render_derived_metadata(card)
        else:
            _render_raw_metadata(card)


# M-P09-COMPOSITES
def _render_raw_metadata(card: IndicatorCardContent) -> None:
    """Right column for raw indicators — engine-config technical metadata."""
    st.markdown("**Data source**")
    st.code(card.asset_id, language=None)
    if card.data_source:
        st.caption(card.data_source)
    scale_str = (
        f"{card.native_scale_m:g} m"
        if card.native_scale_m is not None
        else "— (vector)"
    )
    st.markdown(f"**Scale.** {scale_str}")
    st.markdown(f"**Frequency.** {card.temporal_frequency}")
    st.markdown(f"**Type.** {card.data_type}")


# M-P09-COMPOSITES (v2 — three-branch dispatch)
def _render_derived_metadata(card: IndicatorCardContent) -> None:
    """Right column for derived indicators. Three layouts:

    1. **Pillar aggregate or composite** — formula + weights pulled
       live from c5_drilldown / the composite constant.
    2. **Component score** — conceptual inputs list from the manifest
       (no precise weights surfaced until M-COMPONENT-WEIGHTS lands).
    3. **Defensive** — nothing structured to show; renders a minimal
       marker.
    """
    if card.formula and card.weights:
        st.markdown("**Formula**")
        st.markdown(card.formula)
        st.markdown("**Weights**")
        for term, weight in card.weights.items():
            st.markdown(
                f"<code>{term}</code> · **{weight:.2f}**",
                unsafe_allow_html=True,
            )
        st.markdown("**Type.** Derived")
        return

    if card.inputs:
        st.markdown("**Computed from**")
        for input_id in card.inputs:
            st.markdown(f"- `{input_id}`")
        st.caption(
            "Precise weights live in the engine source — see "
            "`engine.{pillar}.compute_*` functions. v1.x "
            "(M-COMPONENT-WEIGHTS) will extract weights into "
            "structured constants and surface them here."
        )
        st.markdown("**Type.** Derived")
        return

    # Defensive fallback.
    st.markdown("**Type.** Derived (no formula breakdown available)")
