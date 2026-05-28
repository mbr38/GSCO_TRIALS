"""ERA5 reanalysis fetch helpers — M-WIND-A1 v2.0 (28 May 2026).

Built as a shared module rather than indicator-specific code so the Tier C2
boundary-layer-height work can reuse the overpass-hour and per-day sampling
machinery. This module is intentionally narrow:

1. ``compute_overpass_utc_hour`` — pure date / longitude math, no EE.
2. ``sample_era5_wind_at_overpass`` — given a centre point, an ImageCollection,
   and a list of UTC dates, return per-date wind ``(speed_ms, direction_deg)``
   samples or a calm-flagged record.

Asset choice (``ECMWF/ERA5/HOURLY``) is locked in ``engine.constants`` and
referenced here only via the imported names. ``ECMWF/ERA5_LAND/HOURLY`` is
also valid for wind-only use but lacks ``boundary_layer_height`` for the
deferred Tier C2 work, so the shared helper standardises on the full ERA5
product (per docs/v1x_followups.md, 24 May 2026 correction).

Anchored to:
- M-WIND-A1 v2.0 spec §5.1 (overpass formula, per-day sampling, calm gate)
- WA8 (u_ref = 2 m/s) and WA9 (calm threshold = 1 m/s) — applied in
  ``engine.core.wind``, NOT here. This module returns raw u/v samples.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date as _date, timedelta as _td

import ee

from engine.constants import (
    ERA5_HOURLY_ASSET,
    ERA5_WIND_U_BAND,
    ERA5_WIND_V_BAND,
)


# ---------------------------------------------------------------------------
# Overpass hour  (spec §5.1)
# ---------------------------------------------------------------------------

# Sentinel-5P / MAIAC AOD nominal Equator-crossing local time: ~13:30.
# The wind sample should be taken at the overpass hour so the wind state
# coincides with the satellite observation that generated the anomaly.
_SATELLITE_LOCAL_OVERPASS_HOUR: float = 13.5


def compute_overpass_utc_hour(longitude_deg: float) -> int:
    """Return the UTC hour (0–23) closest to the local 13:30 satellite pass
    at ``longitude_deg``.

    Spec §5.1 formula::

        round((13.5 - longitude_deg / 15) % 24)

    Sanity-check spot values from the spec docstring:

        compute_overpass_utc_hour(   0.0) == 14   # Greenwich
        compute_overpass_utc_hour( -60.0) == 18   # Brasília
        compute_overpass_utc_hour(+120.0) ==  6   # Beijing

    Pure function — no EE, no I/O. Wind module multiplies it through to ERA5
    via a ``filter`` on the ``hour`` system property.
    """
    raw = (_SATELLITE_LOCAL_OVERPASS_HOUR - longitude_deg / 15.0) % 24.0
    return int(round(raw)) % 24


# ---------------------------------------------------------------------------
# Per-day sampling  (spec §5.1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Era5WindSample:
    """One day's overpass-hour wind sample at a fixed point.

    All fields populated when the ERA5 reduction yields finite u/v values.
    When the reduction returns null (extremely rare for ERA5; would mean the
    24-hour image stack for that day was empty or masked at the point), the
    sample is recorded with ``coverage_ok=False`` and the speed/direction
    fields are None. Downstream callers (``engine.core.wind``) treat those
    as excluded from the mean rather than failed.
    """

    date_utc:      str
    speed_ms:      float | None
    direction_deg: float | None
    coverage_ok:   bool


def _date_plus_one_day(iso: str) -> str:
    return (_date.fromisoformat(iso) + _td(days=1)).isoformat()


def _wind_speed_direction(u_ms: float, v_ms: float) -> tuple[float, float]:
    """Speed (m/s) and meteorological wind-to direction (degrees, 0=N, 90=E).

    ERA5's u/v are the east/north components of the wind velocity vector.
    The conventional meteorological "direction" we want for plotting is
    "where the wind is blowing toward" (matching the arrow we render on
    the map), so we use ``atan2(u, v)`` (note: u first, v second) which
    points away from the source. Mapped to [0, 360).
    """
    speed = math.sqrt(u_ms * u_ms + v_ms * v_ms)
    raw_deg = math.degrees(math.atan2(u_ms, v_ms))
    direction = (raw_deg + 360.0) % 360.0
    return speed, direction


def sample_era5_wind_at_overpass(
    centre: dict,
    anomaly_dates_utc: list[str],
    *,
    asset_id: str = ERA5_HOURLY_ASSET,
) -> list[Era5WindSample]:
    """Sample ERA5 10-m wind at the supplier point for each anomaly day.

    For each UTC date in ``anomaly_dates_utc``, filter the ERA5 hourly
    ImageCollection to that day's overpass UTC hour and reduce a single
    pixel at ``centre = {lat, lon}`` to ``(u, v)``. Returns one
    ``Era5WindSample`` per input date, in input order.

    Sampling strategy: one ``ee.Dictionary`` per date batched into a single
    ``ee.List``, then one ``getInfo`` for the whole batch. At ~60 anomaly
    days per typical 90-day window, this is one server round-trip total.

    Args:
        centre: ``{"lat", "lon"}`` supplier coordinates.
        anomaly_dates_utc: sorted ISO UTC dates (e.g. ``["2026-03-04", ...]``)
            from ``six_step``'s ``anomaly_dates_utc`` return field.
        asset_id: ERA5 hourly collection ID (overrideable for tests).

    Returns:
        List of ``Era5WindSample``, one per input date. Empty when the
        input list is empty (no EE call made).
    """
    if not anomaly_dates_utc:
        return []

    point = ee.Geometry.Point([centre["lon"], centre["lat"]])
    overpass_hour = compute_overpass_utc_hour(centre["lon"])

    collection = ee.ImageCollection(asset_id).select([
        ERA5_WIND_U_BAND, ERA5_WIND_V_BAND,
    ])

    def _per_date_reduction(date_iso: str):
        # Half-open one-day window then filter to the overpass hour. A
        # single ERA5 image typically exists per hour; ``.mean()`` is the
        # safe collapse if multiple images exist (e.g. ensemble members,
        # which ERA5/HOURLY doesn't carry but a future asset swap might).
        day_ic = (
            collection
            .filterDate(date_iso, _date_plus_one_day(date_iso))
            .filter(ee.Filter.calendarRange(overpass_hour, overpass_hour, "hour"))
        )
        img = day_ic.mean()
        return img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=point,
            scale=27_830.0,  # ERA5 native ~0.25° grid ≈ 27.83 km at equator
            bestEffort=True,
            maxPixels=int(1e6),
        )

    batched = ee.List([
        _per_date_reduction(d) for d in anomaly_dates_utc
    ]).getInfo() or []

    samples: list[Era5WindSample] = []
    for date_iso, raw in zip(anomaly_dates_utc, batched):
        # ``raw`` is the materialised dict; ERA5 returns null when the
        # point falls in a masked cell, which for ERA5 is extremely rare.
        if not isinstance(raw, dict):
            samples.append(Era5WindSample(date_iso, None, None, coverage_ok=False))
            continue
        u = raw.get(ERA5_WIND_U_BAND)
        v = raw.get(ERA5_WIND_V_BAND)
        if u is None or v is None:
            samples.append(Era5WindSample(date_iso, None, None, coverage_ok=False))
            continue
        speed, direction = _wind_speed_direction(float(u), float(v))
        samples.append(
            Era5WindSample(date_iso, speed, direction, coverage_ok=True)
        )
    return samples
