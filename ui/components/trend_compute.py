"""On-demand trend computation adapter (M-TREND-A2).

The single Earth-Engine-touching piece of the UI milestone. Given a series
indicator and the screening's setup + result, it reconstructs the indicator's
ImageCollection exactly as the owning pillar does (so the per-day series is in
the same units as the screening), then calls
`engine.core.trend.compute_trend`. Invoked **on link-click** (the view
triggers it when the trend panel opens — decision-log B-ARCH on-demand
design), never eagerly in the screening path.

Background stats are recomputed by `compute_trend` over the screening window
(the screening result does not surface `bg_std` — Step A B-RECON); the
fallback multipliers and the snapshot confidence are threaded through from the
screening result so a trend can never display more confidently than the
snapshot it is built on (TR13 / C-iii).
"""

from __future__ import annotations

from engine.core.provenance import _COLUMN_TO_SURFACE_UNCERTAINTY
from engine.core.trend import base_indicator_id, compute_trend, is_series_indicator


def trend_inputs(base_id: str, aoi: dict):
    """Reconstruct ``(image_collection, band, scale_m, direction)`` for a
    series indicator, reusing each pillar's own IC builder so the trend
    series matches the screening's band units exactly."""
    pillar = base_id.split(".")[0]
    slug = base_id.split(".")[1] if "." in base_id else base_id

    if pillar == "air":
        from engine.air import AIR_POLLUTANT_CONFIG, _build_image_collection
        cfg = AIR_POLLUTANT_CONFIG[slug]
        return _build_image_collection(cfg), cfg.band, cfg.scale_m, cfg.direction

    if pillar == "ghg":
        from engine.ghg import GHG_INDICATOR_CONFIG, _build_image_collection
        cfg = GHG_INDICATOR_CONFIG[slug]
        return _build_image_collection(cfg), cfg.band, cfg.scale_m, cfg.direction

    if base_id == "nature.ndvi":
        import ee
        from engine.core.adaptive_scale import adaptive_scale_m
        from engine.core.buffers import site_buffer
        from engine.nature import NATURE_INDICATOR_CONFIG
        cfg = NATURE_INDICATOR_CONFIG["ndvi"]
        # Same ×0.0001 rescale + rename the pillar applies before reducing.
        ic = (
            ee.ImageCollection(cfg.asset_id)
            .select("NDVI")
            .map(lambda img: (
                img.multiply(0.0001)
                   .rename("NDVI")
                   .copyProperties(img, ["system:time_start", "system:time_end"])
            ))
        )
        scale = adaptive_scale_m(
            site_buffer(aoi["centre"], aoi["radius_km"]), cfg.scale_m,
        )
        return ic, "NDVI", scale, cfg.direction

    raise ValueError(f"{base_id!r} is not a series indicator")


def compute_trend_for_indicator(select_key: str, setup: dict, result: dict) -> dict:
    """Compute the trend result for a screening's indicator (on-demand).

    `select_key` may be a select key (``"air.no2.score"``) or a base id;
    `setup` is the screening setup (centre / radius_km / time_range);
    `result` is the screening payload (for fallback flags + snapshot
    confidence). Raises `ValueError` for non-series indicators.
    """
    if not is_series_indicator(select_key):
        raise ValueError(f"{select_key!r} has no per-day series (non-series indicator)")
    base_id = base_indicator_id(select_key)
    aoi = {"centre": setup["centre"], "radius_km": setup["radius_km"]}
    time_range = tuple(setup["time_range"])

    ic, band, scale, direction = trend_inputs(base_id, aoi)

    prov = result.get(f"_provenance.{base_id}") or {}
    extra = prov.get("extra") or {}
    return compute_trend(
        aoi,
        ic,
        band,
        time_range,
        indicator_id=base_id,
        direction=direction,
        scale=scale,
        column_to_surface_uncertainty=_COLUMN_TO_SURFACE_UNCERTAINTY.get(base_id, "n_a"),
        temporal_fallback_applied=bool(extra.get("temporal_fallback_used")),
        climatology_fallback_applied=bool(extra.get("climatology_fallback_used")),
        snapshot_confidence=result.get(f"{base_id}.confidence"),
    )
