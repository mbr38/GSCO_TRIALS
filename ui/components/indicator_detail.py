"""Indicator detail card (M-UI-E.6, single-indicator P-05 variant).

Renders one card with the indicator's headline numerics (site,
anomaly, z, score, confidence) and a "Dataset used" expander with the
canonical M5.6 provenance block. Used in place of C5's pillar drill-
downs on the single-indicator variant, where the multi-indicator
aggregates (pillar follow-up priority, breakdown by sub-aggregate)
don't apply.

Authority: docs/Wireframes_All_v4.md §P-05.
"""

# M-UI-E.6
from __future__ import annotations

import streamlit as st

from ui.components.c5_drilldown import _fmt, _render_provenance_block
from ui.components.traffic_light import (
    band_colour,
    band_for_score,
    band_label,
    confidence_glyph,
)


def render_indicator_detail(indicator_id: str, payload: dict) -> None:
    """Render the single-indicator detail card.

    ``indicator_id`` is the canonical ID the user selected — e.g.
    ``"air.no2.score"``, ``"nature.kba.proximity_score"``. Splits into
    pillar + slug to read the right ``<pillar>.<slug>.<measurement>``
    keys from the payload.
    """
    parts = indicator_id.split(".")
    pillar = parts[0]
    slug   = parts[1] if len(parts) > 1 else ""
    prefix = f"{pillar}.{slug}"

    score      = payload.get(f"{prefix}.score") or payload.get(indicator_id)
    site       = payload.get(f"{prefix}.site")
    anomaly    = payload.get(f"{prefix}.anomaly")
    z          = payload.get(f"{prefix}.z")
    confidence = payload.get(f"{prefix}.confidence")
    band       = band_for_score(score)
    colour     = band_colour(band)

    with st.container(border=True):
        st.markdown(f"### `{indicator_id}`")
        col_score, col_metrics = st.columns([1, 3])
        with col_score:
            st.metric("Score", _fmt(score, ".2f"))
            st.markdown(
                f"<span style='color:{colour};font-weight:600;'>"
                f"{band_label(band)}</span> "
                f"&nbsp;&nbsp;{confidence_glyph(confidence)} confidence",
                unsafe_allow_html=True,
            )
        with col_metrics:
            metric_a, metric_b, metric_c = st.columns(3)
            metric_a.metric("Site value", _fmt(site,    ".3g"))
            metric_b.metric("Anomaly",    _fmt(anomaly, "+.3g"))
            metric_c.metric("Z-score",    _fmt(z,       ".2f"))

        st.divider()

        provenance = payload.get(f"_provenance.{pillar}.{slug}")
        with st.expander("Dataset used"):
            if provenance is None:
                st.caption("Not available.")
            else:
                _render_provenance_block(provenance)
