"""Tests for M-OCEAN-RING — background-ring-over-water silent skip.

Three layers exercised:

1. ``engine.core.repeatable_core.background_value`` raises the new
   ``BackgroundRingNoDataError`` subclass when the EE reduction returns
   None for median or stdDev.
2. ``engine.air.run_pillar`` and ``engine.ghg.run_pillar`` route that
   specific exception into the canonical "indicator skipped" payload
   (None-valued measurements + provenance with
   ``skipped_reason='background_ring_no_data'``), and do *not* add an
   entry to ``_failures``.
3. The C9 / C4b prose dicts carry the user-facing translation in
   lockstep.
"""

# M-OCEAN-RING
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from engine.exceptions import (
    BackgroundRingNoDataError,
    IndicatorComputeError,
)
from ui.components.c4b_kpi_grid import _SKIPPED_REASON_TRANSLATIONS
from ui.components.c9_partial_banner import _SKIPPED_REASON_PROSE


# ---------------------------------------------------------------------------
# 1. Exception hierarchy — BackgroundRingNoDataError IS an
#    IndicatorComputeError so existing catches still work.
# ---------------------------------------------------------------------------

def test_background_ring_error_subclasses_indicator_compute_error():
    """Existing ``except IndicatorComputeError`` blocks must still trip
    on the new subclass — otherwise we'd lose all the per-indicator
    failure paths that other call sites rely on.
    """
    err = BackgroundRingNoDataError(indicator_id="air.no2", reason="x")
    assert isinstance(err, IndicatorComputeError)
    assert err.indicator_id == "air.no2"
    assert err.reason == "x"


# ---------------------------------------------------------------------------
# 2. background_value raises BackgroundRingNoDataError on empty reduction
# ---------------------------------------------------------------------------

class TestBackgroundValueRaisesNewError:
    def _stub_ee_and_chain(self, monkeypatch, get_info_returns) -> MagicMock:
        """Wire up a chainable mock for the EE side of ``background_value``.

        Stubs ``ee.Reducer.median`` / ``ee.Reducer.stdDev`` (static calls
        that ``background_value`` makes before any user-passed object is
        touched) and returns a chainable mock to pass as
        ``image_collection``. Its ``reduceRegion(...).getInfo()`` returns
        ``get_info_returns``.
        """
        from engine.core import repeatable_core

        chain = MagicMock()
        chain.select.return_value       = chain
        chain.mean.return_value         = chain
        chain.reduceRegion.return_value = chain
        chain.getInfo.return_value      = get_info_returns
        size_chain = MagicMock()
        size_chain.getInfo.return_value = 12
        chain.size.return_value = size_chain

        # ee.Reducer.median().combine(ee.Reducer.stdDev(), ...) is called
        # statically inside background_value before the user-passed chain
        # is touched. Stubbing the whole Reducer namespace gives every
        # method a callable that returns another mock with .combine.
        monkeypatch.setattr(repeatable_core.ee, "Reducer", MagicMock())
        # M-TIER-A3 Step B — background_ring now returns a dict carrying
        # the land mask + geometric land_fraction; downstream code extracts
        # `["geometry"]`. The sentinel here only needs to be subscriptable
        # with that key — the geometry value is opaque to background_value.
        monkeypatch.setattr(
            repeatable_core,
            "background_ring",
            lambda *_a, **_kw: {
                "geometry": object(),
                "mask": None,
                "land_fraction": 1.0,
                "land_mask_applied": True,
                "land_mask_asset": "MODIS/006/MOD44W",
            },
        )
        return chain

    def test_empty_reduction_raises_background_ring_no_data(self, monkeypatch):
        """Stub the EE chain so reduceRegion().getInfo() returns
        ``{}`` (no median / stdDev keys). ``background_value`` should
        raise ``BackgroundRingNoDataError``, NOT plain
        ``IndicatorComputeError`` (so pillar dispatchers can route it
        through the silent-skip path).
        """
        from engine.core import repeatable_core

        chain = self._stub_ee_and_chain(monkeypatch, get_info_returns={})

        aoi = {"centre": {"lat": -22.0, "lon": -43.0}, "radius_km": 281}

        with pytest.raises(BackgroundRingNoDataError) as excinfo:
            repeatable_core.background_value(
                aoi=aoi, image_collection=chain, band="NO2",
                seasonal=False, scale=1000.0,
            )

        # Reason string carries actionable detail.
        assert "background ring" in excinfo.value.reason
        assert "over water" in excinfo.value.reason

    def test_median_present_but_std_missing_still_raises(self, monkeypatch):
        """Edge case: the ring is small enough that median fills but
        stdDev doesn't (e.g. a single-pixel ring). Same skip path.
        """
        from engine.core import repeatable_core

        chain = self._stub_ee_and_chain(
            monkeypatch, get_info_returns={"NO2_median": 1e-5},  # no stdDev.
        )

        aoi = {"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 281}
        with pytest.raises(BackgroundRingNoDataError):
            repeatable_core.background_value(
                aoi=aoi, image_collection=chain, band="NO2",
                seasonal=False, scale=1000.0,
            )


# ---------------------------------------------------------------------------
# 3. engine.air._emit_skipped_air_result — canonical shape
# ---------------------------------------------------------------------------

class TestEmitSkippedAirResult:
    def test_emits_none_for_every_measurement(self):
        from engine.air import _MEASUREMENT_KEYS, _emit_skipped_air_result

        result = _emit_skipped_air_result(
            "no2",
            time_range=("2026-02-19", "2026-05-20"),
            skipped_reason="background_ring_no_data",
            reason_detail="background ring has no valid pixels",
        )
        for m in _MEASUREMENT_KEYS:
            assert result[f"air.no2.{m}"] is None

    def test_provenance_carries_skipped_reason(self):
        from engine.air import _emit_skipped_air_result

        result = _emit_skipped_air_result(
            "no2",
            time_range=("2026-02-19", "2026-05-20"),
            skipped_reason="background_ring_no_data",
            reason_detail="ring lands over water",
        )
        prov = result["_provenance.air.no2"]
        assert prov["skipped_reason"] == "background_ring_no_data"
        assert prov["observations"] == {"count": 0, "unit": "daily_images"}
        # The detail flows into the method_note for audit visibility.
        assert "ring lands over water" in prov["method_note"]


# ---------------------------------------------------------------------------
# 4. engine.ghg._emit_skipped_ghg_result — canonical shape
# ---------------------------------------------------------------------------

class TestEmitSkippedGhgResult:
    def test_emits_none_only_for_emitted_measurements(self):
        """GHG indicators carry different measurement sets per config
        (CO₂ ≠ CH₄ ≠ VIIRS); the skip helper must respect that."""
        from engine.ghg import GHG_INDICATOR_CONFIG, _emit_skipped_ghg_result

        result = _emit_skipped_ghg_result(
            "ch4",
            time_range=("2026-02-19", "2026-05-20"),
            skipped_reason="background_ring_no_data",
            reason_detail="ring over water",
        )
        for m in GHG_INDICATOR_CONFIG["ch4"].emitted_measurements:
            assert result[f"ghg.ch4.{m}"] is None
        prov = result["_provenance.ghg.ch4"]
        assert prov["skipped_reason"] == "background_ring_no_data"


# ---------------------------------------------------------------------------
# 5. engine.air.run_pillar routes the new error into silent-skip
# ---------------------------------------------------------------------------

class TestAirRunPillarRoutesSkip:
    def test_ring_failure_skips_instead_of_failing(self, monkeypatch):
        """Patch ``compute_pollutant_snapshot`` to raise the new error
        for every selected pollutant. ``run_pillar`` must NOT bubble it
        up as a PillarComputeError; it must emit the skipped payload
        and leave ``_failures`` empty for those entries.
        """
        from engine import air

        def fake_snapshot(aoi, pollutant, time_range, mode, ee_client, fallback=None):
            raise BackgroundRingNoDataError(
                indicator_id=f"air.{pollutant}",
                reason="background ring has no valid pixels — over water",
            )

        monkeypatch.setattr(air, "compute_pollutant_snapshot", fake_snapshot)

        aoi = {"centre": {"lat": -22.0, "lon": -43.0}, "radius_km": 281}
        selected = {"air.no2.score", "air.so2.score"}
        result = air.run_pillar(
            aoi=aoi,
            time_range=("2026-02-19", "2026-05-20"),
            mode="screening",
            selected_indicators=selected,
            ee_client=None,
        )

        # No _failures entries — silent skip.
        assert "_failures" not in result
        # Both pollutants got the canonical skipped shape.
        for pol in ("no2", "so2"):
            assert result[f"air.{pol}.score"] is None
            prov = result[f"_provenance.air.{pol}"]
            assert prov["skipped_reason"] == "background_ring_no_data"

    def test_non_ring_indicator_compute_error_still_routes_to_failures(
        self, monkeypatch,
    ):
        """Regression — a plain ``IndicatorComputeError`` (not a ring
        sub-error) must still land in ``_failures`` so the existing
        per-indicator failure path doesn't break.
        """
        from engine import air

        def fake_snapshot(aoi, pollutant, time_range, mode, ee_client, fallback=None):
            raise IndicatorComputeError(
                indicator_id=f"air.{pollutant}",
                reason="some other failure mode",
            )

        monkeypatch.setattr(air, "compute_pollutant_snapshot", fake_snapshot)

        aoi = {"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 25}
        selected = {"air.no2.score"}
        # Single-pollutant all-fail trips PillarComputeError — that's
        # the existing behaviour for non-ring failures.
        from engine.exceptions import PillarComputeError
        with pytest.raises(PillarComputeError):
            air.run_pillar(
                aoi=aoi,
                time_range=("2026-02-19", "2026-05-20"),
                mode="screening",
                selected_indicators=selected,
                ee_client=None,
            )


# ---------------------------------------------------------------------------
# 6. engine.ghg.run_pillar — same routing for CH₄ / VIIRS
# ---------------------------------------------------------------------------

class TestGhgRunPillarRoutesSkip:
    def test_ring_failure_skips_instead_of_failing(self, monkeypatch):
        from engine import ghg

        def fake_snapshot(aoi, indicator, time_range, mode, ee_client, fallback=None):
            raise BackgroundRingNoDataError(
                indicator_id=f"ghg.{indicator}",
                reason="background ring has no valid pixels — over water",
            )

        def fake_viirs(aoi, time_range, mode, ee_client):
            raise BackgroundRingNoDataError(
                indicator_id="ghg.viirs",
                reason="background ring has no valid pixels — over water",
            )

        monkeypatch.setattr(ghg, "compute_ghg_indicator_snapshot", fake_snapshot)
        # M-GHG-REDESIGN-A1 — VIIRS has its own sustained-contrast path; a ring
        # failure surfaces from it directly. The dispatcher's BackgroundRing
        # handler is indicator-agnostic, so both still route to the same skip.
        monkeypatch.setattr(ghg, "compute_viirs_sustained_contrast", fake_viirs)

        aoi = {"centre": {"lat": -22.0, "lon": -43.0}, "radius_km": 281}
        # CH₄ goes through six_step; VIIRS through compute_viirs_sustained_
        # contrast. CO2 has its own ODIAC path (out_of_coverage skip).
        selected = {"ghg.ch4.score", "ghg.viirs.score"}
        result = ghg.run_pillar(
            aoi=aoi,
            time_range=("2026-02-19", "2026-05-20"),
            mode="screening",
            selected_indicators=selected,
            ee_client=None,
        )

        assert "_failures" not in result
        for ind in ("ch4", "viirs"):
            prov = result[f"_provenance.ghg.{ind}"]
            assert prov["skipped_reason"] == "background_ring_no_data"


# ---------------------------------------------------------------------------
# 7. UI prose registration — kept in lock-step
# ---------------------------------------------------------------------------

def test_skipped_reason_prose_registered_in_c9():
    # M-RING-UX broadened the prose: still mentions water but no longer
    # leads with "Background ring" (now "Background data unavailable").
    # The water cause and the cloud-cover cause are both surfaced.
    assert "background_ring_no_data" in _SKIPPED_REASON_PROSE
    text = _SKIPPED_REASON_PROSE["background_ring_no_data"]
    assert "Background data unavailable" in text
    assert "water" in text
    assert "cloud cover" in text


def test_skipped_reason_prose_registered_in_c4b():
    assert "background_ring_no_data" in _SKIPPED_REASON_TRANSLATIONS
    assert (
        _SKIPPED_REASON_TRANSLATIONS["background_ring_no_data"]
        == _SKIPPED_REASON_PROSE["background_ring_no_data"]
    )
