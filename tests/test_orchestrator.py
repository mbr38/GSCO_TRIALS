"""Tests for engine.orchestrator.ScreeningRun (Milestone 4).

All tests stub `engine.air.run_pillar` via `monkeypatch.setitem` on the
orchestrator's `_PILLARS` dict — no real Earth Engine calls.

The dict-entry path (rather than `monkeypatch.setattr` on
`engine.air.run_pillar` directly) is necessary because `_PILLARS` captures
the function reference at import time; mutating `engine.air.run_pillar`
later doesn't update the captured reference.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from engine import orchestrator
from engine.exceptions import PillarComputeError
from engine.orchestrator import ScreeningRun


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_AOI = {"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 50}
_TIME_RANGE = ("2026-01-01", "2026-04-01")
_CENTRE_METADATA = {"node_id": "test-1", "node_name": "Test point"}

_SELECTED_AIR_ONLY = {"air.no2.score", "air.so2.score"}

_POLLUTANTS = (
    "no2", "so2", "co", "hcho", "o3", "aai", "pm25", "pm10", "aod",
)
_MEASUREMENT_KEYS = (
    "site", "background", "anomaly", "z", "hf",
    "trend", "trend_p", "confidence", "score",
)
_SUB_AGGREGATE_IDS = (
    "air.pm_or_aerosol",
    "air.industrial_combustion_proxy",
    "air.heavy_industry_score",
    "air.voc_photochemical",
    "air.smoke_dust_regional_transport",
    "air.industrial_air_pollution_burden",
)
_PILLAR_AGGREGATE_IDS = (
    "air.pollution_proxy_score",
    "air.spatiotemporal_anomaly_score",
    "air.trend_score",
    "air.measurement_quality_score",  # M-ATTRIB-A1 (AT16)
    "air.audit_followup_priority",
)


def _fake_air_payload() -> dict:
    """Build a full Air-pillar payload: 9 × 9 single-value keys + provenance
    + 6 sub-aggregates + 5 pillar aggregates. Numeric values are arbitrary
    but distinct enough to verify which value reached which composite slot.
    """
    payload: dict = {}
    for pol in _POLLUTANTS:
        for measurement in _MEASUREMENT_KEYS:
            payload[f"air.{pol}.{measurement}"] = 0.5
        payload[f"_provenance.air.{pol}"] = {
            "asset_id":   "FAKE/ASSET",
            "time_range": _TIME_RANGE,
        }
    for sub_id in _SUB_AGGREGATE_IDS:
        payload[sub_id] = 0.5
    # Pillar aggregates — distinct values so we can confirm which one the
    # composite picks up.
    payload["air.pollution_proxy_score"]        = 0.45
    payload["air.spatiotemporal_anomaly_score"] = 0.55
    payload["air.trend_score"]                  = 0.0
    # M-ATTRIB-A1 (AT16) — dual-emit: orchestrator reads the new ID.
    payload["air.measurement_quality_score"]    = 0.72
    payload["air.attribution_confidence_score"] = 0.72
    payload["air.audit_followup_priority"]      = 0.62
    return payload


def _patch_air(monkeypatch, run_pillar_fn) -> None:
    """Replace orchestrator._PILLARS['air'] for the duration of the test.

    Also stubs 'ghg' and 'nature' to no-ops returning {}, so the M4-era tests
    can keep asserting Air-only composite behaviour without picking up real
    GHG or Nature contributions (each would produce non-None quality
    sub-scores even with an empty selection).
    """
    monkeypatch.setitem(orchestrator._PILLARS, "air", run_pillar_fn)
    monkeypatch.setitem(orchestrator._PILLARS, "ghg", lambda **_kw: {})
    monkeypatch.setitem(orchestrator._PILLARS, "nature", lambda **_kw: {})


def _patch_both(monkeypatch, air_fn, ghg_fn) -> None:
    """Replace both pillar functions for two-pillar (M5c) tests.

    Nature is stubbed to a no-op so the M5c-era assertions about Air+GHG
    composite still hold once M5b wires the third pillar.
    """
    monkeypatch.setitem(orchestrator._PILLARS, "air", air_fn)
    monkeypatch.setitem(orchestrator._PILLARS, "ghg", ghg_fn)
    monkeypatch.setitem(orchestrator._PILLARS, "nature", lambda **_kw: {})


# ---------------------------------------------------------------------------
# 1. Happy path — Air succeeds end-to-end
# ---------------------------------------------------------------------------

class TestHappyPathSinglePillar:
    def _run(self, monkeypatch, selected: set[str] | None = None) -> dict:
        _patch_air(monkeypatch, lambda **_kw: _fake_air_payload())
        return ScreeningRun(
            aoi=_AOI,
            selected_indicators=selected or _SELECTED_AIR_ONLY,
            time_range=_TIME_RANGE,
            ee_client=None,
            centre_metadata=_CENTRE_METADATA,
        ).run()

    def test_every_run_pillar_key_present_in_result(self, monkeypatch) -> None:
        result = self._run(monkeypatch)
        for key in _fake_air_payload():
            assert key in result, f"missing key {key!r}"

    def test_composite_is_none_when_only_one_pillar_ran(self, monkeypatch) -> None:
        """M-FOLLOWUP-FALLBACK: composite is strict-None — if any pillar's
        priority is None (here GHG and Nature are stubbed to no-ops),
        the composite is None. The prior survivor-mean behaviour
        propagated the lone surviving pillar's priority as the
        composite, which masked the fact that two of three pillars
        contributed nothing."""
        result = self._run(monkeypatch)
        # Air's priority still computes (Air pillar stub returns it).
        assert result["air.audit_followup_priority"] == pytest.approx(0.62)
        # But composite is None because GHG + Nature returned no priority.
        assert result["composite.overall_screening"] is None

    def test_composite_confidence_is_none_when_only_one_pillar_ran(
        self, monkeypatch,
    ) -> None:
        """M-FOLLOWUP-FALLBACK: composite confidence is strict-None for
        the same reason — the prior survivor-min behaviour exposed a
        single pillar's confidence as the headline."""
        result = self._run(monkeypatch)
        assert result["composite.confidence"] is None

    def test_meta_pillars_run_lists_all_wired_pillars(self, monkeypatch) -> None:
        # M5b/M5c wired GHG + Nature, so the orchestrator now attempts all
        # three pillars even when this test stubs GHG and Nature to no-ops
        # via `_patch_air`.
        result = self._run(monkeypatch)
        assert result["_meta"]["pillars_run"] == ["air", "ghg", "nature"]

    def test_meta_computed_at_is_valid_iso_timestamp(self, monkeypatch) -> None:
        result = self._run(monkeypatch)
        parsed = datetime.fromisoformat(result["_meta"]["computed_at"])
        # UTC tz info round-trips through .isoformat() / .fromisoformat().
        assert parsed.tzinfo is not None

    def test_meta_passthrough_fields_match_constructor(self, monkeypatch) -> None:
        result = self._run(monkeypatch)
        meta = result["_meta"]
        assert meta["aoi"] == _AOI
        assert meta["time_range"] == _TIME_RANGE
        assert meta["centre_metadata"] == _CENTRE_METADATA
        assert meta["mode"] == "screening"
        assert meta["selected_indicators"] == sorted(_SELECTED_AIR_ONLY)

    def test_no_failures_key_when_air_succeeded(self, monkeypatch) -> None:
        result = self._run(monkeypatch)
        assert "_failures" not in result


# ---------------------------------------------------------------------------
# 2. Per-indicator failures within Air — namespaced under "air"
# ---------------------------------------------------------------------------

class TestIndicatorLevelFailures:
    def test_air_failures_list_namespaced_under_air_key(self, monkeypatch) -> None:
        payload = _fake_air_payload()
        air_failures_list = [{
            "pollutant":    "pm25",
            "indicator_id": "air.pm25",
            "reason":       "background ring has no valid pixels",
        }]
        payload["_failures"] = air_failures_list
        _patch_air(monkeypatch, lambda **_kw: payload)

        result = ScreeningRun(
            aoi=_AOI,
            selected_indicators=_SELECTED_AIR_ONLY,
            time_range=_TIME_RANGE,
            ee_client=None,
            centre_metadata=_CENTRE_METADATA,
        ).run()

        assert "_failures" in result
        assert result["_failures"]["air"] == air_failures_list
        # Orchestrator did not abort. M-FOLLOWUP-FALLBACK: composite is
        # None because GHG + Nature are stubbed no-ops (no priority);
        # Air's priority still computes via its stubbed payload.
        assert result["air.audit_followup_priority"] == pytest.approx(0.62)
        assert result["composite.overall_screening"] is None


# ---------------------------------------------------------------------------
# 3. Pillar-wide failure — PillarComputeError is caught, not propagated
# ---------------------------------------------------------------------------

class TestPillarWideFailure:
    def test_pillar_compute_error_is_caught_and_recorded(self, monkeypatch) -> None:
        affected = [
            "air.no2.score", "air.no2.confidence",
            "air.so2.score", "air.so2.confidence",
        ]

        def _raise(**_kw):
            raise PillarComputeError(
                pillar="air",
                indicator_ids=affected,
                reason="all selected pollutants failed",
            )
        _patch_air(monkeypatch, _raise)

        # Must NOT raise.
        result = ScreeningRun(
            aoi=_AOI,
            selected_indicators=_SELECTED_AIR_ONLY,
            time_range=_TIME_RANGE,
            ee_client=None,
            centre_metadata=_CENTRE_METADATA,
        ).run()

        # Failure recorded under namespaced shape with "pillar_wide" marker.
        assert "_failures" in result
        air_entries = result["_failures"]["air"]
        assert any(e.get("type") == "pillar_wide" for e in air_entries)
        wide = next(e for e in air_entries if e.get("type") == "pillar_wide")
        assert wide["indicator_ids"] == affected
        assert "all selected pollutants failed" in wide["reason"]

        # Affected IDs are explicitly None in the payload.
        for ind_id in affected:
            assert result[ind_id] is None

        # Composite is None — no pillar produced a follow-up priority.
        assert result["composite.overall_screening"] is None

        # Air was attempted (and failed); GHG is stubbed to a no-op by
        # `_patch_air`. Both are listed because the orchestrator records
        # every pillar in `_PILLARS` regardless of outcome.
        assert result["_meta"]["pillars_run"] == ["air", "ghg", "nature"]


# ---------------------------------------------------------------------------
# 4. Selected indicators filtered per pillar
# ---------------------------------------------------------------------------

class TestSelectedIndicatorsFilteredPerPillar:
    def test_air_pillar_receives_only_air_indicators(self, monkeypatch) -> None:
        captured: dict = {}

        def _spy(**kwargs):
            captured.update(kwargs)
            return _fake_air_payload()
        _patch_air(monkeypatch, _spy)

        ScreeningRun(
            aoi=_AOI,
            selected_indicators={
                "air.no2.score",
                "ghg.ch4.score",          # Should NOT reach the air pillar.
                "nature.kba.dist_km",     # Should NOT reach the air pillar.
            },
            time_range=_TIME_RANGE,
            ee_client=None,
            centre_metadata=_CENTRE_METADATA,
        ).run()

        assert captured["selected_indicators"] == {"air.no2.score"}
        # And the orchestrator passes through the other kwargs intact.
        assert captured["aoi"] == _AOI
        assert captured["time_range"] == _TIME_RANGE
        assert captured["mode"] == "screening"


# ---------------------------------------------------------------------------
# 5. Composite is None when no pillar succeeded
# ---------------------------------------------------------------------------

class TestCompositeWhenAllPillarsFail:
    def test_composite_overall_and_confidence_both_none(self, monkeypatch) -> None:
        def _raise(**_kw):
            raise PillarComputeError(
                pillar="air",
                indicator_ids=["air.no2.score"],
                reason="everything failed",
            )
        _patch_air(monkeypatch, _raise)

        result = ScreeningRun(
            aoi=_AOI,
            selected_indicators=_SELECTED_AIR_ONLY,
            time_range=_TIME_RANGE,
            ee_client=None,
            centre_metadata=_CENTRE_METADATA,
        ).run()

        assert result["composite.overall_screening"] is None
        assert result["composite.confidence"] is None


# ---------------------------------------------------------------------------
# 6. Composite IDs live at top level — verbal-summary generator depends on this
# ---------------------------------------------------------------------------

class TestCompositeIdsTopLevel:
    def test_composite_keys_are_top_level_not_nested_under_meta(self, monkeypatch) -> None:
        _patch_air(monkeypatch, lambda **_kw: _fake_air_payload())
        result = ScreeningRun(
            aoi=_AOI,
            selected_indicators=_SELECTED_AIR_ONLY,
            time_range=_TIME_RANGE,
            ee_client=None,
            centre_metadata=_CENTRE_METADATA,
        ).run()
        assert "composite.overall_screening" in result
        assert "composite.confidence" in result
        assert "composite.overall_screening" not in result["_meta"]
        assert "composite.confidence" not in result["_meta"]


# ===========================================================================
# Milestone 5c — two-pillar scenarios (Air + GHG)
# ===========================================================================


def _fake_ghg_payload() -> dict:
    """Synthetic GHG payload: CH₄ (full 9 measurements) + VIIRS (reduced 5)
    + four quality sub-scores + eight sub-aggregates + five pillar aggregates."""
    payload: dict = {}
    # CH₄ full measurement set.
    for measurement in (
        "site", "background", "anomaly", "z", "hf",
        "trend", "trend_p", "confidence", "score",
    ):
        payload[f"ghg.ch4.{measurement}"] = 0.5
    payload["_provenance.ghg.ch4"] = {
        "asset_id": "FAKE/CH4", "time_range": _TIME_RANGE,
    }
    # VIIRS reduced set.
    for measurement in ("site", "anomaly", "trend", "confidence", "score"):
        payload[f"ghg.viirs.{measurement}"] = 0.5
    payload["_provenance.ghg.viirs"] = {
        "asset_id": "FAKE/VIIRS", "time_range": _TIME_RANGE,
    }
    # Quality sub-scores.
    payload["ghg.temporal_coverage"]              = 0.8
    payload["ghg.spatial_resolution_suitability"] = 1.0
    payload["ghg.retrieval_inventory_quality"]    = 0.7
    payload["ghg.nearby_source_isolation"]        = 1.0
    # Sub-aggregates: three CO₂-dependent stubs are None.
    payload["ghg.ch4_hotspot_signal"]            = 0.5
    payload["ghg.combustion_proxy"]              = 0.4
    payload["ghg.activity_score"]                = 0.5
    payload["ghg.fire_or_regional_transport_risk"] = 0.3
    payload["ghg.ch4_context_adjusted"]          = 0.45
    payload["ghg.co2_context"]                   = None
    payload["ghg.fossil_combustion_score"]       = None
    payload["ghg.activity_adjusted_co2"]         = None
    # Pillar aggregates — distinct values so we can confirm which one
    # the composite picks up.
    payload["ghg.core_audit_support"]         = 0.42
    payload["ghg.spatiotemporal_anomaly"]     = 0.50
    payload["ghg.trend"]                      = 0.0
    payload["ghg.data_quality_attribution"]   = 0.65
    payload["ghg.audit_followup_priority"]    = 0.55
    return payload


class TestTwoPillarHappyPath:
    def test_composite_is_none_when_nature_no_op_under_strict_propagation(
        self, monkeypatch,
    ) -> None:
        """M-FOLLOWUP-FALLBACK: composite is strict-None — Nature is
        stubbed to a no-op, so it produces no priority and the composite
        is None even though Air and GHG both compute. Pre-fix the
        composite would silently average over the two pillars that did
        produce priorities, masking the missing third pillar.
        """
        _patch_both(
            monkeypatch,
            air_fn=lambda **_kw: _fake_air_payload(),
            ghg_fn=lambda **_kw: _fake_ghg_payload(),
        )
        result = ScreeningRun(
            aoi=_AOI,
            selected_indicators={"air.no2.score", "ghg.ch4.score"},
            time_range=_TIME_RANGE,
            ee_client=None,
            centre_metadata=_CENTRE_METADATA,
        ).run()

        # Keys from both pillars present.
        assert "air.no2.score" in result
        assert "ghg.ch4.score" in result
        # Air + GHG priorities still compute from their stubbed payloads.
        assert result["air.audit_followup_priority"] == pytest.approx(0.62)
        assert result["ghg.audit_followup_priority"] == pytest.approx(0.55)

        # M-FOLLOWUP-FALLBACK: composite is None (Nature stub returned
        # no priority).
        assert result["composite.overall_screening"] is None
        assert result["composite.confidence"] is None

        # All three pillars still listed in _meta.
        assert result["_meta"]["pillars_run"] == ["air", "ghg", "nature"]

        # No failures.
        assert "_failures" not in result

    def test_composite_is_mean_when_all_three_pillars_contribute(
        self, monkeypatch,
    ) -> None:
        """Regression coverage for the happy three-pillar case. When
        every pillar produces a priority and confidence, the composite
        is the equal-weighted mean of priorities and the min of
        confidences. This is the path the old test would have exercised
        if Nature had been wired into the M5c-era stubs.
        """
        def _fake_nature_payload() -> dict:
            return {
                "nature.followup_priority":   0.40,
                "nature.measurement_quality": 0.55,  # M-ATTRIB-A1 (AT13)
            }

        monkeypatch.setitem(orchestrator._PILLARS, "air",    lambda **_kw: _fake_air_payload())
        monkeypatch.setitem(orchestrator._PILLARS, "ghg",    lambda **_kw: _fake_ghg_payload())
        monkeypatch.setitem(orchestrator._PILLARS, "nature", lambda **_kw: _fake_nature_payload())

        result = ScreeningRun(
            aoi=_AOI,
            selected_indicators={
                "air.no2.score", "ghg.ch4.score", "nature.kba.proximity_score",
            },
            time_range=_TIME_RANGE,
            ee_client=None,
            centre_metadata=_CENTRE_METADATA,
        ).run()

        # Composite priority is mean of the three.
        assert result["composite.overall_screening"] == pytest.approx(
            (0.62 + 0.55 + 0.40) / 3,
        )
        # Composite confidence is min of the three.
        assert result["composite.confidence"] == pytest.approx(
            min(0.72, 0.65, 0.55),
        )


class TestAccumulatedPayloadThreadedToGhg:
    def test_ghg_run_pillar_receives_air_payload_in_accumulated_arg(
        self, monkeypatch,
    ) -> None:
        captured: dict = {}

        def _spy_ghg(**kwargs):
            captured.update(kwargs)
            return _fake_ghg_payload()

        _patch_both(
            monkeypatch,
            air_fn=lambda **_kw: _fake_air_payload(),
            ghg_fn=_spy_ghg,
        )

        ScreeningRun(
            aoi=_AOI,
            selected_indicators={"air.no2.score", "ghg.ch4.score"},
            time_range=_TIME_RANGE,
            ee_client=None,
            centre_metadata=_CENTRE_METADATA,
        ).run()

        accumulated = captured["accumulated_payload"]
        # The two values GHG borrows for its sub-aggregates.
        assert "air.industrial_combustion_proxy" in accumulated
        assert "air.smoke_dust_regional_transport" in accumulated
        # _fake_air_payload sets every air.<pollutant>.* and sub-aggregate
        # to 0.5, including these two.
        assert accumulated["air.industrial_combustion_proxy"] == 0.5
        assert accumulated["air.smoke_dust_regional_transport"] == 0.5


class TestPerPillarFailuresNamespaced:
    def test_air_and_ghg_failures_both_present_without_overwriting(
        self, monkeypatch,
    ) -> None:
        air_payload = _fake_air_payload()
        air_payload["_failures"] = [{
            "pollutant":    "pm25",
            "indicator_id": "air.pm25",
            "reason":       "air failure here",
        }]
        ghg_payload = _fake_ghg_payload()
        ghg_payload["_failures"] = [{
            "indicator":    "ch4",
            "indicator_id": "ghg.ch4",
            "reason":       "ghg failure here",
        }]
        _patch_both(
            monkeypatch,
            air_fn=lambda **_kw: air_payload,
            ghg_fn=lambda **_kw: ghg_payload,
        )

        result = ScreeningRun(
            aoi=_AOI,
            selected_indicators={"air.no2.score", "ghg.ch4.score"},
            time_range=_TIME_RANGE,
            ee_client=None,
            centre_metadata=_CENTRE_METADATA,
        ).run()

        assert "_failures" in result
        assert "air" in result["_failures"]
        assert "ghg" in result["_failures"]
        # Each pillar's list survives intact — no overwriting.
        assert result["_failures"]["air"][0]["reason"] == "air failure here"
        assert result["_failures"]["ghg"][0]["reason"] == "ghg failure here"


class TestAirSucceedsGhgPillarWideFails:
    def test_composite_is_none_when_ghg_pillar_fails(
        self, monkeypatch,
    ) -> None:
        """M-FOLLOWUP-FALLBACK: when any pillar's priority is None
        (here GHG raised PillarComputeError, so its priority key is
        absent), the composite is None. The prior survivor-mean
        behaviour exposed Air's priority as the composite, masking the
        fact that GHG didn't run at all.
        """
        def _ghg_fail(**_kw):
            raise PillarComputeError(
                pillar="ghg",
                indicator_ids=["ghg.ch4.score", "ghg.viirs.score"],
                reason="all selected GHG indicators failed",
            )

        _patch_both(
            monkeypatch,
            air_fn=lambda **_kw: _fake_air_payload(),
            ghg_fn=_ghg_fail,
        )

        result = ScreeningRun(
            aoi=_AOI,
            selected_indicators={"air.no2.score", "ghg.ch4.score"},
            time_range=_TIME_RANGE,
            ee_client=None,
            centre_metadata=_CENTRE_METADATA,
        ).run()

        # Air priority still computes from its stubbed payload, but the
        # composite is None because GHG's priority is missing.
        assert result["air.audit_followup_priority"] == pytest.approx(0.62)
        assert result["composite.overall_screening"] is None

        # GHG failure recorded under namespaced shape.
        assert "ghg" in result["_failures"]
        assert any(
            e.get("type") == "pillar_wide" for e in result["_failures"]["ghg"]
        )

        # Both pillars still listed — GHG was attempted, it just failed.
        assert result["_meta"]["pillars_run"] == ["air", "ghg", "nature"]


class TestBothPillarsPillarWideFail:
    def test_composite_none_and_both_failures_recorded(self, monkeypatch) -> None:
        def _air_fail(**_kw):
            raise PillarComputeError(
                pillar="air", indicator_ids=["air.no2.score"], reason="air down",
            )

        def _ghg_fail(**_kw):
            raise PillarComputeError(
                pillar="ghg", indicator_ids=["ghg.ch4.score"], reason="ghg down",
            )

        _patch_both(monkeypatch, air_fn=_air_fail, ghg_fn=_ghg_fail)

        result = ScreeningRun(
            aoi=_AOI,
            selected_indicators={"air.no2.score", "ghg.ch4.score"},
            time_range=_TIME_RANGE,
            ee_client=None,
            centre_metadata=_CENTRE_METADATA,
        ).run()

        assert result["composite.overall_screening"] is None
        assert result["composite.confidence"] is None
        for pillar in ("air", "ghg"):
            assert pillar in result["_failures"]
            assert any(
                e.get("type") == "pillar_wide"
                for e in result["_failures"][pillar]
            )


class TestSelectedRoutedAcrossTwoPillars:
    def test_each_pillar_receives_only_its_own_indicators(
        self, monkeypatch,
    ) -> None:
        air_captured: dict = {}
        ghg_captured: dict = {}

        def _spy_air(**kwargs):
            air_captured.update(kwargs)
            return _fake_air_payload()

        def _spy_ghg(**kwargs):
            ghg_captured.update(kwargs)
            return _fake_ghg_payload()

        _patch_both(monkeypatch, air_fn=_spy_air, ghg_fn=_spy_ghg)

        ScreeningRun(
            aoi=_AOI,
            selected_indicators={
                "air.no2.score",
                "ghg.ch4.score",
                "nature.kba.dist_km",  # Should not reach either pillar.
            },
            time_range=_TIME_RANGE,
            ee_client=None,
            centre_metadata=_CENTRE_METADATA,
        ).run()

        assert air_captured["selected_indicators"] == {"air.no2.score"}
        assert ghg_captured["selected_indicators"] == {"ghg.ch4.score"}
