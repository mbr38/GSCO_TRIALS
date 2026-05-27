"""Large-AOI setup warning (M-FALLBACK-A1 §5.4 / FB19).

A soft, non-blocking alert shown at P-04 / P-07 setup time when the chosen
AOI radius exceeds the regional cutoff (>100 km). FB19 locks this as a
"soft alert … no enforcement; the user clicks through" — so it's an inline
`st.warning`, not a modal that gates the Run button. The matching
`aoi_scale_class` provenance field is emitted by the engine
(`engine.core.fallback.build_fallback_extra`), so this UI is purely the
heads-up; it doesn't itself stamp anything.

Single source of truth for the classification is
`engine.core.fallback.aoi_scale_class`, so the warning copy and the
provenance field can never drift.
"""

from __future__ import annotations

import streamlit as st

from engine.constants import (
    AOI_SCALE_CLASS_REGIONAL_MAX_KM,
    BACKGROUND_RING_MAX_KM,
    BACKGROUND_RING_RADIUS_MULTIPLE,
)
from engine.core.fallback import aoi_scale_class


def render_large_aoi_warning(radius_km: float | None) -> None:
    """Render the §5.4 soft warning when ``radius_km`` exceeds 100 km.

    No-op for site/regional-scale buffers (≤100 km) and for ``None``.
    """
    if radius_km is None or radius_km <= AOI_SCALE_CLASS_REGIONAL_MAX_KM:
        return
    scale = aoi_scale_class(radius_km)
    ring_km = min(
        BACKGROUND_RING_RADIUS_MULTIPLE * radius_km, BACKGROUND_RING_MAX_KM,
    )
    st.warning(
        f"**Large AOI — {scale}-scale.** At a {radius_km:g} km radius, the "
        f"background comparison ring extends to ~{ring_km:g} km. Background "
        f"comparisons may reflect regional context rather than the site's "
        f"local surroundings. The screening still runs; this is recorded as "
        f"`aoi_scale_class = \"{scale}\"` in each indicator's provenance."
    )
