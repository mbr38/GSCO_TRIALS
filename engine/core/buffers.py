"""Site_Buffer and Background_Ring per IC_v4 §6 and Engine_Module_Skeleton §4.2.

Buffers use a geodetic (geodesic) projection — Earth Engine's `Geometry.buffer`
is geodesic by default, which is the H14 requirement: the rendered shape is
true to real distances on the WGS84 ellipsoid, not pixel-distorted.
"""

from __future__ import annotations

import ee

from engine.constants import (
    BACKGROUND_RING_MAX_KM,
    BACKGROUND_RING_RADIUS_MULTIPLE,
)


def site_buffer(
    centre: dict,
    radius_km: float,
    projection: str = "geodetic",
) -> ee.Geometry:
    """Inner circular buffer of `radius_km` around `centre = {lat, lon}`.

    `projection` is currently informational — EE's `.buffer(distance)` is
    geodesic, matching H14. The argument is kept so future implementations
    can swap projections without changing call-sites.
    """
    point = ee.Geometry.Point([centre["lon"], centre["lat"]])
    return point.buffer(distance=radius_km * 1000.0)


def background_ring(
    centre: dict,
    r_site_km: float,
    r_background_km: float | None = None,
) -> ee.Geometry:
    """Annulus from `r_site_km` out to `r_background_km`.

    When `r_background_km` is None, defaults to
    `min(BACKGROUND_RING_RADIUS_MULTIPLE · r_site_km, BACKGROUND_RING_MAX_KM)`
    per IC_v4 §6.2.
    """
    if r_background_km is None:
        r_background_km = min(
            BACKGROUND_RING_RADIUS_MULTIPLE * r_site_km,
            BACKGROUND_RING_MAX_KM,
        )
    outer = site_buffer(centre, r_background_km)
    inner = site_buffer(centre, r_site_km)
    return outer.difference(inner, maxError=1.0)


def pixel_size_warning(
    selected_indicators: set[str],
    r_site_km: float,
) -> dict | None:
    """Wireframes H10 warning: r_site_km < max(pixel size of selected indicators).

    Returns the warning payload, or None when no warning is needed.

    TODO(M3+): implement once per-indicator pixel sizes are codified in
    engine/constants.py (likely a dict keyed by indicator ID). Returning None
    here lets callers wire the integration point without blocking buffer work.
    """
    return None
