"""C3 — traffic-light summary (M-UI-E.2).

Composite chip on top as the headline; three pillar chips in a row
beneath. Each chip carries: pillar name, score (2 d.p.), band-coloured
fill bar, textual band label, and confidence dot.

Authority: ``docs/Wireframes_All_v4.md`` §P-05 C3 and Appendix C.3
(chip composition) / C.4 (accessibility — band label always renders
as text alongside the colour).
"""

# M-UI-E.2
from __future__ import annotations

import streamlit as st

from ui.components.traffic_light import (
    band_colour,
    band_for_score,
    band_label,
    confidence_glyph,
)


# Canonical labels — kept in sync with engine/verbal_summary.py
# ``_PILLAR_DISPLAY`` so chips and prose use the same names. Note the
# lowercase "emissions" in "GHG emissions" matches the verbal summary
# doc §7.2.
_PILLAR_DISPLAY: dict[str, str] = {
    "air":       "Air Pollution",
    "ghg":       "GHG emissions",
    "nature":    "Nature/Land",
    "composite": "Overall",
}

# (priority_key, confidence_key) per chip. Keys mirror the orchestrator's
# ``_PILLAR_PRIORITY_IDS`` / ``_PILLAR_CONFIDENCE_IDS`` (engine/orchestrator.py).
_CHIP_KEYS: dict[str, tuple[str, str]] = {
    "composite": ("composite.overall_screening",   "composite.confidence"),
    "air":       ("air.audit_followup_priority",   "air.attribution_confidence_score"),
    "ghg":       ("ghg.audit_followup_priority",   "ghg.data_quality_attribution"),
    "nature":    ("nature.followup_priority",      "nature.quality_attribution"),
}


def render_c3_summary(payload: dict) -> None:
    """Render the C3 traffic-light summary block.

    Composite chip first (full width) as the headline, then the three
    pillar chips in a row. Missing scores render as a neutral-grey chip
    with ``"—"`` in the score slot — no sentinel value substitution.
    """
    with st.container(border=True):
        st.markdown("### Priority")
        _render_chip("composite", payload)
        col_air, col_ghg, col_nature = st.columns(3)
        with col_air:
            _render_chip("air", payload)
        with col_ghg:
            _render_chip("ghg", payload)
        with col_nature:
            _render_chip("nature", payload)


def _render_chip(chip_key: str, payload: dict) -> None:
    """Render one chip — header row, fill bar, band-label + dot row.

    The fill bar uses inline HTML because Streamlit's progress widget
    doesn't accept colour overrides. The band label always renders as
    text next to the colour bar per Appendix C.4.

    M-FOLLOWUP-FALLBACK: when the score is None, route to the
    no-data variant. The band would otherwise read "—" — technically
    correct but less informative than an explicit "No data" affordance
    paired with a grey fill bar and the appropriate confidence dot.
    """
    priority_key, confidence_key = _CHIP_KEYS[chip_key]
    score = payload.get(priority_key)
    confidence = payload.get(confidence_key)
    label = _PILLAR_DISPLAY[chip_key]

    if score is None:
        _render_no_data_chip(label, confidence)
        return

    band = band_for_score(score)
    score_str = f"{score:.2f}"
    fill_pct = int(score * 100)
    colour = band_colour(band)
    glyph = confidence_glyph(confidence)

    with st.container(border=True):
        st.markdown(
            f"**{label}** &nbsp;&nbsp; "
            f"<span style='float:right;'>{score_str}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='background:#e5e7eb;height:8px;"
            f"border-radius:4px;overflow:hidden;margin:6px 0;'>"
            f"<div style='background:{colour};width:{fill_pct}%;"
            f"height:100%;'></div></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<span style='font-size:0.85em;color:#6b7280;'>"
            f"{band_label(band)}</span>"
            f"<span style='float:right;font-size:1.1em;'>{glyph}</span>",
            unsafe_allow_html=True,
        )


# M-FOLLOWUP-FALLBACK
def _render_no_data_chip(label: str, confidence: float | None) -> None:
    """Render the "no data" variant of a chip.

    Triggered when the pillar's follow-up priority is None — typically
    when strict-None propagation in the engine flagged a real upstream
    failure (skipped indicator, background ring over water, etc.) and
    refused to fall back to one surviving sub-aggregate. The chip's
    score slot reads ``—``, the fill bar is fully grey, and the band
    label is ``"No data"`` so the affordance is unambiguous.

    The confidence dot still renders if a confidence value is present —
    some pillars produce a confidence aggregate even when the headline
    priority is None (it's derived from a different sub-aggregate).
    """
    glyph = confidence_glyph(confidence)
    with st.container(border=True):
        st.markdown(
            f"**{label}** &nbsp;&nbsp; "
            f"<span style='float:right;'>—</span>",
            unsafe_allow_html=True,
        )
        # Empty fill bar — grey rail, no coloured slice.
        st.markdown(
            "<div style='background:#e5e7eb;height:8px;"
            "border-radius:4px;overflow:hidden;margin:6px 0;'></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<span style='font-size:0.85em;color:#6b7280;'>No data</span>"
            f"<span style='float:right;font-size:1.1em;'>{glyph}</span>",
            unsafe_allow_html=True,
        )
