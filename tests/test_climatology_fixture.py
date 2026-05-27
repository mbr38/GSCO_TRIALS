"""Climatology fixture integrity + loader + lookup tests (M-FALLBACK-A1 §7.5).

Pins:
- the committed `demo/climatology.json` structure, vintage, and value sanity
  (finite, non-negative where applicable, all 11 in-scope indicators);
- the loader cache behaviour;
- the baseline accessor's strict-None on missing data;
- the centroid→country lookup's graceful degradation to None.

No Earth Engine: the country lookup is exercised with a fake `ee` module
injected into `sys.modules`.
"""

from __future__ import annotations

import math
import sys
import types

import pytest

from engine.constants import CLIMATOLOGY_INDICATORS
from engine.core import climatology as cl


# ---------------------------------------------------------------------------
# §7.5 — fixture integrity
# ---------------------------------------------------------------------------

class TestFixtureIntegrity:
    @pytest.fixture(autouse=True)
    def _fresh_cache(self):
        cl.clear_cache()
        yield
        cl.clear_cache()

    def test_fixture_loads_and_has_meta(self) -> None:
        fx = cl.load_climatology()
        assert "_meta" in fx and "countries" in fx
        assert fx["_meta"]["vintage"]  # non-empty vintage string

    def test_vintage_is_stamped(self) -> None:
        assert cl.fixture_vintage() == cl.load_climatology()["_meta"]["vintage"]

    def test_meta_lists_the_eleven_in_scope_indicators(self) -> None:
        listed = set(cl.load_climatology()["_meta"]["indicators"])
        assert listed == set(CLIMATOLOGY_INDICATORS)

    def test_demo_relevant_countries_present(self) -> None:
        # Sapezal/Brasilia/Rio → Brazil; Mumbai → India (§7.2 regression set).
        countries = cl.load_climatology()["countries"]
        assert "Brazil" in countries
        assert "India" in countries

    def test_every_country_has_all_indicators_with_sane_values(self) -> None:
        countries = cl.load_climatology()["countries"]
        assert countries, "fixture must ship at least one country"
        for name, entry in countries.items():
            for ind in CLIMATOLOGY_INDICATORS:
                assert ind in entry, f"{name} missing {ind}"
                median = entry[ind]["median"]
                std = entry[ind]["std"]
                assert math.isfinite(median), f"{name}/{ind} median not finite"
                assert math.isfinite(std), f"{name}/{ind} std not finite"
                assert std >= 0.0, f"{name}/{ind} std negative"
                # Non-negative where applicable — AAI is a signed index, so
                # it's exempt (§7.5 "where applicable").
                if ind != "air.aai":
                    assert median >= 0.0, f"{name}/{ind} median negative"


# ---------------------------------------------------------------------------
# Loader cache
# ---------------------------------------------------------------------------

class TestLoaderCache:
    def test_cache_returns_same_object(self) -> None:
        cl.clear_cache()
        a = cl.load_climatology()
        b = cl.load_climatology()
        assert a is b  # cached, not re-read
        cl.clear_cache()

    def test_explicit_path_bypasses_cache(self, tmp_path) -> None:
        import json

        p = tmp_path / "clim.json"
        p.write_text(json.dumps({
            "_meta": {"vintage": "2099"},
            "countries": {"Testland": {"air.no2": {"median": 1.0, "std": 0.5}}},
        }))
        fx = cl.load_climatology(path=p)
        assert fx["_meta"]["vintage"] == "2099"
        # The default cache is untouched by an explicit-path read.
        cl.clear_cache()
        assert cl.load_climatology()["_meta"]["vintage"] != "2099"
        cl.clear_cache()


# ---------------------------------------------------------------------------
# Baseline accessor (strict-None)
# ---------------------------------------------------------------------------

class TestBaselineAccessor:
    _FIXTURE = {
        "_meta": {"vintage": "2026"},
        "countries": {
            "Brazil": {
                "air.no2": {"median": 38.0, "std": 26.0},
                "air.so2": {"median": 75.0},  # missing std → None
            },
        },
    }

    def test_known_country_indicator_returns_baseline(self) -> None:
        b = cl.climatology_baseline("Brazil", "air.no2", fixture=self._FIXTURE)
        assert b is not None
        assert b.median == 38.0 and b.std == 26.0 and b.vintage == "2026"

    def test_unknown_country_returns_none(self) -> None:
        assert cl.climatology_baseline("Atlantis", "air.no2", fixture=self._FIXTURE) is None

    def test_unknown_indicator_returns_none(self) -> None:
        assert cl.climatology_baseline("Brazil", "air.aod", fixture=self._FIXTURE) is None

    def test_missing_statistic_returns_none(self) -> None:
        assert cl.climatology_baseline("Brazil", "air.so2", fixture=self._FIXTURE) is None

    def test_none_country_returns_none(self) -> None:
        assert cl.climatology_baseline(None, "air.no2", fixture=self._FIXTURE) is None


# ---------------------------------------------------------------------------
# Centroid → country lookup (graceful degradation)
# ---------------------------------------------------------------------------

def _fake_ee(names):
    """Build a fake `ee` module whose point-in-polygon returns `names`."""
    mod = types.ModuleType("ee")

    class _FC:
        def filterBounds(self, _pt):
            return self

        def aggregate_array(self, _field):
            class _Arr:
                def getInfo(_self):
                    return names
            return _Arr()

    mod.Geometry = types.SimpleNamespace(Point=lambda coords: object())
    mod.FeatureCollection = lambda _asset: _FC()
    return mod


class TestCountryLookup:
    @pytest.fixture(autouse=True)
    def _fresh(self):
        cl.clear_country_cache()
        yield
        cl.clear_country_cache()

    def test_resolves_country_name(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "ee", _fake_ee(["Brazil"]))
        assert cl.country_for_centroid(-13.5, -58.8) == "Brazil"

    def test_caches_repeat_lookups(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "ee", _fake_ee(["India"]))
        first = cl.country_for_centroid(19.07, 72.87)
        # Swap the fake to a different answer; cache should still return India.
        monkeypatch.setitem(sys.modules, "ee", _fake_ee(["Nowhere"]))
        assert cl.country_for_centroid(19.07, 72.87) == first == "India"

    def test_point_outside_all_polygons_returns_none(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "ee", _fake_ee([]))  # open ocean
        assert cl.country_for_centroid(0.0, -30.0) is None

    def test_ee_failure_degrades_to_none(self, monkeypatch) -> None:
        broken = types.ModuleType("ee")

        def _boom(_asset):
            raise RuntimeError("EE not initialized")

        broken.Geometry = types.SimpleNamespace(Point=lambda coords: object())
        broken.FeatureCollection = _boom
        monkeypatch.setitem(sys.modules, "ee", broken)
        assert cl.country_for_centroid(-15.8, -47.9) is None
