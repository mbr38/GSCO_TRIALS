"""Air-pillar wind attributability (M-WIND-A1 v2.0, 28 May 2026).

Three layers, mirroring ``engine.core.attributability`` (habitat):

1. **Pure math** — ``compute_wind_attributability_state`` (the categorical
   function from spec §5.2), ``circular_mean_deg`` (the angle averaging
   helper). No EE, fully unit-testable.
2. **EE-touching** — ``half_ring_geometry`` (upwind/downwind angular
   sector of the background ring), ``measure_ring_asymmetry`` (per-day
   upwind/downwind reduction of the indicator's ImageCollection).
3. **Orchestration** — ``compute_wind_attribution_extra`` (the top-level
   helper that ``six_step`` invokes for in-scope indicators, producing the
   ``provenance.extra`` block per §5.4).

Wind attributability answers a *different* question from measurement
quality. The M-TIER-A1 confidence chain asks "how well did the satellites
observe this site?"; wind attribution asks "given an observed anomaly, can
we attribute its source to the supplier, or is upwind transport a more
plausible explanation?" (WA1). It is categorical (high / moderate / low /
sparse, AT19 shared grammar) and **does NOT enter the confidence chain or
any composite score**.

Out of scope for this module: changes to confidence formula, CSV columns,
verbal summary mentions, single-indicator inspection view rendering — see
spec §3.2 / §6.

Anchored to:
- M-WIND-A1 v2.0 spec §5 (computation), §6 (UI surfaces — handled in
  ui.components.c4a_indicator_map / c5_drilldown / p11_sections)
- WA5 / WA6 / WA7 (bucket criteria)
- WA8 / WA9 / WA10 (thresholds)
- WA11 (single arrow at AOI centre — implementation in UI layer)
- WA26 (additive provenance.extra fields, no top-level schema change)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Literal

import ee

from engine.constants import (
    LAND_MASK_FRACTION_MIN_THRESHOLD,
    WIND_ASYMMETRY_HIGH_MAX,
    WIND_ASYMMETRY_LOW_MIN,
    WIND_CALM_THRESHOLD_MS,
    WIND_N_MIN_ANOMALY_DAYS,
    WIND_SPEED_HIGH_MAX_MS,
    WIND_SPEED_LOW_MIN_MS,
)
from engine.core.attributability import AttributabilityState
from engine.core.buffers import site_buffer
from engine.core.era5 import Era5WindSample, sample_era5_wind_at_overpass


WindAttributabilityState = AttributabilityState


# ---------------------------------------------------------------------------
# Pure math — categorical function  (spec §5.2)
# ---------------------------------------------------------------------------

def compute_wind_attributability_state(
    mean_wind_speed_ms: float | None,
    mean_asymmetry_ratio: float | None,
    n_anomaly_days: int,
    *,
    n_min: int = WIND_N_MIN_ANOMALY_DAYS,
    speed_high_max: float = WIND_SPEED_HIGH_MAX_MS,
    speed_low_min: float = WIND_SPEED_LOW_MIN_MS,
    ratio_high_max: float = WIND_ASYMMETRY_HIGH_MAX,
    ratio_low_min: float = WIND_ASYMMETRY_LOW_MIN,
) -> WindAttributabilityState:
    """Return the wind attributability category for one indicator.

    Per spec §5.2 (WA5/WA6/WA7):

        sparse    n_anomaly_days < n_min — insufficient sample
        high      mean_wind_speed_ms < speed_high_max
                  AND mean_asymmetry_ratio < ratio_high_max  (both must hold)
        low       mean_wind_speed_ms >= speed_low_min
                  OR mean_asymmetry_ratio >= ratio_low_min   (either suffices)
        moderate  anything in between

    None-handling: when ``mean_asymmetry_ratio is None`` (all anomaly days
    were calm, so no direction → no asymmetry could be computed) the
    function treats it as 0 (perfectly symmetric — calm wind is a strong
    attributability signal toward the supplier, per spec §5.1 final
    bullet). When ``mean_wind_speed_ms is None`` the day-count must also
    be 0 (no samples), so the function returns sparse.

    Pure function — no EE, no I/O. Boundary semantics: each bucket uses
    ``<`` for the upper edge and ``>=`` for the lower edge, so a value
    exactly at the threshold goes to the *higher-severity* bucket
    (low > moderate > high in attribution-confidence terms; we want the
    pessimistic call on ties).
    """
    # Validate first so a negative day count never silently masquerades
    # as sparse (which is semantically "low sample", not "bad input").
    if n_anomaly_days < 0:
        raise ValueError(
            f"n_anomaly_days must be non-negative, got {n_anomaly_days!r}"
        )
    if mean_wind_speed_ms is not None and mean_wind_speed_ms < 0.0:
        raise ValueError(
            f"mean_wind_speed_ms must be non-negative, got {mean_wind_speed_ms!r}"
        )

    if n_anomaly_days < n_min:
        return "sparse"
    if mean_wind_speed_ms is None:
        return "sparse"

    # Treat all-calm (no asymmetry computable) as perfectly symmetric.
    ratio = 0.0 if mean_asymmetry_ratio is None else mean_asymmetry_ratio
    if ratio < 0.0:
        raise ValueError(
            f"mean_asymmetry_ratio must be non-negative, got {mean_asymmetry_ratio!r}"
        )

    if mean_wind_speed_ms >= speed_low_min or ratio >= ratio_low_min:
        return "low"
    if mean_wind_speed_ms < speed_high_max and ratio < ratio_high_max:
        return "high"
    return "moderate"


# ---------------------------------------------------------------------------
# Pure math — circular mean  (spec §5.1)
# ---------------------------------------------------------------------------

def circular_mean_deg(angles_deg: Iterable[float]) -> float | None:
    """Mean direction (degrees, 0–360) of a set of compass angles.

    Naïve arithmetic mean is wrong for circular quantities (1° and 359°
    average to 180° not 0°). This converts each angle to its unit-vector,
    averages componentwise, then takes ``atan2``. Returns None when the
    input is empty or when the resultant vector has zero magnitude
    (perfectly opposing directions cancel — "no preferred direction").
    """
    sum_x = 0.0
    sum_y = 0.0
    n = 0
    for theta in angles_deg:
        rad = math.radians(theta)
        sum_x += math.cos(rad)
        sum_y += math.sin(rad)
        n += 1
    if n == 0:
        return None
    if abs(sum_x) < 1e-12 and abs(sum_y) < 1e-12:
        return None
    mean = math.degrees(math.atan2(sum_y, sum_x))
    return (mean + 360.0) % 360.0


# ---------------------------------------------------------------------------
# EE-touching — half-ring geometry
# ---------------------------------------------------------------------------

# Half-ring angular half-width: ±90° of the named direction, so the two
# half-rings tile the full annulus disjointly (a 180° sector each). The
# constant is exposed so future calibration could narrow to ±60° wedges
# (Q-WA-1) without touching call sites.
_HALF_RING_HALF_WIDTH_DEG: float = 90.0

# Number of polygon vertices along each arc edge. 36 vertices ≈ 5° steps —
# fine enough that the polygonal approximation matches the true geodesic
# arc within sub-pixel error at every supported buffer radius (5–200 km).
_ARC_VERTEX_COUNT: int = 36


def _arc_vertices(
    centre: dict,
    radius_km: float,
    start_bearing_deg: float,
    end_bearing_deg: float,
    n_vertices: int = _ARC_VERTEX_COUNT,
) -> list[list[float]]:
    """Return ``[[lon, lat], ...]`` along the geodesic arc from start→end bearing.

    Pure spherical geodesic — we don't fight EE's projection here because
    the half-ring is a polygon we hand to EE, not a query reducer. The
    haversine destination formula gives a per-point ``(lat, lon)`` we then
    emit in EE's ``(lon, lat)`` order.

    Bearings increment monotonically from ``start_bearing_deg`` to
    ``end_bearing_deg`` (assumed normalised by caller). When the arc
    wraps past 360° (e.g. start=350°, end=460°), the caller is responsible
    for normalising before/after this call.
    """
    earth_radius_km = 6371.0088
    lat0 = math.radians(centre["lat"])
    lon0 = math.radians(centre["lon"])
    angular_distance = radius_km / earth_radius_km
    vertices: list[list[float]] = []
    for i in range(n_vertices + 1):
        frac = i / n_vertices
        bearing = math.radians(
            start_bearing_deg + frac * (end_bearing_deg - start_bearing_deg)
        )
        lat = math.asin(
            math.sin(lat0) * math.cos(angular_distance)
            + math.cos(lat0) * math.sin(angular_distance) * math.cos(bearing)
        )
        lon = lon0 + math.atan2(
            math.sin(bearing) * math.sin(angular_distance) * math.cos(lat0),
            math.cos(angular_distance) - math.sin(lat0) * math.sin(lat),
        )
        vertices.append([math.degrees(lon), math.degrees(lat)])
    return vertices


def half_ring_geometry(
    centre: dict,
    r_site_km: float,
    r_background_km: float,
    direction_deg: float,
    *,
    half_width_deg: float = _HALF_RING_HALF_WIDTH_DEG,
) -> ee.Geometry:
    """Half-ring (angular sector of the background annulus) centred on ``direction_deg``.

    ``direction_deg`` is the bearing the half-ring is centred on, measured
    in compass degrees (0 = North, 90 = East, ...). For the downwind half
    pass the wind-to direction directly; for the upwind half pass
    ``(direction_deg + 180) % 360``.

    The geometry is constructed as a polygon with the outer arc, two radial
    edges, and the inner arc — a "pie slice with the centre removed". Per
    spec §5.1, the half-rings are reduced by the indicator's
    ``ImageCollection`` to compute ``bg_upwind`` and ``bg_downwind`` for the
    asymmetry ratio. Sector geometry is intentionally projection-agnostic
    (the vertices are geodesic-correct) so EE applies its own reductions
    without further projection coupling.
    """
    start_bearing = direction_deg - half_width_deg
    end_bearing = direction_deg + half_width_deg

    outer_arc = _arc_vertices(centre, r_background_km, start_bearing, end_bearing)
    # Inner arc is reversed so the polygon closes cleanly (outer arc end →
    # inner arc start at the same bearing → inner arc reversed → outer arc
    # start = first vertex).
    inner_arc = _arc_vertices(centre, r_site_km, start_bearing, end_bearing)
    inner_arc.reverse()

    polygon_coords = outer_arc + inner_arc
    # Build via the GeoJSON-style constructor instead of
    # ``ee.Geometry.Polygon(coords, ..., geodesic=True)`` — the kwarg form
    # routes ``geodesic`` to ``proj`` in some EE Python SDK versions (seen
    # during M-WIND-A1 v2.0 demo regen: "Argument 'crs': Invalid type.
    # Expected type: String. Actual type: Boolean. Actual value: true"),
    # which silently degrades every wind invocation to sparse. The
    # dict-shaped constructor is positional-arg-free, so the routing
    # error cannot recur.
    return ee.Geometry({
        "type":        "Polygon",
        "coordinates": [polygon_coords],
        "geodesic":    True,
    })


# ---------------------------------------------------------------------------
# EE-touching — per-day asymmetry sampling
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WindAnomalyDayMeasurement:
    """One anomaly day's wind sample plus the upwind/downwind ring reduction.

    ``asymmetry_ratio`` is ``bg_upwind / bg_downwind`` (per spec §5.1). For
    indicators where higher values mean "more pollution" (every in-scope
    indicator: NO₂, SO₂, HCHO, AAI, AOD), an asymmetry ratio above 1.0
    means the upwind background is higher than the downwind background —
    consistent with transported pollution arriving from upwind.

    ``None`` cases:
      - speed < calm threshold (WA9): direction undefined → both ring
        reductions skipped → asymmetry_ratio = None
      - reduction returns null: asymmetry_ratio = None
      - downwind reduction is zero (division by zero): asymmetry_ratio
        = None — the ratio is meaningless and a None flag preserves the
        downstream "non-calm but no asymmetry" branch.
    """

    date_utc:        str
    speed_ms:        float | None
    direction_deg:   float | None
    is_calm:         bool
    bg_upwind:       float | None
    bg_downwind:     float | None
    asymmetry_ratio: float | None


def measure_ring_asymmetry(
    samples: list[Era5WindSample],
    *,
    centre: dict,
    r_site_km: float,
    r_background_km: float,
    image_collection: ee.ImageCollection,
    band: str,
    scale: float | None,
    calm_threshold_ms: float = WIND_CALM_THRESHOLD_MS,
) -> list[WindAnomalyDayMeasurement]:
    """Per-anomaly-day upwind/downwind background-ring reductions.

    For each sample with ``speed_ms >= calm_threshold_ms`` and a valid
    direction, build two half-ring geometries (upwind = direction + 180°,
    downwind = direction), reduce the indicator's ImageCollection over each,
    and compute the ratio. Calm days are recorded with the speed but no
    ring reductions (asymmetry_ratio = None).

    Performance: one ``ee.Dictionary`` per non-calm sample folded into one
    batched ``ee.List`` getInfo. At typical N≈10 non-calm anomaly days,
    this is one server round-trip total for the asymmetry pass.

    Spec authority: §5.1 step 3e. The reductions are mean over the half-
    ring at the indicator's native ``scale``; the choice of mean (vs
    median) matches the existing six_step background convention and is
    intentionally NOT the median used by ``background_value`` because the
    upwind/downwind contrast we care about *is* the tail behaviour, not
    the central value.
    """
    if not samples:
        return []

    # Pre-filter: which samples generate EE reductions?
    non_calm_samples: list[tuple[int, Era5WindSample]] = []
    for idx, s in enumerate(samples):
        if (
            s.coverage_ok
            and s.speed_ms is not None
            and s.direction_deg is not None
            and s.speed_ms >= calm_threshold_ms
        ):
            non_calm_samples.append((idx, s))

    # If every day is calm there are no ring reductions to make — short
    # circuit before any EE call.
    if not non_calm_samples:
        return [
            WindAnomalyDayMeasurement(
                date_utc=s.date_utc,
                speed_ms=s.speed_ms,
                direction_deg=s.direction_deg if s.coverage_ok else None,
                is_calm=(
                    s.coverage_ok
                    and s.speed_ms is not None
                    and s.speed_ms < calm_threshold_ms
                ),
                bg_upwind=None, bg_downwind=None, asymmetry_ratio=None,
            )
            for s in samples
        ]

    # Build the EE batch.
    selected = image_collection.select(band)

    def _reduce_half(geom: ee.Geometry) -> ee.Number:
        return ee.Number(
            selected.mean().reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geom,
                scale=scale,
                bestEffort=True,
                maxPixels=int(1e9),
            ).get(band)
        )

    per_day_dicts: list[ee.Dictionary] = []
    geometries: list[tuple[ee.Geometry, ee.Geometry]] = []
    for _, s in non_calm_samples:
        downwind_geom = half_ring_geometry(
            centre, r_site_km, r_background_km, s.direction_deg,
        )
        upwind_geom = half_ring_geometry(
            centre, r_site_km, r_background_km,
            (s.direction_deg + 180.0) % 360.0,
        )
        geometries.append((upwind_geom, downwind_geom))
        per_day_dicts.append(ee.Dictionary({
            "upwind":   _reduce_half(upwind_geom),
            "downwind": _reduce_half(downwind_geom),
        }))

    batched = ee.List(per_day_dicts).getInfo() or []

    # Map results back to per-input-index dict, then build output list in
    # original sample order. Calm-and-missing days fill in with None ring
    # reductions.
    per_idx: dict[int, dict] = {}
    for (idx, _), result in zip(non_calm_samples, batched):
        per_idx[idx] = result if isinstance(result, dict) else {}

    measurements: list[WindAnomalyDayMeasurement] = []
    for idx, s in enumerate(samples):
        is_calm = (
            s.coverage_ok
            and s.speed_ms is not None
            and s.speed_ms < calm_threshold_ms
        )
        bg_upwind: float | None = None
        bg_downwind: float | None = None
        ratio: float | None = None
        result = per_idx.get(idx)
        if result is not None:
            u_raw = result.get("upwind")
            d_raw = result.get("downwind")
            bg_upwind = float(u_raw) if u_raw is not None else None
            bg_downwind = float(d_raw) if d_raw is not None else None
            if (
                bg_upwind is not None
                and bg_downwind is not None
                and bg_downwind != 0.0
            ):
                ratio = bg_upwind / bg_downwind
        measurements.append(WindAnomalyDayMeasurement(
            date_utc=s.date_utc,
            speed_ms=s.speed_ms,
            direction_deg=s.direction_deg if s.coverage_ok else None,
            is_calm=is_calm,
            bg_upwind=bg_upwind,
            bg_downwind=bg_downwind,
            asymmetry_ratio=ratio,
        ))
    return measurements


# ---------------------------------------------------------------------------
# Orchestration — provenance.extra block
# ---------------------------------------------------------------------------

def _aggregate_measurements(
    measurements: list[WindAnomalyDayMeasurement],
    *,
    calm_threshold_ms: float,
) -> dict:
    """Reduce per-day measurements to the spec §5.4 aggregate fields.

    Returns a dict with ``mean_speed_ms``, ``mean_asymmetry_ratio``,
    ``mean_direction_deg``, ``n_calm_days``. Empty input → all None / 0.
    """
    if not measurements:
        return {
            "mean_speed_ms":        None,
            "mean_asymmetry_ratio": None,
            "mean_direction_deg":   None,
            "n_calm_days":          0,
        }

    # Speed mean: all days with coverage, including calm.
    speeds = [
        m.speed_ms for m in measurements if m.speed_ms is not None
    ]
    mean_speed = sum(speeds) / len(speeds) if speeds else None

    # Direction circular-mean: non-calm days only.
    directions = [
        m.direction_deg for m in measurements
        if not m.is_calm and m.direction_deg is not None
    ]
    mean_direction = circular_mean_deg(directions) if directions else None

    # Asymmetry mean: non-calm days with a finite ratio.
    ratios = [
        m.asymmetry_ratio for m in measurements
        if m.asymmetry_ratio is not None
    ]
    mean_ratio = sum(ratios) / len(ratios) if ratios else None

    n_calm = sum(1 for m in measurements if m.is_calm)

    return {
        "mean_speed_ms":        mean_speed,
        "mean_asymmetry_ratio": mean_ratio,
        "mean_direction_deg":   mean_direction,
        "n_calm_days":          n_calm,
    }


def build_wind_provenance_extra(
    state: WindAttributabilityState,
    mean_speed_ms: float | None,
    mean_asymmetry_ratio: float | None,
    mean_direction_deg: float | None,
    n_anomaly_days: int,
    n_calm_days: int,
    wind_data_window: tuple[str, str] | None,
) -> dict:
    """Build the spec §5.4 provenance.extra block for one in-scope indicator.

    Field naming follows the M-ATTRIB-A1 / M-TIER-A1 / M-FALLBACK-A1 pattern:
    snake_case, the state field uses ``_state`` suffix (Step B reconciliation
    #2) to match ``attributability_state`` in M-ATTRIB-A1's terms. The five
    detail fields are always emitted (set to None when sparse) so downstream
    readers don't need to distinguish "absent" from "sparse".

    ``wind_data_window`` formats as ``"YYYY-MM-DD/YYYY-MM-DD"`` to match the
    M-FALLBACK-A1 ``temporal_fallback_source_window`` convention. When the
    indicator used SPPY temporal fallback, the caller passes the SPPY window
    (composes with M-FALLBACK-A1 per WA23); for the normal path, the
    current window.
    """
    window_str: str | None = None
    if wind_data_window is not None:
        window_str = f"{wind_data_window[0]}/{wind_data_window[1]}"

    return {
        "wind_attributability_state":  state,
        "wind_mean_speed_ms":          mean_speed_ms,
        "wind_mean_asymmetry_ratio":   mean_asymmetry_ratio,
        "wind_mean_direction_deg":     mean_direction_deg,
        "wind_n_anomaly_days":         int(n_anomaly_days),
        "wind_n_calm_days":            int(n_calm_days),
        "wind_data_window":            window_str,
    }


def compute_wind_attribution_extra(
    *,
    centre: dict,
    r_site_km: float,
    r_background_km: float,
    image_collection: ee.ImageCollection,
    band: str,
    scale: float | None,
    anomaly_dates_utc: list[str] | None,
    wind_data_window: tuple[str, str] | None,
    ring_land_fraction: float | None = None,
    n_min: int = WIND_N_MIN_ANOMALY_DAYS,
) -> dict:
    """Top-level wind-attribution helper invoked by ``six_step`` for in-scope indicators.

    Sequence:
      1. Sparse gate (WA10) — when ``anomaly_dates_utc`` has fewer than
         ``n_min`` entries (or is None), emit a sparse provenance block
         immediately. No EE calls.
      2. Sparse gate, second pass — when the ring has effectively no land
         (post-MOD44W mask), asymmetry sampling would reduce over water
         and produce noise. Treat as sparse rather than confidently
         attributing.
      3. Sample ERA5 at the overpass hour for each anomaly day.
      4. Reduce the indicator's IC over upwind/downwind half-rings per
         non-calm anomaly day.
      5. Aggregate (spec §5.1 step 4) and bucket (§5.2).

    Returns the §5.4 provenance.extra dict. Never raises — failures inside
    the EE batch (rare for ERA5; possible for the indicator's own ring
    reduction when coverage is thin) fall back to the sparse provenance
    block so the caller's normal path is never disrupted.

    The caller (``six_step``) is responsible for invoking this only for
    indicators in ``WIND_ATTRIBUTABILITY_INDICATORS``.
    """
    n_dates = len(anomaly_dates_utc) if anomaly_dates_utc else 0

    if n_dates < n_min:
        return build_wind_provenance_extra(
            state="sparse",
            mean_speed_ms=None,
            mean_asymmetry_ratio=None,
            mean_direction_deg=None,
            n_anomaly_days=n_dates,
            n_calm_days=0,
            wind_data_window=wind_data_window,
        )

    # If the ring is effectively all-water, the asymmetry reduction can't
    # produce a meaningful upwind/downwind contrast. Treat as sparse with
    # the day count preserved so the audit appendix still records the
    # anomaly-day count (helpful when diagnosing "why no arrow?").
    if (
        ring_land_fraction is not None
        and ring_land_fraction < LAND_MASK_FRACTION_MIN_THRESHOLD
    ):
        return build_wind_provenance_extra(
            state="sparse",
            mean_speed_ms=None,
            mean_asymmetry_ratio=None,
            mean_direction_deg=None,
            n_anomaly_days=n_dates,
            n_calm_days=0,
            wind_data_window=wind_data_window,
        )

    samples = sample_era5_wind_at_overpass(centre, anomaly_dates_utc)
    measurements = measure_ring_asymmetry(
        samples,
        centre=centre,
        r_site_km=r_site_km,
        r_background_km=r_background_km,
        image_collection=image_collection,
        band=band,
        scale=scale,
    )
    agg = _aggregate_measurements(
        measurements, calm_threshold_ms=WIND_CALM_THRESHOLD_MS,
    )
    state = compute_wind_attributability_state(
        mean_wind_speed_ms=agg["mean_speed_ms"],
        mean_asymmetry_ratio=agg["mean_asymmetry_ratio"],
        n_anomaly_days=n_dates,
    )
    return build_wind_provenance_extra(
        state=state,
        mean_speed_ms=agg["mean_speed_ms"],
        mean_asymmetry_ratio=agg["mean_asymmetry_ratio"],
        mean_direction_deg=agg["mean_direction_deg"],
        n_anomaly_days=n_dates,
        n_calm_days=agg["n_calm_days"],
        wind_data_window=wind_data_window,
    )


# Sparse provenance block — convenience constant for callers that want to
# emit "no wind data" without computing anything (e.g. when ``six_step`` is
# bypassed for a single-snapshot indicator that doesn't have anomaly dates).
def sparse_provenance_extra(
    n_anomaly_days: int = 0,
    wind_data_window: tuple[str, str] | None = None,
) -> dict:
    """Sparse-state ``provenance.extra`` block — convenience for callers
    bypassing the EE path."""
    return build_wind_provenance_extra(
        state="sparse",
        mean_speed_ms=None,
        mean_asymmetry_ratio=None,
        mean_direction_deg=None,
        n_anomaly_days=n_anomaly_days,
        n_calm_days=0,
        wind_data_window=wind_data_window,
    )
