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
from typing import Iterable, NamedTuple

import ee

from engine.constants import (
    ANOMALY_Z_THRESHOLD,
    BACKGROUND_RING_MAX_KM,
    BACKGROUND_RING_RADIUS_MULTIPLE,
    NORMALISATION_K,
    SERVER_SIDE_HF_CHUNK_DAYS_DEFAULT,
    SERVER_SIDE_HF_CHUNK_DAYS_PER_INDICATOR,
)
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
        A ``ServerSideHfResult`` named tuple with three fields:

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

    if n_valid_dates == 0:
        return ServerSideHfResult(0, None, granule_count_total)
    if bg_std_degenerate:
        return ServerSideHfResult(n_valid_dates, None, granule_count_total)
    return ServerSideHfResult(
        n_valid_dates,
        n_hot / n_valid_dates,
        granule_count_total,
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
    """

    n_valid_dates: int
    hf:            float | None
    granule_count: int


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
    hf_result = _server_side_hf(
        aoi, ic_window, band, bg_median, bg_std, z_threshold, scale,
        time_range=time_range,
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
        time_range=time_range,
        n_observations=hf_result.n_valid_dates,
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
        # M-UI-A1-SURFACE engine-gap fix (24 May 2026): surface the raw
        # date and granule counts so pillar `_format_result` functions
        # can thread them into provenance.extra. Informational only —
        # never enters score arithmetic. See ServerSideHfResult.
        "n_valid_dates": hf_result.n_valid_dates,
        "granule_count": hf_result.granule_count,
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
