"""GAUL level1 region wrapper (M-DEMO-DATA).

Wraps the FAO/GAUL/2015/level1 Earth Engine asset. Exposes:

- ``all_countries()`` — sorted list of country names available.
- ``regions_for_country(country)`` — sorted list of admin1 regions
  for one country, each with centroid + a representative buffer
  radius derived from polygon area.

Lazy per-country cache: the first call per country fires one EE
round-trip; subsequent calls are instant. ``clear_cache()`` is exposed
for tests.

**Radius rule** (locked M-DEMO-DATA): ``radius = min(√(area/π), 400 km)``.
The square-root term gives a circle whose area equals the polygon's
area — a "representative buffer". The 400 km cap keeps absurd cases
(Sakha, Greenland, Amazonas) bounded to something a screening tool can
actually use. ``Region.is_capped`` lets the UI render a tooltip ("region
is larger than the representative buffer") when the cap kicks in.
"""

# M-DEMO-DATA
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import ee


_GAUL_LEVEL1_ASSET: Final[str]   = "FAO/GAUL/2015/level1"
_RADIUS_CAP_KM:     Final[float] = 400.0

# M-DEMO-DATA polish: smallest screening-meaningful radius. Matches
# P-04's smallest MNC radius stop (5 km); regions whose natural radius
# is below this aren't useful as screening AOIs. Combined with the
# missing-name filter, drops GAUL's offshore-island / disputed-territory
# entries (which carry null ADM1_NAME and/or sub-5 km natural radii).
_MIN_REGION_RADIUS_KM: Final[float] = 5.0


@dataclass(frozen=True)
class Region:
    """One administrative unit (admin1)."""

    name:              str
    country:           str
    centroid_lat:      float
    centroid_lon:      float
    radius_km:         float   # √(area/π) capped at _RADIUS_CAP_KM
    natural_radius_km: float   # Uncapped — for the "is capped?" tooltip

    @property
    def is_capped(self) -> bool:
        """True when ``natural_radius_km`` exceeded the 400 km cap."""
        return self.natural_radius_km > _RADIUS_CAP_KM


# ---------------------------------------------------------------------------
# Module-level lazy cache
# ---------------------------------------------------------------------------

_country_cache:       dict[str, tuple[Region, ...]] = {}
_all_countries_cache: tuple[str, ...] | None        = None


# ---------------------------------------------------------------------------
# Pure-Python helpers (testable without EE)
# ---------------------------------------------------------------------------

def _radius_from_area_km2(area_km2: float) -> tuple[float, float]:
    """Compute ``(capped_radius_km, natural_radius_km)`` from a polygon area.

    The natural radius is ``√(area/π)`` — the radius of a circle whose
    area equals the polygon's. The capped value is bounded at
    ``_RADIUS_CAP_KM``. Returned as a 2-tuple so the caller can record
    both values on the ``Region`` and surface the cap state via
    ``Region.is_capped``.
    """
    natural = math.sqrt(area_km2 / math.pi)
    return (min(natural, _RADIUS_CAP_KM), natural)


def _build_region_or_none(
    country:      str,
    raw_name:     str | None,
    area_km2:     float,
    centroid_lat: float,
    centroid_lon: float,
) -> Region | None:
    """Build a ``Region`` from raw GAUL fields, or return ``None`` if
    the entry should be filtered out.

    M-DEMO-DATA polish: drops two classes of GAUL entries that surface
    as useless dropdown rows: missing ``ADM1_NAME`` (offshore islands,
    disputed territories) and natural radius below
    ``_MIN_REGION_RADIUS_KM`` (entries too small to be meaningful
    screening AOIs). Both are silent — callers see only the surviving
    regions; there's no "Name Unknown" leak.
    """
    if not raw_name or not str(raw_name).strip():
        return None
    capped, natural = _radius_from_area_km2(area_km2)
    if natural < _MIN_REGION_RADIUS_KM:
        return None
    return Region(
        name=str(raw_name),
        country=country,
        centroid_lat=centroid_lat,
        centroid_lon=centroid_lon,
        radius_km=round(capped, 1),
        natural_radius_km=round(natural, 1),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def all_countries() -> tuple[str, ...]:
    """Return the sorted list of country names in GAUL level1.

    Cached after first call. One EE round-trip on cold start.
    """
    global _all_countries_cache
    if _all_countries_cache is not None:
        return _all_countries_cache

    fc = ee.FeatureCollection(_GAUL_LEVEL1_ASSET)
    country_list = (
        fc.aggregate_array("ADM0_NAME")
          .distinct()
          .sort()
          .getInfo()
    )
    _all_countries_cache = tuple(country_list)
    return _all_countries_cache


def regions_for_country(country: str) -> tuple[Region, ...]:
    """Return all admin1 regions for ``country``, sorted by name.

    Each region carries centroid lat/lon and a representative buffer
    radius. Cached per country; first call per cold country fires one
    EE round-trip, subsequent calls are instant.
    """
    if country in _country_cache:
        return _country_cache[country]

    fc = (
        ee.FeatureCollection(_GAUL_LEVEL1_ASSET)
        .filter(ee.Filter.eq("ADM0_NAME", country))
    )

    # Server-side annotation: attach centroid coordinates + area_km² so
    # one ``getInfo()`` pulls everything we need for every region.
    def _annotate(feat):
        geom            = feat.geometry()
        centroid_coords = geom.centroid(maxError=100).coordinates()
        area_m2         = geom.area(maxError=100)
        return feat.set({
            "_centroid_lon": centroid_coords.get(0),
            "_centroid_lat": centroid_coords.get(1),
            "_area_km2":     area_m2.divide(1e6),
        })

    info = fc.map(_annotate).getInfo()

    # M-DEMO-DATA polish — silently drop unnamed / sub-threshold entries
    # via _build_region_or_none. The ADM1_CODE fallback for the name
    # field is gone: the filter guarantees the helper either returns a
    # Region with a real ADM1_NAME or returns None.
    regions: list[Region] = []
    for feature in info["features"]:
        props = feature["properties"]
        region = _build_region_or_none(
            country=country,
            raw_name=props.get("ADM1_NAME"),
            area_km2=props["_area_km2"],
            centroid_lat=float(props["_centroid_lat"]),
            centroid_lon=float(props["_centroid_lon"]),
        )
        if region is not None:
            regions.append(region)

    regions.sort(key=lambda r: r.name)
    _country_cache[country] = tuple(regions)
    return _country_cache[country]


def country_boundary_fc(country: str) -> "ee.FeatureCollection":
    """Styled GAUL-level1 ``FeatureCollection`` for ``country``.

    Outline only (no fill, 2 px blue stroke) — used by the P-02
    Regional-analysis preview to draw the country's administrative
    boundary under the per-region markers. Server-side; no ``getInfo``.
    """
    return (
        ee.FeatureCollection(_GAUL_LEVEL1_ASSET)
        .filter(ee.Filter.eq("ADM0_NAME", country))
        .style(color="2563eb", fillColor="00000000", width=2)
    )


def clear_cache() -> None:
    """Reset both caches. Exposed for tests."""
    global _all_countries_cache
    _all_countries_cache = None
    _country_cache.clear()
