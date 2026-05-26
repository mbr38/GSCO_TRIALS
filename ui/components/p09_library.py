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
from engine.constants import INDICATOR_CONFIDENCE_FAMILY


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


# M-TIER-A3 Step H2 Surface 2 — ring-based indicators (those that use
# Background_Ring as the comparison surface). When rendered in the
# library, each of these gets the shared coastal-handling methodology
# paragraph below the card's Limitations section. Order matches spec §3.8.
_RING_BASED_INDICATORS: frozenset[str] = frozenset({
    "air.no2.score",
    "air.so2.score",
    "air.co.score",
    "air.hcho.score",
    "air.aai.score",
    "air.o3.score",
    "air.aod.score",
    "ghg.ch4.score",
    "ghg.co2.score",
})

_COASTAL_HANDLING_CARD_PARAGRAPH: str = (
    "**Coastal sites.** When the surrounding comparison area "
    "(the \"background ring\") overlaps the coastline, the tool excludes "
    "ocean pixels from the baseline calculation. The comparison is made "
    "against the land portion of the ring only.\n\n"
    "This matters because pollutants in air don't behave the same over "
    "open ocean as over land — ocean values are typically near-zero "
    "(clean marine air), and including them would artificially depress "
    "the baseline and make every coastal supplier look like an outlier. "
    "The land mask uses the MODIS MOD44W global water dataset "
    "(250 m resolution). The exact land-vs-water split for a given "
    "screening run is shown in the confidence breakdown."
)


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

        # M-TIER-A3 Step H2 Surface 2 — ring-based indicators get the
        # shared coastal-handling methodology paragraph. Static text;
        # the per-run land vs water split is surfaced in the C5
        # "Coastal handling" sub-section on P-05 (Surface 1).
        if card.indicator_id in _RING_BASED_INDICATORS:
            st.markdown("**How this is computed (coastal sites)**")
            st.markdown(_COASTAL_HANDLING_CARD_PARAGRAPH)

        st.markdown("**Regulatory / ESG alignment**")
        st.markdown(card.esg_alignment)

    with col_right:
        if card.kind == "derived":
            _render_derived_metadata(card)
        else:
            _render_raw_metadata(card)

    # M-UI-A1-SURFACE Sub-milestone 4 (24 May 2026): per-family
    # confidence explainer. Static text — live values stay on P-05
    # (D5 lock). Placed BELOW the methodology block, not interleaved.
    with st.expander(
        "What confidence means for this indicator",
        expanded=False,
    ):
        st.markdown(_confidence_explanation_for(card.indicator_id))


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


# ──────────────────────────────────────────────────────────────────
# M-UI-A1-SURFACE Sub-milestone 4 — per-indicator confidence explainer
# ──────────────────────────────────────────────────────────────────

# Family copy lifted verbatim from the spec. Wording ties to
# docs/M-TIER-A1_plain_language_explainer.md and Sub-milestone 2's
# "What's behind this confidence?" expander on P-05.
_LIVE_REVISIT_EXPLANATION: str = (
    "Confidence for this indicator is computed from four factors: "
    "(1) the quality of the raw sensor data after QA filtering, "
    "(2) the number of valid observation days within the analysis "
    "window vs how many were expected for this sensor's revisit "
    "cadence, (3) the strength of any anomaly observed (fraction of "
    "days that crossed the threshold), (4) how well the satellite's "
    "pixel size matches the analysis buffer. Sensors that measure the "
    "whole air column rather than ground-level (NO₂, SO₂, CO, HCHO, "
    "CH₄) carry an additional discount per audit §1.5. See the "
    "'What's behind this confidence?' expander on P-05 for the live "
    "breakdown."
)

_SINGLE_SNAPSHOT_EXPLANATION: str = (
    "Confidence for this reference dataset is 1.0 by construction "
    "when the dataset is in coverage — these are static or annual "
    "sources without per-observation noise. The relevant audit "
    "context is the dataset's vintage and coverage window (visible "
    "in the 'Datasets used' expander on P-05). If the analysis "
    "window falls outside the dataset's coverage (e.g. ODIAC CO₂ "
    "at 2020-2023 vintage queried for a 2026 window), the indicator "
    "is skipped entirely with skipped_reason='out_of_coverage' and "
    "does not contribute to its pillar — vintage drift makes "
    "'confidence = 1.0' inapplicable until the dataset is updated."
)

_DERIVED_EXPLANATION: str = (
    "This is a derived sub-score computed from multiple primary "
    "indicators. Its confidence flows from the survivor-renormalised "
    "aggregate of contributing indicators (strict-None propagates "
    "from any indicator that failed). The pillar-level confidence "
    "(composite.confidence) is the min of all three pillar "
    "confidences per the conservative-aggregation rule. Note: this "
    "explanation describes the *confidence* attached to a derived "
    "score — not the score itself, which is computed via the formula "
    "and weights shown above. Score aggregation uses the rule "
    "appropriate to each pillar (mean for composite.overall_screening; "
    "weighted sums or formulas for pillar-level scores)."
)

_FOOTER: str = (
    "Live confidence values for this indicator appear on P-05 when "
    "a screening is run."
)

_UNKNOWN_FALLBACK: str = (
    "Confidence for this indicator is not yet documented. See P-05 "
    "for live values when a screening is run."
)

_FAMILY_EXPLANATIONS: dict[str, str] = {
    "live_revisit":    _LIVE_REVISIT_EXPLANATION,
    "single_snapshot": _SINGLE_SNAPSHOT_EXPLANATION,
    "derived":         _DERIVED_EXPLANATION,
}


def _confidence_explanation_for(indicator_id: str) -> str:
    """Return a 2-3 sentence plain-language explanation of confidence
    for the given indicator's family.

    Lookup is two-tiered: the full ``indicator_id`` is tried first
    (which is what disambiguates ``nature.habitat.conversion_score``
    as ``derived`` from the raw ``nature.habitat`` single_snapshot
    base), then the first two dot-segments as a fallback for raw IDs
    like ``air.no2.score`` → ``air.no2``.

    Unknown IDs return a short fallback without the footer (so the
    footer's promise of "live values on P-05" doesn't make a claim we
    can't keep).
    """
    family = INDICATOR_CONFIDENCE_FAMILY.get(indicator_id)
    if family is None:
        base = ".".join(indicator_id.split(".")[:2])
        family = INDICATOR_CONFIDENCE_FAMILY.get(base)
    if family is None:
        return _UNKNOWN_FALLBACK
    explanation = _FAMILY_EXPLANATIONS[family]
    return f"{explanation}\n\n{_FOOTER}"


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
