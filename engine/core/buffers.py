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


# M-TIER-A3 Step A — land mask for Background_Ring coastal handling.
# MOD44W v6: 250 m static global product, single `water_mask` band where
# 1 = water and 0 = land. We invert via `.Not()` so reducers can call
# `updateMask(land_image)` intuitively (land=1 keeps land pixels).
#
# Spec note (M-TIER-A3 §3.1) draft showed `ee.Image(f"{ASSET}/water_mask")`
# which treats MOD44W as a single Image with a sub-asset path. The EE
# catalog actually exposes `MODIS/006/MOD44W` as an ImageCollection (one
# per-year image with `water_mask` as a *band*). `.mosaic()` flattens the
# collection to a single image — coastline drift across years is well
# below the 250 m mask resolution per the spec's vintage note.
LAND_MASK_ASSET: str = "MODIS/006/MOD44W"
LAND_MASK_BAND: str = "water_mask"


def _land_mask_image() -> "ee.Image":
    """Return a binary `ee.Image` with land=1, water=0.

    Source: MOD44W v6 (250 m, static global product, MODIS-derived). The
    asset is exposed as an ImageCollection in EE's catalog with one image
    per year; we mosaic to a single image (vintage drift << 250 m mask).
    """
    return (
        ee.ImageCollection(LAND_MASK_ASSET)
        .select(LAND_MASK_BAND)
        .mosaic()
        .Not()
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
    apply_land_mask: bool = True,
) -> dict:
    """Annulus from `r_site_km` out to `r_background_km`, with land mask.

    When `r_background_km` is None, defaults to
    `min(BACKGROUND_RING_RADIUS_MULTIPLE · r_site_km, BACKGROUND_RING_MAX_KM)`
    per IC_v4 §6.2.

    M-TIER-A3 Step B — returns a dict (was: bare ee.Geometry) carrying:

      - ``geometry``: ee.Geometry of the annulus (unchanged from pre-milestone)
      - ``mask``: ee.Image binary land mask (land=1) when
        ``apply_land_mask=True``, else None
      - ``land_fraction``: float in [0.0, 1.0] — geometric land fraction of
        the annulus per MOD44W. Always computed (one ~500 ms getInfo per
        ring construction); cost amortised across all indicators sharing
        the same AOI per spec §3.7
      - ``land_mask_applied``: mirrors ``apply_land_mask`` for provenance
      - ``land_mask_asset``: MOD44W asset ID, always populated for vintage
        tracking even when ``apply_land_mask=False``

    ``apply_land_mask=False`` exists for (a) future composition with
    M-CLIM-A3b (climatology fallback may want both masked and unmasked
    introspection) and (b) regression testing against pre-milestone
    behaviour. Spec lock LM3 makes True the production default.
    """
    if r_background_km is None:
        r_background_km = min(
            BACKGROUND_RING_RADIUS_MULTIPLE * r_site_km,
            BACKGROUND_RING_MAX_KM,
        )
    outer = site_buffer(centre, r_background_km)
    inner = site_buffer(centre, r_site_km)
    geometry = outer.difference(inner, maxError=1.0)

    mask = _land_mask_image()
    info = mask.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geometry,
        scale=250,
        maxPixels=int(1e9),
    ).getInfo() or {}
    # MOD44W band keeps its `water_mask` name after `.Not()`; the *value*
    # at that key is the land fraction in [0, 1] because Mean over a binary
    # land=1/water=0 image gives the land share directly.
    raw = info.get(LAND_MASK_BAND)
    land_fraction = float(raw) if raw is not None else 0.0

    return {
        "geometry": geometry,
        "mask": mask if apply_land_mask else None,
        "land_fraction": land_fraction,
        "land_mask_applied": apply_land_mask,
        "land_mask_asset": LAND_MASK_ASSET,
    }


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
