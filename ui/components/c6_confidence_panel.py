"""C6 — confidence panel (M-UI-E.5).

Three rows, one per pillar. Each row: pillar name, numeric confidence,
dot glyph, band label, limiting-factor prose. Sits between C5 drill-
downs and C7 verbal summary so the "interpretive" content (confidence
+ prose) is grouped after the data.

Limiting-factor logic is delegated to ``engine.verbal_summary`` so the
prose surfaced in C6 cannot drift from what C7's templates pick — both
read the same `_AIR_LIMITING_FACTOR_PROSE` / `_GHG_LIMITING_FACTOR_PROSE`
/ `_NATURE_LIMITING_FACTOR_PROSE` tables.

Authority: docs/Wireframes_All_v4.md §P-05 C6 + Appendix C.2.
"""

# M-UI-E.5
from __future__ import annotations

import streamlit as st

from engine.verbal_summary import (
    _GHG_LIMITING_FACTOR_PROSE,
    _NATURE_LIMITING_FACTOR_PROSE,
    _resolve_air_limiting_factor,
    _resolve_quality_limiting_factor,
)
from ui.components.legacy_id_fallback import payload_read
from ui.components.traffic_light import (
    band_for_score,
    band_label,
    confidence_glyph,
)


# (display name, confidence payload key, pillar id for limiting-factor dispatch).
# M-ATTRIB-A1 (AT16 / AT13): renamed measurement-quality IDs.
_PILLAR_ROWS: tuple[tuple[str, str, str], ...] = (
    ("Air Pollution", "air.measurement_quality_score", "air"),
    ("GHG emissions", "ghg.data_quality_attribution",  "ghg"),
    ("Nature/Land",   "nature.measurement_quality",    "nature"),
)


def render_c6_confidence_panel(payload: dict) -> None:
    """Render the C6 confidence panel — one row per pillar."""
    with st.container(border=True):
        st.markdown("### Confidence")
        st.caption(
            "Per-pillar data-quality scores. The limiting factor is the "
            "lowest-scoring sub-component of each pillar's quality "
            "aggregate — the thing that constrains how much weight to "
            "place on the priority score."
        )
        st.divider()
        for display_name, conf_key, pillar in _PILLAR_ROWS:
            # M-ATTRIB-A1 dual-emit shim — read new ID, fall back to legacy
            # so old saved analyses still render the pillar confidence rows.
            confidence = payload_read(payload, conf_key)
            _render_row(display_name, confidence, pillar, payload)


def _render_row(
    display_name: str,
    confidence:   float | None,
    pillar:       str,
    payload:      dict,
) -> None:
    """One pillar's row: name + score + dot + band + limiting factor."""
    band     = band_for_score(confidence)
    glyph    = confidence_glyph(confidence)
    conf_str = f"{confidence:.2f}" if confidence is not None else "—"
    band_str = band_label(band)

    limiting = _limiting_factor_for(pillar, payload)

    col_name, col_score, col_prose = st.columns([2, 2, 5])
    with col_name:
        st.markdown(f"**{display_name}**")
    with col_score:
        st.markdown(
            f"<span style='font-size:1.4em;font-weight:600;'>{conf_str}</span>"
            f"&nbsp;&nbsp;<span style='font-size:1.2em;'>{glyph}</span>"
            f"&nbsp;<span style='font-size:0.85em;color:#6b7280;'>{band_str}</span>",
            unsafe_allow_html=True,
        )
    with col_prose:
        if limiting:
            st.markdown(f"Limited by: {limiting}")
        else:
            st.caption("No limiting factor identified.")


def _limiting_factor_for(pillar: str, payload: dict) -> str | None:
    """Dispatch to the right verbal-summary resolver."""
    if pillar == "air":
        return _resolve_air_limiting_factor(payload)
    if pillar == "ghg":
        return _resolve_quality_limiting_factor(
            payload, _GHG_LIMITING_FACTOR_PROSE,
        )
    if pillar == "nature":
        return _resolve_quality_limiting_factor(
            payload, _NATURE_LIMITING_FACTOR_PROSE,
        )
    return None
