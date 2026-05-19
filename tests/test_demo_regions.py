"""Tests for demo.regions (M-DEMO-DATA).

Two sections:

1. **Pure-Python** — radius helper, ``Region.is_capped``, cache state
   machine. No EE round-trips; safe to run in CI.
2. **Real Earth Engine** — marked with ``@pytest.mark.skipif`` against
   ``RUN_EE_TESTS``, mirroring ``tests/test_ghg_integration.py``.
   These verify Brazil's 27 admin1 regions resolve, centroids/radii
   are sane, and ``all_countries()`` works against the live asset.
"""

# M-DEMO-DATA
from __future__ import annotations

import os

import pytest

from demo import regions as regions_mod
from demo.regions import (
    Region,
    _MIN_REGION_RADIUS_KM,
    _RADIUS_CAP_KM,
    _build_region_or_none,
    _radius_from_area_km2,
    all_countries,
    clear_cache,
    regions_for_country,
)


# ---------------------------------------------------------------------------
# Pure-Python — radius math
# ---------------------------------------------------------------------------

def test_small_polygon_radius_is_not_capped():
    """Area 1 000 km² ≈ 17.8 km natural radius → well under the cap."""
    capped, natural = _radius_from_area_km2(1_000.0)
    assert capped == natural
    assert 17.0 < natural < 18.5


def test_huge_polygon_radius_is_capped_at_400():
    """Area 800 000 km² ≈ 505 km natural radius → capped to 400."""
    capped, natural = _radius_from_area_km2(800_000.0)
    assert capped == _RADIUS_CAP_KM
    assert 500.0 < natural < 510.0


def test_radius_at_exact_cap_threshold_does_not_clip():
    """Area sized so √(area/π) == 400 exactly → no clip, natural == capped."""
    area_at_cap = (_RADIUS_CAP_KM ** 2) * 3.141_592_653_589_793
    capped, natural = _radius_from_area_km2(area_at_cap)
    assert capped == pytest.approx(natural)
    assert capped == pytest.approx(_RADIUS_CAP_KM)


# ---------------------------------------------------------------------------
# Pure-Python — Region.is_capped
# ---------------------------------------------------------------------------

def test_region_is_capped_true_when_natural_exceeds_cap():
    r = Region(
        name="Big",
        country="Test",
        centroid_lat=0.0, centroid_lon=0.0,
        radius_km=400.0, natural_radius_km=505.0,
    )
    assert r.is_capped is True


def test_region_is_capped_false_when_natural_under_cap():
    r = Region(
        name="Small",
        country="Test",
        centroid_lat=0.0, centroid_lon=0.0,
        radius_km=50.0, natural_radius_km=50.0,
    )
    assert r.is_capped is False


# ---------------------------------------------------------------------------
# Pure-Python — cache state machine (no EE)
# ---------------------------------------------------------------------------

def test_regions_cache_short_circuits_when_country_already_cached():
    """Once a country sits in ``_country_cache``, ``regions_for_country``
    returns the cached tuple without hitting EE. Pre-populate the cache
    with a sentinel and verify the function returns *that exact object*
    — proves the early-return branch fired.
    """
    clear_cache()
    sentinel = (
        Region(
            name="Sentinel",
            country="Brazil",
            centroid_lat=-15.0, centroid_lon=-50.0,
            radius_km=100.0, natural_radius_km=100.0,
        ),
    )
    regions_mod._country_cache["Brazil"] = sentinel

    result = regions_for_country("Brazil")
    assert result is sentinel  # Identity, not equality — cache hit only.


def test_all_countries_cache_short_circuits_when_already_cached():
    clear_cache()
    sentinel = ("CountryA", "CountryB")
    regions_mod._all_countries_cache = sentinel

    result = all_countries()
    assert result is sentinel


def test_clear_cache_resets_both_caches():
    clear_cache()
    regions_mod._country_cache["X"] = ()
    regions_mod._all_countries_cache = ("X",)

    clear_cache()

    assert regions_mod._country_cache == {}
    assert regions_mod._all_countries_cache is None


# ---------------------------------------------------------------------------
# M-DEMO-DATA polish — _build_region_or_none filter
# ---------------------------------------------------------------------------
# GAUL 2015 includes offshore-island and disputed-territory entries
# with null ADM1_NAME and/or sub-5 km natural radii. The filter drops
# both classes silently — callers only see screenable regions.

def test_named_and_large_region_is_built():
    """Happy path — proper name + decent area → typed Region."""
    region = _build_region_or_none(
        country="Brazil",
        raw_name="São Paulo",
        area_km2=250_000.0,   # ≈ 282 km natural radius — well above threshold.
        centroid_lat=-22.0,
        centroid_lon=-49.0,
    )
    assert region is not None
    assert region.name == "São Paulo"
    assert region.natural_radius_km > _MIN_REGION_RADIUS_KM


def test_named_but_tiny_region_is_dropped():
    """Real-name entry that's too small to be a meaningful screening AOI."""
    # Area ≈ 50 km² → natural radius ≈ 4 km, below the 5 km threshold.
    region = _build_region_or_none(
        country="Brazil",
        raw_name="Ilhabela",
        area_km2=50.0,
        centroid_lat=-23.78,
        centroid_lon=-45.36,
    )
    assert region is None


def test_unnamed_large_region_is_dropped():
    """Null name → drop, even when the polygon is big enough to screen."""
    region = _build_region_or_none(
        country="Brazil",
        raw_name=None,
        area_km2=10_000.0,
        centroid_lat=-3.85,
        centroid_lon=-32.42,
    )
    assert region is None


def test_unnamed_tiny_region_is_dropped():
    """Both filter conditions fire — single drop is enough."""
    region = _build_region_or_none(
        country="Brazil",
        raw_name=None,
        area_km2=10.0,
        centroid_lat=-20.50,
        centroid_lon=-29.32,
    )
    assert region is None


def test_whitespace_only_name_is_dropped():
    """``"   "`` shouldn't slip past the name check."""
    region = _build_region_or_none(
        country="Brazil",
        raw_name="   ",
        area_km2=250_000.0,
        centroid_lat=-22.0,
        centroid_lon=-49.0,
    )
    assert region is None


# ---------------------------------------------------------------------------
# Real Earth Engine — gated by RUN_EE_TESTS
# ---------------------------------------------------------------------------

_requires_ee = pytest.mark.skipif(
    os.environ.get("RUN_EE_TESTS") != "1",
    reason="set RUN_EE_TESTS=1 (and EE_PROJECT_ID) to run real-EE tests",
)


@pytest.fixture(scope="module")
def _initialised_ee():
    """Initialise Earth Engine once per module run."""
    import ee
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        pytest.skip("EE_PROJECT_ID not set")
    ee.Initialize(project=project)
    clear_cache()


@_requires_ee
def test_all_countries_includes_brazil(_initialised_ee):
    countries = all_countries()
    assert "Brazil" in countries


@_requires_ee
def test_regions_for_brazil_has_at_least_twenty_six(_initialised_ee):
    """GAUL level1 lists 27 Brazilian admin1 units. Allow ≥26 for slack
    against minor asset revisions."""
    clear_cache()
    regions = regions_for_country("Brazil")
    assert len(regions) >= 26


@_requires_ee
def test_brazilian_regions_have_sensible_field_ranges(_initialised_ee):
    """Every Brazilian region: lat ∈ [-35, 5], lon ∈ [-75, -30],
    radius > 0. Conservatively wide bounding box around Brazil."""
    clear_cache()
    for r in regions_for_country("Brazil"):
        assert -35.0 <= r.centroid_lat <= 5.0,  r.name
        assert -75.0 <= r.centroid_lon <= -30.0, r.name
        assert r.radius_km > 0,                  r.name


@_requires_ee
def test_brazil_sao_paulo_region_centroid_is_near_expected(_initialised_ee):
    """GAUL's São Paulo state centroid should land near (-22, -49). Allow
    ±3° to absorb polygon-shape quirks."""
    clear_cache()
    regions = {r.name: r for r in regions_for_country("Brazil")}
    sp = regions.get("São Paulo") or regions.get("Sao Paulo")
    assert sp is not None, list(regions.keys())[:5]
    assert -25.0 <= sp.centroid_lat <= -19.0
    assert -52.0 <= sp.centroid_lon <= -46.0
