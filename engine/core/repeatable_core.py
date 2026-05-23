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
from engine.core.confidence import (
    compute_anomaly_strength_term,
    compute_indicator_confidence,
    compute_n_valid_term,
    compute_qa_term,
    compute_spatial_context_term,
)
from engine.core.normalisation import to_score
from engine.core.provenance import _COLUMN_TO_SURFACE_UNCERTAINTY
from engine.exceptions import (
    BackgroundRingNoDataError,
    IndicatorComputeError,
    SiteBufferNoDataError,
)

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


# Earth Engine's compute graph aborts a `.map().getInfo()` chain once the
# collection exceeds ~5000 elements. The per-date site series only feeds HF
# (hotspot frequency), so capping at the most recent N observations is a
# screening-grade approximation: a 90-day window has ~30-60 Sentinel-5P
# observations, well under the cap; longer windows become recency-weighted.
_PER_DATE_SERIES_MAX_OBSERVATIONS: int = 100


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
        # M-AIR-GHG-DEFENSIVE: raise SiteBufferNoDataError so pillar
        # dispatchers can route this to a skipped payload (with an
        # asset-family-specific reason code) instead of a hard failure.
        # Subclass of IndicatorComputeError — existing generic handlers
        # still trip if a caller doesn't want the distinction.
        # One extra getInfo on the failure path only — saves debugging time
        # when a buffer / time-range combination produces no usable pixels.
        n_total = int(image_collection.size().getInfo() or 0)
        raise SiteBufferNoDataError(
            indicator_id=band,
            reason=(
                f"site buffer has no valid pixels "
                f"({n_total} observations in time_range; "
                f"scale={scale}m; buffer={aoi['radius_km']}km)"
            ),
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
    median = info.get(f"{band}_median") if info else None
    std = info.get(f"{band}_stdDev") if info else None
    if median is None or std is None:
        # M-OCEAN-RING: distinguish "ring reduces to nothing" (which is
        # typical for coastal AOIs whose ring lands over water) from
        # other failure modes. Pillar dispatchers catch the specific
        # subclass to emit a skipped_reason payload rather than a hard
        # _failures entry; everything else still flows through the
        # generic IndicatorComputeError path.
        n_total = int(image_collection.size().getInfo() or 0)
        # M-RING-UX — broadened reason text to acknowledge both causes
        # (ring over water OR sparse-coverage region) and surface that
        # to method_note via the pillar's _emit_skipped_*_result helper.
        raise BackgroundRingNoDataError(
            indicator_id=band,
            reason=(
                f"background ring has no valid pixels "
                f"({n_total} observations in time_range; "
                f"scale={scale}m; buffer={aoi['radius_km']}km) "
                "— ring either lands over water or over a region with "
                "persistent cloud cover / sparse satellite coverage"
            ),
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
# Step 6 — confidence  (M-TIER-A1: real per-indicator formula per IC_v4 §6.3)
# ---------------------------------------------------------------------------

def _window_days(time_range: tuple[str, str]) -> int | None:
    """Inclusive day count between two ISO dates. None on parse failure."""
    from datetime import date as _date
    try:
        start = _date.fromisoformat(time_range[0])
        end   = _date.fromisoformat(time_range[1])
    except (TypeError, ValueError):
        return None
    return max(1, (end - start).days)


def _buffer_area_m2(radius_km: float) -> float:
    import math as _math
    return _math.pi * (radius_km * 1000.0) ** 2


# ---------------------------------------------------------------------------
# Server-side N_valid + HF (M-TIER-A1 Step 8)
# ---------------------------------------------------------------------------


def _server_side_hf(
    aoi: dict,
    image_collection: ee.ImageCollection,
    band: str,
    bg_median: float,
    bg_std: float,
    z_threshold: float,
    scale: float | None,
) -> tuple[int, float | None]:
    """Compute (n_valid, HF) over the *entire* filtered collection server-side.

    Maps over every image (no `.limit()` cap — that cap was the bug the
    Brasilia + Rotterdam AOD/CH4 diagnostic surfaced). Per-image:

      1. reduceRegion with a *combined* Mean + Count reducer over
         Site_Buffer at `scale`. Mean may be null when the band is
         fully masked over the buffer, but Count is *always* a real
         Number (0 when no valid pixels, ≥1 otherwise). `is_valid` is
         derived from Count, sidestepping the null-propagation problem.
      2. `is_hot   = (z >= z_threshold) AND is_valid`, where the z math
         uses the steady-state (bg_median, bg_std) baseline from steps 1+2.
         The mean is guarded with `If(is_valid, mean, 0)` so invalid rows
         don't crash arithmetic.

    Aggregates the per-image `is_valid` and `is_hot` sums via
    `reduceColumns(ee.Reducer.sum().repeat(2), ...)` — one `.getInfo()`
    at the end, no client-side loop.

    Returns:
        n_valid: count of images whose site-buffer mean was non-null at
                 the requested scale. This is what feeds the A1
                 confidence formula's N_valid term via
                 `compute_n_valid_term(n_observations=n_valid, ...)`.
        hf:      `n_hot / n_valid` as a float in [0, 1], or `None` when
                 `bg_std <= 0` (degenerate background — z undefined) or
                 `n_valid == 0` (no data — strict-None propagates upward).

    Design note on null handling. An earlier draft used a
    `_MISSING_SITE_VALUE_SENTINEL` passed as the `ee.Dictionary.get`
    default, but EE's `get(key, default)` returns `default` only when
    the key is *absent* — not when the key is present and maps to
    `null`. `reduceRegion` produces `{band: null}` (not a missing key)
    when the band is fully masked, so the sentinel never fired and
    downstream `ee.Number(null).neq(...)` raised `Number.neq:
    Parameter 'left' is required and may not be null.`. The Count
    reducer sidesteps this: it's a counting reducer, so the absence
    of valid pixels is encoded as the value `0`, never as `null`.
    """
    geom = site_buffer(aoi["centre"], aoi["radius_km"])
    bg_std_degenerate = bg_std <= 0

    # Combined reducer: one reduceRegion per image, both Mean and Count
    # returned in one dict.  Mean may be null when the band is fully
    # masked; Count is always a Number (0 when no pixels, ≥1 otherwise),
    # so we drive is_valid from Count.
    mean_count_reducer = ee.Reducer.mean().combine(
        reducer2=ee.Reducer.count(),
        sharedInputs=True,
    )

    # EE's combine() naming convention with sharedInputs:
    #   - first reducer's output keeps the band name             → `<band>`
    #   - subsequent reducers get a suffix from the reducer name → `<band>_count`
    mean_key  = band
    count_key = f"{band}_count"

    def per_image(image: ee.Image) -> ee.Feature:
        reduction = image.select(band).reduceRegion(
            reducer=mean_count_reducer,
            geometry=geom,
            scale=scale,
            bestEffort=True,
            maxPixels=int(1e9),
        )
        # `default=0` covers the rare case where the band is missing
        # from the image entirely (vs the common case of being present
        # but fully masked, which Count already encodes as 0).
        count = ee.Number(reduction.get(count_key, 0))
        is_valid = count.gt(0)
        # Mean reducer over zero valid pixels OMITS the output key
        # entirely (not even null), so we MUST pass a default to
        # reduction.get(mean_key) — both branches of If evaluate
        # server-side, so an undefaulted .get() crashes the map even
        # when is_valid=0 short-circuits it logically. The default 0.0
        # is never read on the valid path (count > 0 → key present).
        site_mean = ee.Number(
            ee.Algorithms.If(is_valid, reduction.get(mean_key, 0.0), 0.0)
        )
        if bg_std_degenerate:
            is_hot = ee.Number(0)
        else:
            z = site_mean.subtract(bg_median).divide(bg_std)
            is_hot = z.gte(z_threshold).And(is_valid)
        return ee.Feature(None, {"is_valid": is_valid, "is_hot": is_hot})

    fc = image_collection.select(band).map(per_image)
    summed = fc.reduceColumns(
        reducer=ee.Reducer.sum().repeat(2),
        selectors=["is_valid", "is_hot"],
    ).getInfo() or {}
    sums = summed.get("sum") or [0, 0]
    n_valid = int(sums[0] or 0)
    n_hot   = int(sums[1] or 0)

    if n_valid == 0:
        return 0, None
    if bg_std_degenerate:
        return n_valid, None
    return n_valid, n_hot / n_valid


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

    # M-TIER-A1 Step 8 — server-side N_valid + HF. Replaces the
    # client-side `_per_date_site_series` + `anomaly_z_hf(series)` path
    # which had a 100-image cap that under-reported n_observations for
    # multi-swath / multi-orbit assets (see tools/diag_aod_ch4_controls.py).
    # `anomaly_z_hf` is still called with an empty series to compute
    # anomaly + z from the steady-state values; HF is overwritten with
    # the server-side count below.
    azhf = anomaly_z_hf(site, bg_median, bg_std, [], z_threshold=z_threshold)
    n_valid, hf = _server_side_hf(
        aoi, ic_window, band, bg_median, bg_std, z_threshold, scale,
    )
    azhf["hf"] = hf

    score = to_score(site, bg_median, bg_std, direction=direction, k=k)

    # Trend (M-TIER-A2): trend.py doesn't exist yet — the existing
    # `if _trend is not None and series` block was dead code (always
    # False since the import always fails). When Tier A2 lands, it must
    # provide a server-side reducer following the same pattern as
    # `_server_side_hf` below — no client-side per-date series sampling.
    # See docstring "Trend computation (M-TIER-A2 follow-up)" below.
    trend, trend_p = None, None

    # M-TIER-A1 — per-indicator confidence via the universal 4-term formula
    # × column-to-surface multiplier (IC_v4 §6.3 / audit §1.1).
    # Strict-None at the indicator level: any missing term collapses the
    # confidence to None; pillar rollups handle that via survivor-renormalise.
    # n_observations now comes from the server-side count, not len(series).
    confidence_terms = _confidence_terms_from_six_step_state(
        indicator_id=indicator_id,
        aoi=aoi,
        time_range=time_range,
        n_observations=n_valid,
        hf=azhf["hf"],
    )
    confidence = compute_indicator_confidence(
        indicator_id=indicator_id or "<unknown>",
        column_to_surface_uncertainty=_COLUMN_TO_SURFACE_UNCERTAINTY.get(
            indicator_id or "", "n_a",
        ),
        **confidence_terms,
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
        # M-TIER-A1: surface the four input terms so callers can pass them
        # into provenance.extra for audit transparency without recomputing.
        "confidence_terms": {
            **confidence_terms,
            "column_to_surface_uncertainty": _COLUMN_TO_SURFACE_UNCERTAINTY.get(
                indicator_id or "", "n_a",
            ),
        },
    }


def _confidence_terms_from_six_step_state(
    *,
    indicator_id: str | None,
    aoi: dict,
    time_range: tuple[str, str],
    n_observations: int,
    hf: float | None,
) -> dict:
    """Resolve the four A1 confidence-formula terms from six_step's local state.

    Centralised here so the six_step orchestrator stays small and the
    Nature indicators that DON'T go through six_step (KBA, DW composite,
    Hansen, ODIAC, etc.) can reuse the same shape via the engine.core
    public helpers when they construct their own confidence values.
    """
    if not indicator_id:
        # Without an indicator_id we can't look up the static QA, pixel area,
        # or expected revisit cadence — strict-None propagates.
        return {
            "qa": None, "n_valid": None,
            "anomaly_strength": None, "spatial_context": None,
        }
    return {
        "qa": compute_qa_term(indicator_id),
        "n_valid": compute_n_valid_term(
            indicator_id,
            n_observations=n_observations,
            window_days=_window_days(time_range),
        ),
        "anomaly_strength": compute_anomaly_strength_term(
            indicator_id, hf=hf,
        ),
        "spatial_context": compute_spatial_context_term(
            indicator_id, buffer_area_m2=_buffer_area_m2(aoi["radius_km"]),
        ),
    }


def _per_date_site_series(
    aoi: dict,
    image_collection: ee.ImageCollection,
    band: str,
    scale: float | None = None,
) -> list[float]:
    """DEPRECATED (M-TIER-A1 Step 8, 23 May 2026) — superseded by
    `_server_side_hf` for HF computation; no longer called by `six_step`.

    Retained here for any out-of-tree caller that imported it pre-Step-8
    and for the diagnostic tools that mirror its semantics inline. New
    code should call `_server_side_hf` instead — it (a) drops the
    100-image cap that hid temporal coverage for multi-swath assets like
    MODIS MAIAC GRANULES, and (b) does the HF arithmetic server-side
    rather than pulling per-date values to the client.

    Per-date Site_Buffer mean across `image_collection`. Capped at the
    most recent `_PER_DATE_SERIES_MAX_OBSERVATIONS` images via `.limit(N)`
    because EE's compute graph aborted a `.map().getInfo()` chain once
    the collection grew past ~5000 elements. The output fed HF in
    pre-Step-8 six_step, which is what Step 8 lifted server-side.
    """
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

    fc = (
        image_collection
        .select(band)
        .limit(_PER_DATE_SERIES_MAX_OBSERVATIONS)
        .map(_reduce)
        .getInfo()
        or {}
    )
    features = fc.get("features", [])
    return [
        float(feat["properties"]["value"])
        for feat in features
        if feat.get("properties", {}).get("value") is not None
    ]
