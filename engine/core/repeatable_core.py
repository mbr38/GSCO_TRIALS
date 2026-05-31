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

import concurrent.futures
from datetime import date as _date, timedelta as _td
from typing import Iterable, NamedTuple

import ee

from engine.constants import (
    ANOMALY_Z_THRESHOLD,
    BACKGROUND_RING_MAX_KM,
    BACKGROUND_RING_RADIUS_MULTIPLE,
    CLIMATOLOGY_BASELINE_MIN_COMPUTABLE_DAYS,
    CLIMATOLOGY_BASELINE_MIN_DAYS,
    CLIMATOLOGY_BASELINE_SPARSE_MIN_VALID_DAYS,
    CLIMATOLOGY_DENOMINATOR_EXCLUDED_INDICATORS,
    CLIMATOLOGY_INDICATORS,
    LAND_MASK_FRACTION_MIN_THRESHOLD,
    NORMALISATION_K,
    SERVER_SIDE_HF_CHUNK_DAYS_DEFAULT,
    SERVER_SIDE_HF_CHUNK_DAYS_PER_INDICATOR,
    WIND_ATTRIBUTABILITY_INDICATORS,
)
from engine.core.buffers import background_ring, site_buffer
from engine.core.climatology import climatology_baseline, country_for_centroid
from engine.core.confidence import (
    compute_anomaly_strength_term,
    compute_indicator_confidence,
    compute_n_valid_term,
    compute_qa_term,
    compute_spatial_context_term,
)
from engine.core.fallback import (
    NO_FALLBACK,
    FallbackContext,
    FallbackOutcome,
    build_fallback_extra,
    resolve_fallback_plan,
    sliding_lookback_windows,
    sppy_window,
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

def _site_value_reduction(
    aoi: dict,
    image_collection: ee.ImageCollection,
    band: str,
    scale: float | None,
):
    """Build the server-side reduction for site value, *without* calling
    ``getInfo``. Returned object is an unevaluated ``ee.Dictionary`` whose
    materialised form is ``{band: mean_value_or_None}``.

    Shared between the standalone ``site_value`` path (one getInfo per
    indicator) and ``six_step``'s M-PERF-A1 batched path (one
    ``ee.Dictionary`` combining site + background, then a single getInfo
    for the pair). The site geometry is built internally so callers
    (including six_step) never need to thread ``site_buffer`` through
    twice — that keeps the reduction's pre-conditions in one place.
    """
    geom = site_buffer(aoi["centre"], aoi["radius_km"])
    img = image_collection.select(band).mean()
    return img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geom,
        scale=scale,
        bestEffort=True,
        maxPixels=int(1e9),
    )


def site_value(
    aoi: dict,
    image_collection: ee.ImageCollection,
    band: str,
    scale: float | None = None,
    *,
    _precomputed: dict | None = None,
) -> float:
    """Mean of `band` over Site_Buffer across `image_collection`.

    Raises `IndicatorComputeError` when the buffer has zero valid pixels.

    M-PERF-A1 — when ``_precomputed`` is supplied, it must be the already-
    materialised inner dict from the batched ``ee.Dictionary`` call in
    ``six_step``. Skips the reduceRegion round-trip and runs the same
    null-value error path on the supplied dict, so the failure mode is
    identical whether the call is batched or standalone.
    """
    if _precomputed is None:
        info = _site_value_reduction(aoi, image_collection, band, scale).getInfo()
    else:
        info = _precomputed
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

def _background_value_reduction(
    image_collection: ee.ImageCollection,
    ring: dict,
    band: str,
    *,
    seasonal: bool,
    scale: float | None,
):
    """Build the server-side reduction for background value, *without*
    calling ``getInfo``. Returned object is an unevaluated ``ee.Dictionary``
    whose materialised form is
    ``{f"{band}_median": ..., f"{band}_stdDev": ...}``.

    Shared with ``six_step``'s M-PERF-A1 batched path. The land-mask /
    seasonality / per-image mask composition is identical to
    ``background_value``'s pre-batching shape so the batched and
    unbatched dictionaries are interchangeable.
    """
    geom = ring["geometry"]
    mask = ring["mask"]
    ic = image_collection.select(band)
    if seasonal and _seasonality is not None:
        ic = _seasonality.same_month_filter(ic)
    if mask is not None:
        ic = ic.map(lambda img: img.updateMask(mask))
    img = ic.mean()
    reducers = ee.Reducer.median().combine(ee.Reducer.stdDev(), sharedInputs=True)
    return img.reduceRegion(
        reducer=reducers,
        geometry=geom,
        scale=scale,
        bestEffort=True,
        maxPixels=int(1e9),
    )


def background_value(
    aoi: dict,
    image_collection: ee.ImageCollection,
    band: str,
    seasonal: bool = True,
    scale: float | None = None,
    *,
    ring: dict | None = None,
    _precomputed: dict | None = None,
) -> tuple[float, float]:
    """Median and stdDev of `band` over Background_Ring.

    When `seasonal=True` and `engine/core/seasonality.py` is available, the
    image collection is filtered to the same calendar months as the analysis
    window (§0.6). Until that module exists, the seasonal filter is a no-op.

    M-TIER-A3 Step E — when `ring` is supplied by the caller (typically
    `six_step`), reuse it so the land-fraction `getInfo` round-trip is paid
    once per indicator rather than twice. The constructed ring dict is
    backward-compatible: legacy callers that pass nothing get the
    pre-milestone behaviour of internal construction.
    """
    # M-TIER-A3 Step B/C — background_ring returns a dict carrying the
    # land mask + geometric land_fraction. Step C consumes the mask via
    # per-image `updateMask` so the reduction only sees land pixels.
    if ring is None:
        ring = background_ring(aoi["centre"], aoi["radius_km"])
    mask = ring["mask"]

    # M-TIER-A3 Step D / LM7 — when masking is enabled and the geometric
    # land fraction is below the threshold, the residual land set is too
    # small to support a meaningful background reduction. Fire the
    # existing ring-empty skip path with a *distinct* reason so analytics
    # can separate "almost all ocean" from "ring empty for indicator-
    # specific reasons (sparse overpass, all cloudy)". User-facing
    # message stays the same — both subtypes route through the
    # `background_ring_no_data` skipped_reason renderer (spec §3.5,
    # `Inspection.js` Q-A3-1 recommendation).
    #
    # M-PERF-A1 — this check stays in place even on the ``_precomputed``
    # batched path so the batched and standalone call shapes raise the
    # same error in the same conditions.
    if mask is not None and ring["land_fraction"] < LAND_MASK_FRACTION_MIN_THRESHOLD:
        raise BackgroundRingNoDataError(
            indicator_id=band,
            reason=(
                f"ring_empty_post_land_mask: geometric land fraction "
                f"{ring['land_fraction']:.3f} is below the "
                f"{LAND_MASK_FRACTION_MIN_THRESHOLD:.2f} threshold "
                f"(buffer={aoi['radius_km']}km centre={aoi['centre']}) — "
                "ring is effectively over water"
            ),
        )

    if _precomputed is None:
        # TODO(M3+): wire same-month filter once engine/core/seasonality.py lands.
        info = _background_value_reduction(
            image_collection, ring, band, seasonal=seasonal, scale=scale,
        ).getInfo()
    else:
        info = _precomputed
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
# M-DIAG-A4 — climatology-baseline temporal denominator
# ---------------------------------------------------------------------------
# The anomaly detector's denominator was the *spatial* std of the time-averaged
# ring (`background_value`'s second return). M-DIAG-A3 (H1c) showed that is the
# wrong scale: per-day *temporal* deviations were being normalised by a spatial
# spread 2-14× too small, inflating per-day z into magnitude artefacts. The fix
# replaces that denominator with the *temporal* std of the site's per-day value
# series over a trailing clean prior period. `bg_median` (the spatial median of
# the ring) is unchanged — only the normalisation scale becomes temporal.

def _climatology_window(
    time_range: tuple[str, str],
    *,
    min_days: int = CLIMATOLOGY_BASELINE_MIN_DAYS,
) -> tuple[str, str, int] | None:
    """Trailing climatology window for the temporal denominator (DGC1).

    Baseline length = ``max(min_days, screening_window_length)`` trailing,
    ending at the screening-window start (exclusive). Returns
    ``(clim_start_iso, clim_end_iso, baseline_days)`` or ``None`` when
    ``time_range`` is not a parseable ISO pair (e.g. the ``("static",
    "static")`` sentinel reference-data indicators use — those never reach
    here via six_step, but the guard keeps the helper total).
    """
    try:
        start = _date.fromisoformat(time_range[0])
    except (TypeError, ValueError, IndexError):
        return None
    win_days = _window_days(time_range)
    baseline_days = max(min_days, win_days if win_days is not None else min_days)
    clim_start = start - _td(days=baseline_days)
    return clim_start.isoformat(), start.isoformat(), baseline_days


def _temporal_std(values: list[float]) -> tuple[float | None, int]:
    """Population std of a per-day site series (matches EE ``Reducer.stdDev``).

    Returns ``(std, n_valid_days)``. ``std`` is ``None`` when there are fewer
    than ``CLIMATOLOGY_BASELINE_MIN_COMPUTABLE_DAYS`` observations (a std needs
    at least two). Population (ddof=0) std is used so the temporal denominator
    matches the EE reducer the spatial std it replaces was computed with.
    """
    import statistics as _stats
    n = len(values)
    if n < CLIMATOLOGY_BASELINE_MIN_COMPUTABLE_DAYS:
        return None, n
    return _stats.pstdev(values), n


def _climatology_bg_std(
    aoi: dict,
    image_collection: ee.ImageCollection,
    envelope,
    band: str,
    time_range: tuple[str, str],
    scale: float | None,
    *,
    indicator_id: str | None,
) -> tuple[float | None, int, int | None]:
    """Temporal σ of the site's per-day series over a trailing prior period.

    Site-level (Q-DGC-A: a single per-day series at the site over the clean
    prior window, not per-ring-pixel). Reuses the tested per-day reducer
    ``engine.core.trend._server_side_day_means`` (DGC4 — compose with existing
    infra rather than re-deriving the chunked server-side day aggregation).

    Returns ``(bg_std_temporal | None, n_valid_days, baseline_days | None)``.
    ``bg_std_temporal`` is ``None`` when the window can't be built or the prior
    period yields < 2 valid days; callers then leave the spatial std in place.
    """
    win = _climatology_window(time_range)
    if win is None:
        return None, 0, None
    clim_start, clim_end, baseline_days = win
    if clim_end <= clim_start:
        return None, 0, baseline_days

    # Lazy import — trend.py imports helpers FROM repeatable_core, so a
    # module-level import here would be circular (mirrors six_step's local
    # import of engine.core.wind).
    from engine.core.trend import _server_side_day_means

    try:
        clim_ic = (
            image_collection
            .filterDate(clim_start, clim_end)
            .filterBounds(envelope.bounds())
        )
        series = _server_side_day_means(
            aoi, clim_ic, band, scale,
            time_range=(clim_start, clim_end), indicator_id=indicator_id,
        )
    except Exception as exc:  # noqa: BLE001 — denominator never crashes the indicator
        # Mirror six_step's wind-block precedent: a sampling failure degrades
        # gracefully (caller keeps the spatial std + flags
        # clim_baseline_applied=False) rather than failing the whole indicator,
        # but it is LOUD so dev / regen runs surface it — the wind module's
        # silent-degrade regression is the cautionary tale here.
        import warnings as _warnings
        _warnings.warn(
            f"climatology-baseline denominator degraded to spatial std for "
            f"{indicator_id!r}: {type(exc).__name__}: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        return None, 0, baseline_days

    values = [value for _iso, value in series]
    std, n_valid_days = _temporal_std(values)
    return std, n_valid_days, baseline_days


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


_MS_PER_UTC_DAY: int = 86_400_000

# v1.x followup #1 — the legacy module-level `_SERVER_SIDE_HF_CHUNK_DAYS`
# constant has been replaced by per-indicator values in
# `engine.constants.SERVER_SIDE_HF_CHUNK_DAYS_PER_INDICATOR`, with
# `SERVER_SIDE_HF_CHUNK_DAYS_DEFAULT` as the fallback. Low-cadence
# indicators (~1 image/day) get chunk_days = 90 = full window → single-
# chunk fast path; high-cadence multi-swath products (AOD, CH4) keep
# 10-day chunks to stay under EE's 5-minute getInfo timeout.


# v1.x followup #2 — when the chunked path is taken (i.e. > 1 chunk), the
# per-chunk getInfo calls are network-bound and independent, so they run
# concurrently via ThreadPoolExecutor. Max concurrency is capped at AOD's
# worst case (90-day window / 10-day chunks = 9 chunks); higher values
# don't add speedup with our current indicator set. EE's per-user
# concurrent-request limit is typically ~40, leaving comfortable headroom.
_SERVER_SIDE_HF_MAX_CONCURRENCY: int = 9


def _date_chunks_iso(
    time_range: tuple[str, str],
    chunk_days: int = SERVER_SIDE_HF_CHUNK_DAYS_DEFAULT,
) -> list[tuple[str, str]]:
    """Split an ISO-date window into half-open chunks of `chunk_days` each.

    The final chunk may be shorter. Returns a list of `(start_iso, end_iso)`
    pairs where `end_iso` is exclusive (the next chunk's start). Used by
    `_server_side_hf` to keep each per-chunk `getInfo()` bounded.
    """
    from datetime import date as _date, timedelta as _td
    try:
        start = _date.fromisoformat(time_range[0])
        end   = _date.fromisoformat(time_range[1])
    except (TypeError, ValueError):
        # Caller passed a non-ISO range (e.g. ("static", "static") for
        # reference data). Caller-side, _server_side_hf only runs on
        # ImageCollections where time_range is a real ISO pair, but be
        # defensive — single-chunk fallback.
        return [time_range]
    if end <= start:
        return [time_range]

    chunks: list[tuple[str, str]] = []
    cursor = start
    while cursor < end:
        next_cursor = min(cursor + _td(days=chunk_days), end)
        chunks.append((cursor.isoformat(), next_cursor.isoformat()))
        cursor = next_cursor
    return chunks


def _process_chunk_for_server_side_hf(
    selected: ee.ImageCollection,
    chunk: tuple[str, str] | None,
    per_image,
) -> tuple[set[int], set[int], int]:
    """Run one chunk's reduce + getInfo. Returns (valid_days, hot_days, granule_count).

    Extracted from the chunked loop body so the chunked path can submit
    each chunk to a ThreadPoolExecutor (v1.x followup #2). The single-
    chunk fast paths in `_server_side_hf` call it inline.

    `selected` is the band-selected ImageCollection (already filtered for
    bounds upstream). `chunk` is either an (iso_start, iso_end) date pair
    to filter further, or None to use `selected` unchanged. `per_image`
    is the closure over reducer + baseline state defined in
    `_server_side_hf` — closures-in-threads are safe (no pickling, GIL
    not held during EE network wait).
    """
    chunk_ic = selected if chunk is None else selected.filterDate(chunk[0], chunk[1])
    fc = chunk_ic.map(per_image)
    valid_fc = fc.filter(ee.Filter.eq("is_valid", 1))
    hot_fc   = fc.filter(ee.Filter.eq("is_hot",   1))
    # One getInfo per chunk: distinct-day arrays for the two validity
    # bands AND the raw granule count for this chunk. The granule count
    # piggybacks on the existing dict so we don't pay an extra round-trip
    # (M-UI-A1-SURFACE engine-gap fix, 24 May 2026).
    chunk_result = ee.Dictionary({
        "valid_days":    valid_fc.aggregate_array("day_bucket").distinct(),
        "hot_days":      hot_fc.aggregate_array("day_bucket").distinct(),
        "granule_count": chunk_ic.size(),
    }).getInfo() or {}
    valid_days = {int(d) for d in (chunk_result.get("valid_days") or [])}
    hot_days   = {int(d) for d in (chunk_result.get("hot_days")   or [])}
    granule_count = int(chunk_result.get("granule_count") or 0)
    return valid_days, hot_days, granule_count


def _server_side_hf(
    aoi: dict,
    image_collection: ee.ImageCollection,
    band: str,
    bg_median: float,
    bg_std: float,
    z_threshold: float,
    scale: float | None,
    *,
    time_range: tuple[str, str] | None = None,
    indicator_id: str | None = None,
) -> "ServerSideHfResult":
    """Compute (n_valid_dates, HF, granule_count) over the collection server-side.

    Counts **distinct UTC days** (not granules) where the buffer was
    observable / crossed threshold. Two design properties matter:

      1. **Per-date semantics per IC_v4 §0.2 step 5.** HF is documented
         as the fraction of *dates* whose per-date z ≥ threshold, not
         the fraction of images. The legacy `_per_date_site_series`
         docstring already used the per-date framing implicitly. The
         pre-Step-8 code conflated granules with dates by `.limit(100)`-
         capping the granule collection; the post-Step-B uncapped code
         counted granules as independent observations (inflating
         `n_valid` for multi-swath products like MAIAC AOD at ~58
         granules/day). This version tags every per-granule Feature
         with a `day_bucket` integer and counts distinct day_buckets
         at the FeatureCollection level — correct per-date semantics.

      2. **Chunked client-side loop to stay under EE's 5-min wall.**
         At Distrito Federal scale (43 km buffer × 5 200 AOD granules
         over 90 days), a single `getInfo()` over the unchunked
         collection hits `HttpError 400 Computation timed out` at 300s.
         An earlier attempt to fix this by daily-mosaicing inside
         server-side `ee.List.map(Filter.eq(...))` hit a *different*
         EE limit ("User memory limit exceeded") because Filter.eq
         per day forces EE to materialise the full property index for
         each filter pass. This version splits `time_range` into
         `_SERVER_SIDE_HF_CHUNK_DAYS`-day chunks client-side; each
         chunk's compute graph is bounded by ~chunk_days × per-day
         granules ≈ 580 reduceRegions for AOD, well under timeout.
         Day-bucket sets accumulate client-side across chunks. Trades
         1 big `getInfo` for ~9 small `getInfo`s at 90-day windows;
         total wall-clock is comparable or better, no timeout risk.

    Per granule (inside each chunk):

      1. reduceRegion with a *combined* Mean + Count reducer over
         Site_Buffer at `scale`. Mean may be null when the band is
         fully masked over the buffer, but Count is *always* a real
         Number (0 when no valid pixels, ≥1 otherwise). `is_valid` is
         derived from Count, sidestepping the null-propagation problem.
      2. `is_hot   = (z >= z_threshold) AND is_valid`, where the z math
         uses the steady-state (bg_median, bg_std) baseline from steps 1+2.
         The mean is guarded with `If(is_valid, mean, 0)` so invalid rows
         don't crash arithmetic.
      3. The granule's `system:time_start` is floor-divided by one UTC
         day (86 400 000 ms) and stored as `day_bucket`. For non-UTC
         AOIs, swaths near local midnight may fall into the "previous"
         or "next" local day — fine for HF semantics (day-distinctness
         only), worth being explicit so future maintainers don't
         misread. A local-solar-day extension is a future Tier-C item.

    Per chunk (client-side accumulator):

      The chunk's FeatureCollection is filtered to `is_valid==1` /
      `is_hot==1`, then `aggregate_array("day_bucket").distinct()` runs
      server-side — feature-level operations on ~580 small features per
      chunk, never image-level. The two distinct-day arrays are returned
      as a single dict (one `getInfo()` per chunk), and the day-buckets
      are union'd into client-side Python sets across chunks.

    Returns:
        A ``ServerSideHfResult`` named tuple with four fields:

        n_valid_dates: count of distinct UTC days (across the full
                 `time_range`) with at least one granule whose buffer
                 was usable. Feeds the A1 confidence formula's N_valid
                 term via `compute_n_valid_term(n_observations=...)`.
                 Also surfaced in ``provenance.extra.n_valid_dates`` for
                 audit transparency (the close-entry's promised dates-
                 vs-granules disambiguation lives here).
        hf:      `n_hot_days / n_valid_days` as a float in [0, 1], or
                 `None` when `bg_std <= 0` (degenerate background) or
                 `n_valid_dates == 0` (no data — strict-None propagates).
        granule_count: raw image count across the full `time_range`
                 (before per-date dedup). Always ≥ ``n_valid_dates`` for
                 multi-swath / multi-orbit products; equal for daily-
                 single-image products. Informational only — never
                 enters score arithmetic. Surfaced in
                 ``provenance.extra.granule_count`` so audit reviewers
                 can see the rate at which the engine collapsed many
                 swaths into per-date evidence.

    Args:
        time_range: required for chunking. When None, falls back to a
                    single unchunked call — only safe for tests with
                    small collections.

    Design note on null handling. An earlier draft used a sentinel
    passed to `ee.Dictionary.get(key, default)` to detect masked-band
    cases, but EE's `get(key, default)` returns `default` only when
    the key is *absent* — not when the key is present and maps to
    `null`. `reduceRegion` produces `{band: null}` when the band is
    fully masked, so the sentinel never fired and downstream
    `ee.Number(null)` raised. The Count reducer in the combined
    Mean+Count is the fix: Count returns 0 (not null) for fully-
    masked images, so `is_valid` derives safely.
    """
    geom = site_buffer(aoi["centre"], aoi["radius_km"])
    bg_std_degenerate = bg_std <= 0

    mean_count_reducer = ee.Reducer.mean().combine(
        reducer2=ee.Reducer.count(),
        sharedInputs=True,
    )
    # M-DIAG-A1 FIX (29 May 2026). EE auto-suffixes outputs when reducers
    # are combined via `sharedInputs=True` — the mean output's actual key
    # is `{band}_mean`, not the bare band name. The legacy code read
    # `{band}` and hit the absent-key default 0.0, silently zeroing every
    # per-day site_mean and turning the per-day HF detector into a
    # sign-of-bg_median oracle for the M-TIER-A1 Step 8 path. See
    # docs/M-DIAG-A1_diagnosis_report.md §7.
    mean_key  = f"{band}_mean"
    count_key = f"{band}_count"

    def per_image(image: ee.Image) -> ee.Feature:
        reduction = image.select(band).reduceRegion(
            reducer=mean_count_reducer,
            geometry=geom,
            scale=scale,
            bestEffort=True,
            maxPixels=int(1e9),
        )
        count = ee.Number(reduction.get(count_key, 0))
        is_valid = count.gt(0)
        site_mean = ee.Number(
            ee.Algorithms.If(is_valid, reduction.get(mean_key, 0.0), 0.0)
        )
        if bg_std_degenerate:
            is_hot = ee.Number(0)
        else:
            z = site_mean.subtract(bg_median).divide(bg_std)
            is_hot = z.gte(z_threshold).And(is_valid)
        # Day-bucket tag — see docstring §3.
        day_bucket = ee.Number(image.get("system:time_start")).divide(
            _MS_PER_UTC_DAY,
        ).floor()
        return ee.Feature(None, {
            "is_valid":   is_valid,
            "is_hot":     is_hot,
            "day_bucket": day_bucket,
        })

    # Decide chunking. Three paths:
    #   1. `time_range` is missing — single call over the whole collection
    #      (tests + unusual callers). No filterDate; no chunk lookup.
    #   2. `chunk_days >= window_days` (v1x followup #1, 24 May 2026) —
    #      low-cadence indicator's full window fits in one call. Skip
    #      `_date_chunks_iso` entirely; reuse the no-filterDate path with
    #      the upstream-filtered ic_window (already date-bounded by
    #      `six_step`).
    #   3. Otherwise — per-indicator chunked path. Use the indicator-
    #      specific value from
    #      `SERVER_SIDE_HF_CHUNK_DAYS_PER_INDICATOR`, falling through to
    #      `SERVER_SIDE_HF_CHUNK_DAYS_DEFAULT` (10 days) when the indicator
    #      isn't in the lookup. Each chunk filters the collection by date.
    chunks: list[tuple[str, str] | None]
    if time_range is None:
        chunks = [None]
    else:
        chunk_days = SERVER_SIDE_HF_CHUNK_DAYS_PER_INDICATOR.get(
            indicator_id or "", SERVER_SIDE_HF_CHUNK_DAYS_DEFAULT,
        )
        win_days = _window_days(time_range)
        if win_days is None or chunk_days >= win_days:
            # Fast path: one call over the upstream-filtered collection.
            chunks = [None]
        else:
            chunks = list(_date_chunks_iso(time_range, chunk_days=chunk_days))

    valid_days_seen: set[int] = set()
    hot_days_seen:   set[int] = set()
    granule_count_total = 0

    selected = image_collection.select(band)

    # v1.x followup #2 — concurrent chunks. Each chunk's getInfo() is an
    # independent network-bound EE call; threading parallelises the wait
    # without GIL conflict. Fast paths (`len(chunks) == 1`) skip the
    # executor entirely so single-call indicators don't pay the pool
    # creation overhead.
    if len(chunks) > 1:
        max_workers = min(_SERVER_SIDE_HF_MAX_CONCURRENCY, len(chunks))
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
        ) as executor:
            futures = [
                executor.submit(
                    _process_chunk_for_server_side_hf,
                    selected, chunk, per_image,
                )
                for chunk in chunks
            ]
            for future in concurrent.futures.as_completed(futures):
                chunk_valid, chunk_hot, chunk_n = future.result()
                # Set union deduplicates day_buckets that happen to land
                # in two chunks (test 3.3c pins this invariant).
                valid_days_seen |= chunk_valid
                hot_days_seen   |= chunk_hot
                granule_count_total += chunk_n
    else:
        chunk_valid, chunk_hot, chunk_n = _process_chunk_for_server_side_hf(
            selected, chunks[0], per_image,
        )
        valid_days_seen |= chunk_valid
        hot_days_seen   |= chunk_hot
        granule_count_total += chunk_n

    n_valid_dates = len(valid_days_seen)
    n_hot         = len(hot_days_seen)

    # M-WIND-A1 v2.0 — sorted ISO UTC dates of the hot/anomaly days. Sorted
    # so downstream consumers (engine.core.wind) see a deterministic order
    # for per-day ERA5 sampling and for the audit-friendly ``wind_data_window``
    # provenance field.
    anomaly_dates_utc = (
        sorted(_day_bucket_to_iso(d) for d in hot_days_seen)
        if hot_days_seen else []
    )

    if n_valid_dates == 0:
        return ServerSideHfResult(0, None, granule_count_total, None)
    if bg_std_degenerate:
        # HF is undefined, but anomaly_dates_utc was computed against a
        # degenerate baseline so the set is meaningless — return empty
        # rather than the unreliable list.
        return ServerSideHfResult(n_valid_dates, None, granule_count_total, [])
    return ServerSideHfResult(
        n_valid_dates,
        n_hot / n_valid_dates,
        granule_count_total,
        anomaly_dates_utc,
    )


class ServerSideHfResult(NamedTuple):
    """Return shape for ``_server_side_hf``.

    Added in the M-UI-A1-SURFACE engine-gap fix (24 May 2026): the
    legacy ``(n_valid, hf)`` 2-tuple folded the distinct-dates count
    and granule count into the same opaque integer, leaving the
    audit-transparency dates-vs-granules disambiguation un-surfaceable
    downstream. The named tuple lets every caller pick the field by
    name; positional unpacking (``n, h, g = _server_side_hf(...)``)
    still works for callers that want it.

    M-WIND-A1 v2.0 (28 May 2026) — added ``anomaly_dates_utc`` so the
    wind-attribution module (engine.core.wind) can sample ERA5 wind on
    exactly the dates where the indicator crossed the anomaly z-threshold.
    Before this, ``hot_days_seen`` was computed inside ``_server_side_hf``
    and then discarded once the HF ratio was returned. The field is None
    when no anomaly days were observed (n_valid_dates == 0 path) and an
    empty list when the bg_std-degenerate path fires (HF undefined). For
    indicators outside the wind-attribution scope the field rides through
    unread, which preserves the strict-None semantics elsewhere.
    """

    n_valid_dates:     int
    hf:                float | None
    granule_count:     int
    # Default to None so test fixtures and smoke tools that pre-date
    # M-WIND-A1 v2.0 keep constructing the tuple as a 3-arg call without
    # breakage. In-engine constructions (the three return paths above) pass
    # the field explicitly so production behaviour is unaffected.
    anomaly_dates_utc: list[str] | None = None


# Day-bucket → ISO UTC date. ``day_bucket`` is the integer EE writes when
# we floor ``system:time_start`` (ms since UTC epoch) by one UTC day, so
# adding it as a day-delta to 1970-01-01 reverses the operation.
_UTC_EPOCH: _date = _date(1970, 1, 1)


def _day_bucket_to_iso(day_bucket: int) -> str:
    return (_UTC_EPOCH + _td(days=int(day_bucket))).isoformat()


# ---------------------------------------------------------------------------
# M-GHG-REDESIGN-A1 — per-image site + ring series
# ---------------------------------------------------------------------------
# `six_step` reduces the background ring exactly once (to a static
# bg_median / bg_std). The VIIRS sustained-contrast re-grammar needs the
# *per-timestep* contrast of the site against its background ring, so it
# needs both site_mean AND ring_mean for every image in the window — data
# the spatial-baseline path never surfaced (recon §3,
# docs/M-GHG-REDESIGN-A1_step_a_findings.md). This helper provides exactly
# that: a per-UTC-day series of (site_mean, ring_mean), reusing the same
# server-side per-image FeatureCollection + chunking machinery as
# `_server_side_hf` so it stays under EE's 5-minute getInfo wall.
#
# Deliberately generic (not VIIRS-specific) so other ring-relative
# per-timestep signals can reuse it; today only VIIRS calls it. Attributability
# is preserved by construction — every value is site-vs-its-own-ring, never
# absolute regional brightness (spec §0 invariant).


class PerImageSiteRingSeries(NamedTuple):
    """Return shape for ``per_image_site_ring_series``.

    ``timesteps`` is a list of ``(iso_date, site_mean, ring_mean)`` tuples,
    one per distinct UTC day on which BOTH the site buffer and the
    (land-masked) background ring had at least one valid pixel, sorted by
    date. ``granule_count`` is the raw image count before per-day dedup
    (informational, mirrors ServerSideHfResult). When a day carries more
    than one granule the per-day value is the mean of that day's granules
    (VIIRS VNP46A2 is a daily product, so this is normally 1:1).
    """

    timesteps:     list[tuple[str, float, float]]
    granule_count: int


def per_image_site_ring_series(
    aoi: dict,
    image_collection: ee.ImageCollection,
    band: str,
    time_range: tuple[str, str],
    *,
    scale: float | None = None,
    ring: dict | None = None,
    indicator_id: str | None = None,
) -> PerImageSiteRingSeries:
    """Per-UTC-day series of (site_mean, ring_mean) over the window.

    Mirrors ``_server_side_hf``'s per-image FeatureCollection + day-bucket +
    chunked-getInfo design, but emits the raw per-image site and ring means
    instead of collapsing them to a scalar HF. The background ring is
    land-masked exactly as ``_background_value_reduction`` does (so site and
    ring share the same land-pixel convention).

    A timestep is included only when BOTH reductions saw at least one valid
    pixel (site_count > 0 AND ring_count > 0) — a one-sided observation
    can't yield a ring-relative contrast. Per-day collapse averages any
    same-day granules.

    Returns an empty ``timesteps`` list (not an error) when no day had both
    site and ring coverage; the VIIRS caller maps that to a None score
    ("no data, no claim", CLAUDE.md §7). Raising is the caller's choice.
    """
    site_geom = site_buffer(aoi["centre"], aoi["radius_km"])
    if ring is None:
        ring = background_ring(aoi["centre"], aoi["radius_km"])
    ring_geom = ring["geometry"]
    ring_mask = ring["mask"]

    mean_count_reducer = ee.Reducer.mean().combine(
        reducer2=ee.Reducer.count(), sharedInputs=True,
    )
    mean_key  = f"{band}_mean"
    count_key = f"{band}_count"

    def per_image(image: ee.Image) -> ee.Feature:
        img = image.select(band)
        site_red = img.reduceRegion(
            reducer=mean_count_reducer, geometry=site_geom, scale=scale,
            bestEffort=True, maxPixels=int(1e9),
        )
        # Land-mask the ring read so it matches background_value's land
        # convention (M-TIER-A3). The site buffer is intentionally NOT
        # land-masked — site coverage is judged on raw pixels.
        ring_img = img.updateMask(ring_mask) if ring_mask is not None else img
        ring_red = ring_img.reduceRegion(
            reducer=mean_count_reducer, geometry=ring_geom, scale=scale,
            bestEffort=True, maxPixels=int(1e9),
        )
        site_count = ee.Number(site_red.get(count_key, 0))
        ring_count = ee.Number(ring_red.get(count_key, 0))
        is_valid = site_count.gt(0).And(ring_count.gt(0))
        site_mean = ee.Number(
            ee.Algorithms.If(site_count.gt(0), site_red.get(mean_key, 0.0), 0.0)
        )
        ring_mean = ee.Number(
            ee.Algorithms.If(ring_count.gt(0), ring_red.get(mean_key, 0.0), 0.0)
        )
        day_bucket = ee.Number(image.get("system:time_start")).divide(
            _MS_PER_UTC_DAY,
        ).floor()
        return ee.Feature(None, {
            "is_valid":   is_valid,
            "site_mean":  site_mean,
            "ring_mean":  ring_mean,
            "day_bucket": day_bucket,
        })

    # Chunk identically to _server_side_hf so we stay under EE's getInfo wall.
    if time_range is None:
        chunks: list[tuple[str, str] | None] = [None]
    else:
        chunk_days = SERVER_SIDE_HF_CHUNK_DAYS_PER_INDICATOR.get(
            indicator_id or "", SERVER_SIDE_HF_CHUNK_DAYS_DEFAULT,
        )
        win_days = _window_days(time_range)
        if win_days is None or chunk_days >= win_days:
            chunks = [None]
        else:
            chunks = list(_date_chunks_iso(time_range, chunk_days=chunk_days))

    selected = image_collection.select(band)
    # day_bucket -> list of (site_mean, ring_mean) for same-day granules.
    by_day: dict[int, list[tuple[float, float]]] = {}
    granule_total = 0

    def _process(chunk: tuple[str, str] | None) -> dict:
        chunk_ic = selected if chunk is None else selected.filterDate(chunk[0], chunk[1])
        valid_fc = chunk_ic.map(per_image).filter(ee.Filter.eq("is_valid", 1))
        return ee.Dictionary({
            "day":  valid_fc.aggregate_array("day_bucket"),
            "site": valid_fc.aggregate_array("site_mean"),
            "ring": valid_fc.aggregate_array("ring_mean"),
            "granule_count": chunk_ic.size(),
        }).getInfo() or {}

    if len(chunks) > 1:
        max_workers = min(_SERVER_SIDE_HF_MAX_CONCURRENCY, len(chunks))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            results = list(ex.map(_process, chunks))
    else:
        results = [_process(chunks[0])]

    for res in results:
        granule_total += int(res.get("granule_count") or 0)
        days  = res.get("day")  or []
        sites = res.get("site") or []
        rings = res.get("ring") or []
        for d, s, r in zip(days, sites, rings):
            by_day.setdefault(int(d), []).append((float(s), float(r)))

    timesteps: list[tuple[str, float, float]] = []
    for day in sorted(by_day):
        pairs = by_day[day]
        site_avg = sum(p[0] for p in pairs) / len(pairs)
        ring_avg = sum(p[1] for p in pairs) / len(pairs)
        timesteps.append((_day_bucket_to_iso(day), site_avg, ring_avg))

    return PerImageSiteRingSeries(timesteps=timesteps, granule_count=granule_total)


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
    fallback: FallbackContext | None = None,
) -> dict:
    """Run the full IC_v4 §0.2 pipeline and return the standard result dict.

    Raises `IndicatorComputeError` if the site or background reduction yields
    no valid pixels for `band` in `time_range` (and no fallback recovers it).

    M-FALLBACK-A1 — when `fallback` is a `FallbackContext` (and not strict
    audit mode), zero-coverage failures are recovered where possible:

    - **1.1 SPPY** — a zero-pixel SITE buffer is retried over the
      same-period-previous-year window (or, for the sliding-lookback
      strategy, the first earlier window with coverage). Confidence ×0.60.
    - **1.2 climatology** — an unavailable BACKGROUND ring (water-only or
      empty) is replaced by the per-country climatology baseline, for the
      11 in-scope indicators. Confidence ×0.75.

    The composition follows the §4.5 decision table (`resolve_fallback_plan`).
    `fallback=None` (the default) is the pre-milestone path — no fallbacks,
    identical behaviour — which keeps every direct-call test unchanged.
    `aoi_scale_class` is emitted in the returned `fallback_extra` regardless.
    """
    # v1x followup #13 — filterBounds to the analysis envelope (= circle at
    # r_background_km, which encloses both site_buffer and background_ring).
    # The envelope, not site_buffer alone, is required: background_value
    # reduces over the ring (annulus from r_site to r_background) and would
    # silently lose granules that intersect only the ring if we filtered on
    # the smaller site_buffer. For granule footprints typical of v1 raster
    # assets (MAIAC ~1200 km, S5P L3 ~2600 km swaths) the two filters
    # produce identical reductions in practice — the envelope choice is the
    # principled safe default that survives smaller-footprint future assets.
    #
    # `.bounds()` (axis-aligned bbox) instead of the buffer circle: EE's
    # filterBounds-on-circle path triggers a cross-projection intersection
    # against the sinusoidal-projected MODIS NDVI IC (which goes through a
    # `.map(multiply+rename)` upstream); the .mean() reducer then fails
    # with "reduce.mean: Projection error: Unable to compute intersection
    # of geometries in projections SR-ORG:6974 and EPSG:4326". The bounds
    # rectangle avoids that intersection path entirely. Verified empirically
    # across NDVI (MODIS sinusoidal), AOD (MODIS sinusoidal), and S5P L3
    # (EPSG:4326) — the bounds form works for all three. Net effect: a
    # slightly larger filter than the circle, but still ~24× smaller than
    # the unfiltered global pool for granule-based assets.
    r_background_km = min(
        BACKGROUND_RING_RADIUS_MULTIPLE * aoi["radius_km"],
        BACKGROUND_RING_MAX_KM,
    )
    analysis_envelope = site_buffer(aoi["centre"], r_background_km)
    ic_window = (
        image_collection
        .filterDate(time_range[0], time_range[1])
        .filterBounds(analysis_envelope.bounds())
    )

    # M-TIER-A3 Step E — construct the background ring once here so the
    # land-fraction `getInfo` round-trip is paid once per indicator. The
    # same dict is reused inside `background_value` (skipping its internal
    # construction) and surfaced in the return payload so pillar
    # `_format_result` functions can thread the three new MOD44W fields
    # into `provenance.extra` (spec §3.6).
    ring = background_ring(aoi["centre"], aoi["radius_km"])

    if fallback is None or fallback.strict_audit_mode:
        # Pre-milestone path (and strict audit mode, FB16): no fallbacks —
        # identical to the M-TIER-A3 behaviour. Any zero-coverage failure
        # propagates so the pillar dispatcher emits its skipped payload.
        #
        # M-PERF-A1 — batch site_value + background_value into one
        # ee.Dictionary so the no-fallback hot path pays one getInfo
        # round-trip instead of two. The two reductions share neither
        # geometry nor reducer kind (site=Mean over Site_Buffer,
        # background=Median+StdDev over the land-masked annulus), but
        # ee.Dictionary composes them server-side and one getInfo call
        # materialises both. Failure detection runs on the unpacked
        # dicts inside ``site_value`` / ``background_value`` via the
        # ``_precomputed`` kwarg, so the categorical raise-paths are
        # identical to the standalone code.
        #
        # The fallback path below intentionally does *not* batch — it
        # may re-call site_value over different image_collections (SPPY
        # windows) and may bypass the background reduction entirely
        # (climatology). Batching there would couple branches that need
        # independent retry semantics.
        combined = ee.Dictionary({
            "site": _site_value_reduction(aoi, ic_window, band, scale),
            "background": _background_value_reduction(
                ic_window, ring, band, seasonal=seasonal, scale=scale,
            ),
        }).getInfo() or {}
        site = site_value(
            aoi, ic_window, band, scale=scale,
            _precomputed=combined.get("site"),
        )
        bg_median, bg_std = background_value(
            aoi, ic_window, band, seasonal=seasonal, scale=scale, ring=ring,
            _precomputed=combined.get("background"),
        )
        fb_outcome = NO_FALLBACK
        hf_ic, hf_time_range = ic_window, time_range
    else:
        (
            site, bg_median, bg_std, fb_outcome, hf_ic, hf_time_range,
        ) = _resolve_with_fallback(
            aoi=aoi,
            image_collection=image_collection,
            envelope=analysis_envelope,
            ic_window=ic_window,
            band=band,
            time_range=time_range,
            ring=ring,
            seasonal=seasonal,
            scale=scale,
            indicator_id=indicator_id,
            fallback=fallback,
        )

    # M-DIAG-A4 — replace the spatial-std denominator with the temporal σ of
    # the site's per-day series over a trailing clean prior period (the H1c
    # fix). `bg_median` (spatial median of the ring) is unchanged; only the
    # normalisation *scale* becomes temporal. Global (operator decision 31 May
    # 2026): the replaced `bg_std` flows into the aggregate z (anomaly_z_hf),
    # the per-day HF detector (_server_side_hf), the composite severity score
    # (to_score), and the trend severity downstream. Computed for every path
    # incl. strict-audit — it is the primary denominator now, not a recovery
    # fallback. When the prior period yields a computable σ (≥ 2 valid days) it
    # is used unconditionally (a σ of 0 → the existing `bg_std <= 0` guards
    # strict-None z/hf/score, which is the correct "temporally uniform site"
    # behaviour); when it can't be computed, `bg_std` is left as the spatial
    # std and `clim_baseline_applied=False` is surfaced — a loud fallback, not
    # a silent default (CLAUDE.md §7).
    bg_std_spatial = bg_std
    # VIIRS exclusion (operator decision, Phase 3 / E2): night-lights have
    # near-zero temporal variance at stably-lit sites, so the temporal
    # denominator collapses (the mirror of the H1c spatial collapse). VIIRS
    # keeps its spatial-std denominator until a purpose-built lit-frequency ↔
    # GHG method lands (docs/v1x_followups.md). Skip the EE sample entirely.
    clim_excluded = indicator_id in CLIMATOLOGY_DENOMINATOR_EXCLUDED_INDICATORS
    if clim_excluded:
        clim_bg_std, clim_valid_days, clim_baseline_days = None, 0, None
    else:
        clim_bg_std, clim_valid_days, clim_baseline_days = _climatology_bg_std(
            aoi, image_collection, analysis_envelope, band, time_range, scale,
            indicator_id=indicator_id,
        )
    clim_applied = (not clim_excluded) and clim_bg_std is not None
    if clim_applied:
        bg_std = clim_bg_std
    clim_denominator_extra = {
        "clim_baseline_applied": clim_applied,
        "clim_baseline_excluded": clim_excluded,
        "clim_baseline_days": clim_baseline_days,
        "clim_baseline_valid_days": clim_valid_days,
        "clim_baseline_sparse": bool(
            clim_applied
            and clim_valid_days < CLIMATOLOGY_BASELINE_SPARSE_MIN_VALID_DAYS
        ),
        "bg_std_temporal": clim_bg_std,
        "bg_std_spatial": bg_std_spatial,
    }

    # M-TIER-A1 Step 8 — server-side N_valid + HF. Replaces the
    # client-side `_per_date_site_series` + `anomaly_z_hf(series)` path
    # which had a 100-image cap that under-reported n_observations for
    # multi-swath / multi-orbit assets (see tools/diag_aod_ch4_controls.py).
    # `anomaly_z_hf` is still called with an empty series to compute
    # anomaly + z from the steady-state values; HF is overwritten with
    # the server-side count below.
    azhf = anomaly_z_hf(site, bg_median, bg_std, [], z_threshold=z_threshold)
    # HF + N_valid use the *effective* window — when SPPY recovered the site,
    # that's the previous-year window where data actually exists; otherwise
    # it's the current window. Without this, an SPPY-recovered site would
    # still draw N_valid=0 from the empty current window and strict-None the
    # whole confidence, defeating the 0.60 fallback penalty.
    hf_result = _server_side_hf(
        aoi, hf_ic, band, bg_median, bg_std, z_threshold, scale,
        time_range=hf_time_range,
        indicator_id=indicator_id,
    )
    azhf["hf"] = hf_result.hf

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
        time_range=hf_time_range,
        n_observations=hf_result.n_valid_dates,
        hf=azhf["hf"],
    )
    confidence = compute_indicator_confidence(
        indicator_id=indicator_id or "<unknown>",
        column_to_surface_uncertainty=_COLUMN_TO_SURFACE_UNCERTAINTY.get(
            indicator_id or "", "n_a",
        ),
        temporal_fallback_applied=fb_outcome.temporal_used,
        climatology_fallback_applied=fb_outcome.climatology_used,
        **confidence_terms,
    )

    # M-WIND-A1 v2.0 — compute the wind-attribution provenance block for
    # in-scope indicators (NO₂, SO₂, HCHO, AAI, AOD). Wind attribution is
    # categorical (high / moderate / low / sparse) and lives in
    # provenance.extra; it does NOT feed `confidence` above (WA1). The
    # block uses the *effective* window (`hf_time_range`) so SPPY-recovered
    # indicators get wind sampled from the same period the indicator data
    # came from (WA23, Step B reconciliation #3 — collapses the planned
    # Step E composition pass to a window pass-through). Sparse-on-failure:
    # any EE exception during wind sampling is caught and degraded to a
    # sparse block rather than disrupting the main indicator payload.
    wind_extra: dict | None = None
    if indicator_id in WIND_ATTRIBUTABILITY_INDICATORS:
        from engine.core.wind import (  # local import — wind→repeatable_core would be circular if reversed
            compute_wind_attribution_extra,
            sparse_provenance_extra,
        )
        try:
            wind_extra = compute_wind_attribution_extra(
                centre=aoi["centre"],
                r_site_km=aoi["radius_km"],
                r_background_km=min(
                    BACKGROUND_RING_RADIUS_MULTIPLE * aoi["radius_km"],
                    BACKGROUND_RING_MAX_KM,
                ),
                image_collection=hf_ic,
                band=band,
                scale=scale,
                anomaly_dates_utc=hf_result.anomaly_dates_utc,
                wind_data_window=hf_time_range,
                ring_land_fraction=ring.get("land_fraction"),
                # M-DIAG-A2 §4.1 — let the wind module pick the AAI-safe
                # absolute-value ratio for sign-bearing indicators.
                indicator_id=indicator_id,
            )
        except Exception as exc:  # noqa: BLE001 — wind is informational; never crash the indicator
            # Emit a warning so dev / regen runs surface the silent-degrade
            # path. Production UI still gets the graceful sparse fallback
            # (WA1: wind never crashes the indicator). The original M-WIND-A1
            # v2.0 demo regen silently degraded every indicator to sparse
            # because an ee.Geometry kwarg-routing bug raised inside the
            # batched .getInfo() and nothing was logged — that class of
            # regression should be loud, not invisible.
            import warnings as _warnings
            _warnings.warn(
                f"wind attribution degraded to sparse for {indicator_id!r}: "
                f"{type(exc).__name__}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            wind_extra = sparse_provenance_extra(
                n_anomaly_days=len(hf_result.anomaly_dates_utc or []),
                wind_data_window=hf_time_range,
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
        # M-UI-A1-SURFACE engine-gap fix (24 May 2026): surface the raw
        # date and granule counts so pillar `_format_result` functions
        # can thread them into provenance.extra. Informational only —
        # never enters score arithmetic. See ServerSideHfResult.
        "n_valid_dates": hf_result.n_valid_dates,
        "granule_count": hf_result.granule_count,
        # M-WIND-A1 v2.0 — the dates (sorted ISO UTC) on which the indicator
        # crossed the anomaly z-threshold within the effective window.
        # Consumed by engine.core.wind to sample ERA5 wind on exactly those
        # dates; pillar `_format_result` threads it through provenance.extra
        # as audit transparency. None / empty list when no anomaly days exist.
        "anomaly_dates_utc": hf_result.anomaly_dates_utc,
        # M-TIER-A3 Step E — three new provenance.extra fields per spec §3.6.
        # Geometric land share of the background ring; whether the mask
        # was applied to the reduction; and the asset ID for vintage
        # tracking. Pillar `_format_result` functions copy these into
        # `extra` for audit transparency and future M-CLIM-A3b
        # composition. Always populated by the Step B/E pipeline.
        "ring_land_fraction":  ring["land_fraction"],
        "ring_land_mask_applied": ring["land_mask_applied"],
        "ring_land_mask_asset":   ring["land_mask_asset"],
        # M-FALLBACK-A1 §4.7 — additive provenance.extra fields recording
        # which fallback fired (or none). aoi_scale_class is always present.
        # Pillar `_format_result` functions merge this into provenance.extra.
        "fallback_extra": build_fallback_extra(
            radius_km=aoi["radius_km"],
            temporal_fallback_used=fb_outcome.temporal_used,
            temporal_fallback_strategy=fb_outcome.temporal_strategy,
            temporal_fallback_source_window=fb_outcome.temporal_window,
            climatology_fallback_used=fb_outcome.climatology_used,
            climatology_fallback_vintage=fb_outcome.climatology_vintage,
        ),
        # M-WIND-A1 v2.0 §5.4 — additive provenance.extra fields recording
        # the wind attributability state and the underlying numbers. None for
        # out-of-scope indicators (so pillar `_format_result` can skip the
        # merge for non-wind pollutants without further branching).
        "wind_extra": wind_extra,
        # M-DIAG-A4 — climatology-baseline denominator provenance. Records
        # whether the temporal σ replaced the spatial std, the trailing
        # baseline window length, the valid-day count, the sparse flag, and
        # both σ values for audit. Always present (the denominator runs on
        # every six_step path); pillar `_format_result` merges it into
        # provenance.extra alongside fallback_extra / wind_extra.
        "clim_denominator_extra": clim_denominator_extra,
    }


# ---------------------------------------------------------------------------
# M-FALLBACK-A1 — site/background resolution with the two fallbacks
# ---------------------------------------------------------------------------

def _window_ic(image_collection, envelope, window: tuple[str, str]):
    """Filter `image_collection` to `window` and the analysis envelope.

    Mirrors the inline construction in `six_step` so an SPPY / sliding
    window reduces over exactly the same spatial envelope as the current
    window — only the date range differs.
    """
    return (
        image_collection
        .filterDate(window[0], window[1])
        .filterBounds(envelope.bounds())
    )


def _recover_site(
    aoi, image_collection, envelope, band, time_range, scale, strategy,
) -> tuple[float | None, tuple[str, str] | None]:
    """Try to recover the site value over a previous window (1.1).

    For ``"sppy"`` there is one candidate (same period, previous year). For
    ``"sliding_lookback"`` the candidates step backward until one has
    coverage. Returns ``(value, window_used)`` or ``(None, None)`` if none
    of the candidates yields valid pixels.
    """
    if strategy == "sliding_lookback":
        candidates = sliding_lookback_windows(time_range)
    else:
        candidates = [sppy_window(time_range)]
    for window in candidates:
        ic = _window_ic(image_collection, envelope, window)
        try:
            return site_value(aoi, ic, band, scale=scale), window
        except SiteBufferNoDataError:
            continue
    return None, None


def _recover_ring(
    aoi, image_collection, envelope, band, window, seasonal, scale, ring,
) -> tuple[float, float] | None:
    """Try to recover the background ring over `window` (Mode C SPPY ring).

    Returns ``(median, std)`` or ``None`` if the ring is still empty.
    """
    ic = _window_ic(image_collection, envelope, window)
    try:
        return background_value(
            aoi, ic, band, seasonal=seasonal, scale=scale, ring=ring,
        )
    except BackgroundRingNoDataError:
        return None


def _try_climatology(aoi, indicator_id, fallback):
    """Look up the per-country climatology baseline for this indicator (1.2).

    Returns a ``ClimatologyBaseline`` or ``None`` when the indicator is out
    of the climatology scope (FB10), the centroid can't be resolved to a
    country, or no fixture entry exists.
    """
    if not indicator_id or indicator_id not in CLIMATOLOGY_INDICATORS:
        return None
    centre = aoi["centre"]
    country = country_for_centroid(centre["lat"], centre["lon"])
    return climatology_baseline(
        country, indicator_id, fixture=fallback.climatology_fixture,
    )


def _resolve_with_fallback(
    *,
    aoi,
    image_collection,
    envelope,
    ic_window,
    band,
    time_range,
    ring,
    seasonal,
    scale,
    indicator_id,
    fallback: FallbackContext,
):
    """Site + background resolution with the §4.5 fallback composition.

    Returns ``(site, bg_median, bg_std, FallbackOutcome, hf_ic,
    hf_time_range)``. ``hf_ic`` / ``hf_time_range`` are the window the SITE
    value came from, so the downstream HF + N_valid computation reflects
    where data actually exists. Re-raises the original
    ``SiteBufferNoDataError`` / ``BackgroundRingNoDataError`` when no
    fallback can recover the indicator — the pillar dispatcher then emits
    its skipped payload exactly as in the no-fallback path.
    """
    # --- current-window attempts (capture outcomes; do not raise yet) ---
    try:
        site = site_value(aoi, ic_window, band, scale=scale)
        site_ok, site_err = True, None
    except SiteBufferNoDataError as err:
        site, site_ok, site_err = None, False, err

    # Mode 1 — a structurally-water ring (land fraction below the mask
    # threshold) is detected from the ring dict directly; SPPY can't recover
    # a permanently-ocean ring, so we skip the current reduction and let
    # climatology fire.
    ring_is_water = bool(ring.get("land_mask_applied")) and (
        ring.get("land_fraction", 1.0) < LAND_MASK_FRACTION_MIN_THRESHOLD
    )

    bg_median = bg_std = None
    ring_err = None
    if ring_is_water:
        ring_ok = False
    else:
        try:
            bg_median, bg_std = background_value(
                aoi, ic_window, band, seasonal=seasonal, scale=scale, ring=ring,
            )
            ring_ok = True
        except BackgroundRingNoDataError as err:
            ring_ok, ring_err = False, err

    plan = resolve_fallback_plan(
        site_current_ok=site_ok,
        ring_current_ok=ring_ok,
        ring_is_water=ring_is_water,
        strict_audit_mode=False,  # strict mode never reaches this resolver
    )

    temporal_used = False
    temporal_strategy: str | None = None
    temporal_window: tuple[str, str] | None = None
    site_window = time_range  # the window the SITE value comes from

    # --- 1.1 SPPY — recover the site ---
    if not site_ok and plan.attempt_sppy_site:
        recovered, window_used = _recover_site(
            aoi, image_collection, envelope, band, time_range, scale,
            fallback.temporal_fallback_strategy,
        )
        if recovered is not None:
            site, site_ok = recovered, True
            temporal_used = True
            temporal_strategy = fallback.temporal_fallback_strategy
            temporal_window = window_used
            site_window = window_used

    if not site_ok:
        # Mode A / C with SPPY also empty → the indicator genuinely fails.
        raise site_err or SiteBufferNoDataError(
            indicator_id=band,
            reason="site buffer empty and SPPY fallback found no pixels either",
        )

    # --- ring recovery: SPPY ring (Mode C) then climatology (1.2) ---
    climatology_used = False
    climatology_vintage: str | None = None
    if not ring_ok:
        if plan.attempt_sppy_ring:
            sppy_w = temporal_window or sppy_window(time_range)
            recovered_ring = _recover_ring(
                aoi, image_collection, envelope, band, sppy_w,
                seasonal, scale, ring,
            )
            if recovered_ring is not None:
                bg_median, bg_std = recovered_ring
                ring_ok = True
                temporal_used = True
                temporal_strategy = fallback.temporal_fallback_strategy
                temporal_window = sppy_w
        if not ring_ok and plan.use_climatology:
            baseline = _try_climatology(aoi, indicator_id, fallback)
            if baseline is not None:
                bg_median, bg_std = baseline.median, baseline.std
                ring_ok = True
                climatology_used = True
                climatology_vintage = baseline.vintage

    if not ring_ok:
        raise ring_err or BackgroundRingNoDataError(
            indicator_id=band,
            reason=(
                "background ring unavailable; no SPPY ring and no "
                "climatology baseline for this country/indicator"
            ),
        )

    outcome = FallbackOutcome(
        temporal_used=temporal_used,
        temporal_strategy=temporal_strategy,
        temporal_window=temporal_window,
        climatology_used=climatology_used,
        climatology_vintage=climatology_vintage,
    )
    if site_window == time_range:
        hf_ic = ic_window
    else:
        hf_ic = _window_ic(image_collection, envelope, site_window)
    return site, bg_median, bg_std, outcome, hf_ic, site_window


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
