"""Six-step repeatable core method per IC_v4 §0.2.

Three layers in this file:

1. EE-touching: `site_value` (step 1) and `background_value` (step 2) talk to
   Earth Engine via reduceRegion.
2. Pure math: `anomaly_z_hf` (steps 3-5) takes plain numbers and returns plain
   numbers, so the algorithm can be tested without EE.
3. Orchestration: `six_step` runs all six steps and assembles the standard
   {site, background, anomaly, z, hf, trend, trend_p, confidence, score} dict.

Trend (step ~) and the same-month seasonality filter (§0.6) live in
`engine/core/trend.py` and `engine/core/seasonality.py` respectively. Both
modules are optional — if they don't exist yet, this module routes to a no-op
and leaves their outputs as None with a TODO.
"""

from __future__ import annotations

from typing import Iterable

import ee

from engine.constants import ANOMALY_Z_THRESHOLD, NORMALISATION_K
from engine.core.buffers import background_ring, site_buffer
from engine.core.normalisation import to_score
from engine.exceptions import IndicatorComputeError

# Optional dependencies. Left as None when the module doesn't exist yet so
# six_step can degrade gracefully until milestones 5+ land them.
try:
    from engine.core import trend as _trend  # type: ignore[import-not-found]
except ImportError:
    _trend = None  # type: ignore[assignment]

try:
    from engine.core import seasonality as _seasonality  # type: ignore[import-not-found]
except ImportError:
    _seasonality = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Step 1 — site value (IC_v4 §0.2)
# ---------------------------------------------------------------------------

def site_value(
    aoi: dict,
    image_collection: ee.ImageCollection,
    band: str,
    scale: float | None = None,
) -> float:
    """Mean of `band` over Site_Buffer across `image_collection`.

    Raises `IndicatorComputeError` when the buffer has zero valid pixels.
    """
    geom = site_buffer(aoi["centre"], aoi["radius_km"])
    img = image_collection.select(band).mean()
    info = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geom,
        scale=scale,
        bestEffort=True,
        maxPixels=int(1e9),
    ).getInfo()
    value = info.get(band) if info else None
    if value is None:
        raise IndicatorComputeError(
            indicator_id=band,
            reason="site buffer has no valid pixels",
        )
    return float(value)


# ---------------------------------------------------------------------------
# Step 2 — background value (IC_v4 §0.2, optional §0.6 seasonality)
# ---------------------------------------------------------------------------

def background_value(
    aoi: dict,
    image_collection: ee.ImageCollection,
    band: str,
    seasonal: bool = True,
    scale: float | None = None,
) -> tuple[float, float]:
    """Median and stdDev of `band` over Background_Ring.

    When `seasonal=True` and `engine/core/seasonality.py` is available, the
    image collection is filtered to the same calendar months as the analysis
    window (§0.6). Until that module exists, the seasonal filter is a no-op.
    """
    geom = background_ring(aoi["centre"], aoi["radius_km"])
    ic = image_collection.select(band)

    if seasonal and _seasonality is not None:
        ic = _seasonality.same_month_filter(ic)
    # TODO(M3+): wire same-month filter once engine/core/seasonality.py lands.

    img = ic.mean()
    reducers = ee.Reducer.median().combine(ee.Reducer.stdDev(), sharedInputs=True)
    info = img.reduceRegion(
        reducer=reducers,
        geometry=geom,
        scale=scale,
        bestEffort=True,
        maxPixels=int(1e9),
    ).getInfo()
    if not info:
        raise IndicatorComputeError(
            indicator_id=band,
            reason="background ring reducer returned no info",
        )
    median = info.get(f"{band}_median")
    std = info.get(f"{band}_stdDev")
    if median is None or std is None:
        raise IndicatorComputeError(
            indicator_id=band,
            reason="background ring has no valid pixels",
        )
    return float(median), float(std)


# ---------------------------------------------------------------------------
# Steps 3-5 — anomaly, z, HF  (pure math; no EE)
# ---------------------------------------------------------------------------

def anomaly_z_hf(
    site: float,
    bg_median: float,
    bg_std: float,
    time_series: Iterable[float],
    z_threshold: float = ANOMALY_Z_THRESHOLD,
) -> dict:
    """Steps 3-5 of IC_v4 §0.2.

    Returns {"anomaly", "z", "hf"} where:
    - anomaly = site − bg_median (always defined)
    - z       = anomaly / bg_std
    - hf      = fraction of `time_series` dates whose per-date z ≥ z_threshold
                using the *same* (bg_median, bg_std) baseline

    Degenerate cases:
    - bg_std ≤ 0 → z and hf are returned as None.
    - empty time_series → hf is returned as None (anomaly and z stand).
    """
    anomaly = site - bg_median

    if bg_std <= 0:
        return {"anomaly": anomaly, "z": None, "hf": None}

    z = anomaly / bg_std

    series = list(time_series)
    if not series:
        return {"anomaly": anomaly, "z": z, "hf": None}

    hits = sum(1 for value in series if (value - bg_median) / bg_std >= z_threshold)
    hf = hits / len(series)
    return {"anomaly": anomaly, "z": z, "hf": hf}


# ---------------------------------------------------------------------------
# Step 6 — confidence  (placeholder; see chat: IC_v4 §6.3 doc gap)
# ---------------------------------------------------------------------------

def _placeholder_confidence(
    n_valid: int,
    n_total: int | None,
    mean_qa: float,
) -> float | None:
    """v1 placeholder: confidence = (N_valid / N_total) · mean_qa.

    IC_v4 §0.2 step 6 promises a formula in §6.3, but §6.3 in IC_v4 actually
    covers buffer *circumstances*, not the confidence formula. Known doc gap.
    TODO: replace with the real formula once IC_v4 §6.3 is corrected.
    """
    if n_total is None or n_total <= 0:
        return None
    raw = (n_valid / n_total) * mean_qa
    return max(0.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# Orchestration — all six steps in one call
# ---------------------------------------------------------------------------

def six_step(
    aoi: dict,
    image_collection: ee.ImageCollection,
    band: str,
    time_range: tuple[str, str],
    ee_client,
    *,
    indicator_id: str | None = None,
    direction: str = "higher_is_worse",
    seasonal: bool = True,
    z_threshold: float = ANOMALY_Z_THRESHOLD,
    k: float = NORMALISATION_K,
    scale: float | None = None,
) -> dict:
    """Run the full IC_v4 §0.2 pipeline and return the standard result dict.

    Raises `IndicatorComputeError` if the site or background reduction yields
    no valid pixels for `band` in `time_range`.
    """
    ic_window = image_collection.filterDate(time_range[0], time_range[1])

    site = site_value(aoi, ic_window, band, scale=scale)
    bg_median, bg_std = background_value(
        aoi, ic_window, band, seasonal=seasonal, scale=scale,
    )

    series = _per_date_site_series(aoi, ic_window, band, scale=scale)

    azhf = anomaly_z_hf(site, bg_median, bg_std, series, z_threshold=z_threshold)
    score = to_score(site, bg_median, bg_std, direction=direction, k=k)

    if _trend is not None and series:
        trend, trend_p = _trend.theil_sen_slope(series)
    else:
        # TODO(M5+): wire Theil-Sen / Mann-Kendall once engine/core/trend.py lands.
        trend, trend_p = None, None

    # Placeholder confidence — see _placeholder_confidence docstring for the gap.
    n_expected = int(ic_window.size().getInfo() or 0)
    confidence = _placeholder_confidence(
        n_valid=len(series), n_total=n_expected, mean_qa=1.0,
    )

    return {
        "site":       site,
        "background": bg_median,
        "anomaly":    azhf["anomaly"],
        "z":          azhf["z"],
        "hf":         azhf["hf"],
        "trend":      trend,
        "trend_p":    trend_p,
        "confidence": confidence,
        "score":      score,
    }


def _per_date_site_series(
    aoi: dict,
    image_collection: ee.ImageCollection,
    band: str,
    scale: float | None = None,
) -> list[float]:
    """Per-date Site_Buffer mean across `image_collection`."""
    geom = site_buffer(aoi["centre"], aoi["radius_km"])

    def _reduce(image: ee.Image) -> ee.Feature:
        value = image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=scale,
            bestEffort=True,
            maxPixels=int(1e9),
        ).get(band)
        return ee.Feature(None, {"value": value})

    fc = image_collection.select(band).map(_reduce).getInfo() or {}
    features = fc.get("features", [])
    return [
        float(feat["properties"]["value"])
        for feat in features
        if feat.get("properties", {}).get("value") is not None
    ]
