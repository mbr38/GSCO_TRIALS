"""Categorical attributability (M-ATTRIB-A1, Layer 2).

Attributability answers a *different* question from measurement quality:
not "how well did the satellites observe this site?" (that's the M-TIER-A1
confidence chain in `engine.core.confidence`) but "is the detected signal
plausibly attributable to the supplier, or to something else inside the
AOI / a distant actor?".

Per the locked design (AT1 / AT3), attributability is **categorical**
(high / moderate / low / sparse), surfaces visually on the map and in the
C5 disclaimer, and does **not** enter the confidence chain or the composite
score. This module is the pure, EE-free home for the categorical bucketing
and the small geodesic helper the spatial-link computation needs — parallel
to `engine.core.confidence` for measurement quality.

In v1.x the only indicator with attributability is Nature's habitat
conversion (`compute_supplier_spatial_link` in `engine.nature`, which does
the EE centroid work and then calls `compute_habitat_attributability`
here). M-WIND-A1 v2.0 will add Air attributability on top of this same
bucket grammar (AT19).

Anchored to:
- M-ATTRIB-A1 spec §4.3 / §4.4 (centroid offset + categorical function)
- AT12 (bucket thresholds, in engine.constants)
- AT19 (shared high/moderate/low/sparse grammar with M-WIND-A1 v2.0)
"""

from __future__ import annotations

import math
from typing import Literal

from engine.constants import (
    HABITAT_SPATIAL_LINK_HIGH_KM,
    HABITAT_SPATIAL_LINK_MOD_KM,
    N_MIN_PIXELS_FOR_CENTROID,
)

# Shared bucket grammar (AT19). Re-exported so UI / M-WIND-A1 v2.0 import the
# canonical string set from one place rather than re-typing the literals.
AttributabilityState = Literal["high", "moderate", "low", "sparse"]
ATTRIBUTABILITY_STATES: tuple[str, ...] = ("high", "moderate", "low", "sparse")

# Mean Earth radius (km) — WGS84 authalic radius, matches the geodesic
# convention EE's `Geometry.distance` uses closely enough for the km-scale
# offsets we bucket here.
_EARTH_RADIUS_KM: float = 6371.0088


def haversine_km(
    lat1: float, lon1: float, lat2: float, lon2: float,
) -> float:
    """Great-circle distance between two lat/lon points, in kilometres.

    Pure spherical geodesic (haversine). Used by
    `engine.nature.compute_supplier_spatial_link` to measure the
    supplier→change-centroid offset without a second Earth Engine round
    trip (the centroid coordinates are already materialised client-side).
    """
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2.0) ** 2
    )
    return 2.0 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


_COMPASS_POINTS: tuple[str, ...] = (
    "N", "NE", "E", "SE", "S", "SW", "W", "NW",
)


def compass_direction(
    lat1: float, lon1: float, lat2: float, lon2: float,
) -> str:
    """8-point compass bearing from point 1 (supplier) to point 2 (centroid).

    Used by the C5 expander and the PDF audit appendix to phrase
    "habitat changes centred {dist} km {direction} of the supplier".
    Returns one of N / NE / E / SE / S / SW / W / NW. Pure; no engine state.
    """
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(rlat2)
    x = (
        math.cos(rlat1) * math.sin(rlat2)
        - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon)
    )
    bearing = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    # 8 sectors of 45°, centred on each cardinal/intercardinal point.
    idx = int((bearing + 22.5) % 360.0 // 45.0)
    return _COMPASS_POINTS[idx]


def compute_habitat_attributability(
    centroid_offset_km: float | None,
    n_change_pixels: int,
    *,
    n_min: int = N_MIN_PIXELS_FOR_CENTROID,
    high_threshold_km: float = HABITAT_SPATIAL_LINK_HIGH_KM,
    moderate_threshold_km: float = HABITAT_SPATIAL_LINK_MOD_KM,
) -> AttributabilityState:
    """Categorical attributability for habitat conversion (AT12 / §4.4).

    Buckets the distance from the supplier coordinate to the centroid of
    habitat-conversion pixels:

        sparse    n_change_pixels < n_min, OR centroid_offset_km is None
                  (too little change signal to attribute anywhere)
        high      centroid_offset_km ≤ high_threshold_km       (≤ 1.0 km)
        moderate  high_threshold_km < … ≤ moderate_threshold_km (1.0–3.0 km)
        low       centroid_offset_km > moderate_threshold_km    (> 3.0 km)

    Pure function, no engine state. The sparse check runs first: an
    insufficient-pixel result has no trustworthy centroid even if a distance
    was computed. A negative distance is nonsensical (distances are ≥ 0) and
    is treated as sparse rather than silently bucketed.
    """
    if (
        centroid_offset_km is None
        or n_change_pixels < n_min
        or centroid_offset_km < 0.0
    ):
        return "sparse"
    if centroid_offset_km <= high_threshold_km:
        return "high"
    if centroid_offset_km <= moderate_threshold_km:
        return "moderate"
    return "low"
