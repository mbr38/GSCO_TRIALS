"""Synthetic-payload tests for engine.air (Milestones 3a + 3b).

Tests do not touch Earth Engine. `ee.ImageCollection` is stubbed with a
chain-friendly fake; `engine.air.six_step` and `compute_pollutant_snapshot`
are monkey-patched per test as needed.

Real-EE smoke tests live in tests/test_air_integration.py (skipped unless
`RUN_EE_TESTS=1` is set).
"""

from __future__ import annotations

import math

import pytest

from engine.air import (
    AIR_POLLUTANT_CONFIG,
    PollutantConfig,
    apply_aod_qa_mask,
    compute_air_audit_followup_priority,
    compute_air_pollution_proxy_score,
    compute_attribution_confidence_score,
    compute_heavy_industry_score,
    compute_industrial_air_pollution_burden,
    compute_industrial_combustion_proxy,
    compute_pm_or_aerosol,
    compute_pollutant_snapshot,
    compute_smoke_dust_regional_transport,
    compute_spatiotemporal_anomaly_score,
    compute_trend_score,
    compute_voc_photochemical,
    run_pillar,
)
from engine.constants import (
    HEAVY_INDUSTRY_WEIGHTS,
    INDUSTRIAL_BURDEN_WEIGHTS,
    INDUSTRIAL_COMBUSTION_PROXY_WEIGHTS,
    O3_SCORE_CAP,
    PM_OR_AEROSOL_WEIGHTS,
    SMOKE_DUST_TRANSPORT_WEIGHTS,
    VOC_PHOTOCHEMICAL_WEIGHTS,
)
from engine.exceptions import IndicatorComputeError, PillarComputeError


# ---------------------------------------------------------------------------
# Fakes that let air.py build its ImageCollection without EE init
# ---------------------------------------------------------------------------

class _FakeIC:
    """Chain-friendly stand-in for ee.ImageCollection."""

    def map(self, _fn): return self
    def select(self, _band): return self
    def filterDate(self, *_a, **_kw): return self


@pytest.fixture
def fake_ee(monkeypatch):
    """Replace `engine.air.ee.ImageCollection` with a chainable fake.

    Without this, building the ImageCollection inside compute_pollutant_snapshot
    would attempt to talk to the real EE backend.
    """
    monkeypatch.setattr(
        "engine.air.ee.ImageCollection",
        lambda *_a, **_kw: _FakeIC(),
    )


_DEFAULT_SIX_STEP: dict = {
    "site":       100.0,
    "background": 50.0,
    "anomaly":    50.0,
    "z":          5.0,
    "hf":         0.4,
    "trend":      None,
    "trend_p":    None,
    "confidence": 0.7,
    "score":      0.6,
}


@pytest.fixture
def fake_six_step(monkeypatch):
    """Replace `engine.air.six_step` with a lambda returning a configurable dict."""

    def install(payload: dict | None = None) -> dict:
        result = payload if payload is not None else dict(_DEFAULT_SIX_STEP)
        monkeypatch.setattr("engine.air.six_step", lambda **_kw: result)
        return result

    return install


# Large enough to clear the pixel-size guard for CAMS (44.5 km native pixel)
# so the parametrized "all pollutants" tests can use a single AOI fixture.
_AOI = {"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 50}
_TIME_RANGE = ("2026-01-01", "2026-04-01")


# ---------------------------------------------------------------------------
# AIR_POLLUTANT_CONFIG integrity
# ---------------------------------------------------------------------------

class TestConfigIntegrity:
    def test_nine_pollutants_registered(self) -> None:
        assert set(AIR_POLLUTANT_CONFIG.keys()) == {
            "no2", "so2", "co", "hcho", "o3", "aai", "pm25", "pm10", "aod",
        }

    @pytest.mark.parametrize("key", list(AIR_POLLUTANT_CONFIG.keys()))
    def test_each_entry_has_required_fields(self, key: str) -> None:
        cfg = AIR_POLLUTANT_CONFIG[key]
        assert isinstance(cfg, PollutantConfig)
        assert cfg.asset_id
        assert cfg.band
        assert cfg.scale_factor > 0
        assert cfg.scale_m > 0
        assert cfg.display_unit
        assert cfg.direction in ("higher_is_worse", "lower_is_worse")

    def test_o3_score_cap_is_one_half(self) -> None:
        assert AIR_POLLUTANT_CONFIG["o3"].score_cap == 0.5
        assert AIR_POLLUTANT_CONFIG["o3"].score_cap == O3_SCORE_CAP

    def test_aod_has_callable_preprocess(self) -> None:
        cfg = AIR_POLLUTANT_CONFIG["aod"]
        assert callable(cfg.preprocess)
        assert cfg.preprocess is apply_aod_qa_mask

    def test_only_o3_has_a_score_cap(self) -> None:
        for key, cfg in AIR_POLLUTANT_CONFIG.items():
            if key == "o3":
                continue
            assert cfg.score_cap is None, f"{key} unexpectedly has a score_cap"

    def test_only_aod_has_a_preprocess(self) -> None:
        for key, cfg in AIR_POLLUTANT_CONFIG.items():
            if key == "aod":
                continue
            assert cfg.preprocess is None, f"{key} unexpectedly has a preprocess"


# ---------------------------------------------------------------------------
# O3 score-cap behaviour  (IC_v4 §1.3)
# ---------------------------------------------------------------------------

class TestO3ScoreCap:
    def _run_o3(self, fake_six_step, *, score: float | None) -> dict:
        fake_six_step({**_DEFAULT_SIX_STEP, "score": score})
        return compute_pollutant_snapshot(
            aoi=_AOI, pollutant="o3", time_range=_TIME_RANGE,
            mode="screening", ee_client=None,
        )

    def test_high_o3_score_capped_to_half(self, fake_ee, fake_six_step) -> None:
        result = self._run_o3(fake_six_step, score=0.9)
        assert result["air.o3.score"] == 0.5

    def test_low_o3_score_unchanged(self, fake_ee, fake_six_step) -> None:
        result = self._run_o3(fake_six_step, score=0.3)
        assert result["air.o3.score"] == 0.3

    def test_o3_score_none_stays_none(self, fake_ee, fake_six_step) -> None:
        # If six_step returned None (degenerate background), the cap must not
        # synthesise a value.
        result = self._run_o3(fake_six_step, score=None)
        assert result["air.o3.score"] is None

    def test_no2_high_score_not_capped(self, fake_ee, fake_six_step) -> None:
        # Sanity check: other pollutants do not get the o3 cap applied.
        fake_six_step({**_DEFAULT_SIX_STEP, "score": 0.9})
        result = compute_pollutant_snapshot(
            aoi=_AOI, pollutant="no2", time_range=_TIME_RANGE,
            mode="screening", ee_client=None,
        )
        assert result["air.no2.score"] == 0.9


# ---------------------------------------------------------------------------
# Canonical ID mapping
# ---------------------------------------------------------------------------

class TestCanonicalIdMapping:
    @pytest.mark.parametrize("pollutant", list(AIR_POLLUTANT_CONFIG.keys()))
    def test_every_pollutant_returns_the_nine_measurement_keys(
        self, fake_ee, fake_six_step, pollutant: str,
    ) -> None:
        fake_six_step()
        result = compute_pollutant_snapshot(
            aoi=_AOI, pollutant=pollutant, time_range=_TIME_RANGE,
            mode="screening", ee_client=None,
        )
        for measurement in (
            "site", "background", "anomaly", "z", "hf",
            "trend", "trend_p", "confidence", "score",
        ):
            assert f"air.{pollutant}.{measurement}" in result

    def test_values_pass_through_from_six_step(self, fake_ee, fake_six_step) -> None:
        fake_six_step()
        result = compute_pollutant_snapshot(
            aoi=_AOI, pollutant="no2", time_range=_TIME_RANGE,
            mode="screening", ee_client=None,
        )
        assert result["air.no2.site"] == 100.0
        assert result["air.no2.background"] == 50.0
        assert result["air.no2.anomaly"] == 50.0
        assert result["air.no2.confidence"] == 0.7

    def test_none_values_propagate(self, fake_ee, fake_six_step) -> None:
        # trend / trend_p are None until engine/core/trend.py lands; the
        # mapping must preserve that, not silently drop them.
        fake_six_step()
        result = compute_pollutant_snapshot(
            aoi=_AOI, pollutant="no2", time_range=_TIME_RANGE,
            mode="screening", ee_client=None,
        )
        assert result["air.no2.trend"] is None
        assert result["air.no2.trend_p"] is None


# ---------------------------------------------------------------------------
# Provenance block
# ---------------------------------------------------------------------------

class TestProvenance:
    @pytest.mark.parametrize("pollutant", list(AIR_POLLUTANT_CONFIG.keys()))
    def test_provenance_block_present_for_every_pollutant(
        self, fake_ee, fake_six_step, pollutant: str,
    ) -> None:
        fake_six_step()
        result = compute_pollutant_snapshot(
            aoi=_AOI, pollutant=pollutant, time_range=_TIME_RANGE,
            mode="screening", ee_client=None,
        )
        prov = result[f"_provenance.air.{pollutant}"]
        assert prov["asset_id"] == AIR_POLLUTANT_CONFIG[pollutant].asset_id
        assert prov["time_range"] == _TIME_RANGE


# ---------------------------------------------------------------------------
# Wrappers
# ---------------------------------------------------------------------------

class TestWrappers:
    def test_pm25_wrapper_delegates_with_correct_key(
        self, fake_ee, fake_six_step,
    ) -> None:
        from engine.air import compute_pm25_proxy
        fake_six_step()
        result = compute_pm25_proxy(_AOI, _TIME_RANGE, "screening", None)
        assert "air.pm25.score" in result
        assert "_provenance.air.pm25" in result

    def test_pm10_wrapper_delegates_with_correct_key(
        self, fake_ee, fake_six_step,
    ) -> None:
        from engine.air import compute_pm10_proxy
        fake_six_step()
        result = compute_pm10_proxy(_AOI, _TIME_RANGE, "screening", None)
        assert "air.pm10.score" in result

    def test_aod_wrapper_delegates_with_correct_key(
        self, fake_ee, fake_six_step,
    ) -> None:
        from engine.air import compute_aod
        fake_six_step()
        result = compute_aod(_AOI, _TIME_RANGE, "screening", None)
        assert "air.aod.score" in result


# ---------------------------------------------------------------------------
# Unknown pollutant
# ---------------------------------------------------------------------------

class TestUnknownPollutant:
    def test_unknown_key_raises_key_error(self, fake_ee) -> None:
        with pytest.raises(KeyError):
            compute_pollutant_snapshot(
                aoi=_AOI, pollutant="nox", time_range=_TIME_RANGE,
                mode="screening", ee_client=None,
            )


# ---------------------------------------------------------------------------
# Pixel-size guard (catches buffer < native pixel before EE is invoked)
# ---------------------------------------------------------------------------

class TestPixelSizeGuard:
    def test_pm25_at_1km_radius_raises_before_ee_call(self) -> None:
        # No `fake_ee` fixture: the guard must fire before any ee.* call.
        with pytest.raises(
            IndicatorComputeError,
            match=r"smaller than .* native pixel",
        ):
            compute_pollutant_snapshot(
                aoi={"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 1},
                pollutant="pm25",
                time_range=_TIME_RANGE,
                mode="screening",
                ee_client=None,
            )


# ===========================================================================
# Milestone 3b — sub-aggregates, pillar aggregates, run_pillar
# ===========================================================================

# ---------------------------------------------------------------------------
# Sub-aggregate weight integrity  (IC_v4 §1.2)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,weights", [
    ("PM_OR_AEROSOL_WEIGHTS",              PM_OR_AEROSOL_WEIGHTS),
    ("INDUSTRIAL_COMBUSTION_PROXY_WEIGHTS", INDUSTRIAL_COMBUSTION_PROXY_WEIGHTS),
    ("HEAVY_INDUSTRY_WEIGHTS",              HEAVY_INDUSTRY_WEIGHTS),
    ("VOC_PHOTOCHEMICAL_WEIGHTS",           VOC_PHOTOCHEMICAL_WEIGHTS),
    ("SMOKE_DUST_TRANSPORT_WEIGHTS",        SMOKE_DUST_TRANSPORT_WEIGHTS),
    ("INDUSTRIAL_BURDEN_WEIGHTS",           INDUSTRIAL_BURDEN_WEIGHTS),
])
def test_sub_aggregate_weights_sum_to_one(name: str, weights: dict) -> None:
    total = sum(weights.values())
    assert math.isclose(total, 1.0, abs_tol=1e-9), f"{name} sum was {total}"


# ---------------------------------------------------------------------------
# Sub-aggregate happy paths  (IC_v4 §1.2)
# ---------------------------------------------------------------------------

class TestSubAggregateFormulas:
    def test_industrial_combustion_proxy(self) -> None:
        payload = {"air.no2.score": 0.5, "air.co.score": 0.4}
        out = compute_industrial_combustion_proxy(payload)
        assert out["air.industrial_combustion_proxy"] == pytest.approx(0.60 * 0.5 + 0.40 * 0.4)

    def test_heavy_industry_score(self) -> None:
        payload = {
            "air.so2.score":     0.5,
            "air.no2.score":     0.4,
            "air.pm_or_aerosol": 0.3,
        }
        out = compute_heavy_industry_score(payload)
        expected = 0.60 * 0.5 + 0.30 * 0.4 + 0.10 * 0.3
        assert out["air.heavy_industry_score"] == pytest.approx(expected)

    def test_voc_photochemical(self) -> None:
        payload = {
            "air.hcho.score": 0.5,
            "air.no2.score":  0.4,
            "air.o3.score":   0.3,
        }
        out = compute_voc_photochemical(payload)
        expected = 0.50 * 0.5 + 0.30 * 0.4 + 0.20 * 0.3
        assert out["air.voc_photochemical"] == pytest.approx(expected)

    def test_smoke_dust_regional_transport(self) -> None:
        payload = {
            "air.co.score":      0.5,
            "air.aai.score":     0.4,
            "air.pm_or_aerosol": 0.3,
        }
        out = compute_smoke_dust_regional_transport(payload)
        expected = 0.40 * 0.5 + 0.40 * 0.4 + 0.20 * 0.3
        assert out["air.smoke_dust_regional_transport"] == pytest.approx(expected)

    def test_industrial_air_pollution_burden(self) -> None:
        payload = {
            "air.no2.score":     0.5,
            "air.so2.score":     0.4,
            "air.pm_or_aerosol": 0.3,
        }
        out = compute_industrial_air_pollution_burden(payload)
        expected = 0.40 * 0.5 + 0.35 * 0.4 + 0.25 * 0.3
        assert out["air.industrial_air_pollution_burden"] == pytest.approx(expected)

    def test_strict_returns_none_when_any_dependency_missing(self) -> None:
        # Sub-aggregates (other than pm_or_aerosol) are strict — any None dep
        # makes the whole thing None rather than a misleading partial sum.
        payload = {"air.no2.score": 0.5}   # co.score missing
        out = compute_industrial_combustion_proxy(payload)
        assert out["air.industrial_combustion_proxy"] is None


# ---------------------------------------------------------------------------
# compute_pm_or_aerosol — CAMS fallback (IC_v4 §1.2 E4)
# ---------------------------------------------------------------------------

class TestPmOrAerosolFallback:
    def test_primary_path_when_pm25_and_aai_both_present(self) -> None:
        payload = {
            "air.pm25.score": 0.5,
            "air.pm25.site":  25.0,
            "air.aai.score":  0.4,
        }
        out = compute_pm_or_aerosol(payload)
        assert out["air.pm_or_aerosol"] == pytest.approx(0.60 * 0.5 + 0.40 * 0.4)
        assert out["_provenance.air.pm_or_aerosol"] == {"formula": "primary"}

    def test_fallback_when_pm25_site_is_none(self) -> None:
        payload = {
            "air.pm25.score": 0.5,
            "air.pm25.site":  None,
            "air.aai.score":  0.6,
        }
        out = compute_pm_or_aerosol(payload)
        assert out["air.pm_or_aerosol"] == 0.6
        assert out["_provenance.air.pm_or_aerosol"] == {"formula": "fallback_aai_only"}

    def test_fallback_when_pm25_score_is_none(self) -> None:
        payload = {
            "air.pm25.score": None,
            "air.pm25.site":  25.0,
            "air.aai.score":  0.7,
        }
        out = compute_pm_or_aerosol(payload)
        assert out["air.pm_or_aerosol"] == 0.7
        assert out["_provenance.air.pm_or_aerosol"] == {"formula": "fallback_aai_only"}

    def test_returns_none_when_both_pm25_and_aai_unavailable(self) -> None:
        payload = {
            "air.pm25.score": None,
            "air.pm25.site":  None,
            "air.aai.score":  None,
        }
        out = compute_pm_or_aerosol(payload)
        assert out["air.pm_or_aerosol"] is None
        # Fallback provenance is still reported — the trigger fired, AAI just
        # had no value to contribute either.
        assert out["_provenance.air.pm_or_aerosol"] == {"formula": "fallback_aai_only"}


# ---------------------------------------------------------------------------
# Pillar-aggregate renormalisation  (IC_v4 §1.3)
# ---------------------------------------------------------------------------

class TestPillarAggregateRenormalisation:
    def test_pollution_proxy_score_renormalises_over_two_present_pollutants(self) -> None:
        # Only no2 and so2 are in the payload (and in selected). Weights from
        # AIR_POLLUTION_PROXY_WEIGHTS for these are 0.30 and 0.20; renormalise
        # over the sum 0.50.
        payload = {"air.no2.score": 0.5, "air.so2.score": 0.4}
        selected = {"air.no2.score", "air.so2.score"}
        out = compute_air_pollution_proxy_score(payload, selected)
        expected = (0.30 * 0.5 + 0.20 * 0.4) / (0.30 + 0.20)
        assert out["air.pollution_proxy_score"] == pytest.approx(expected)

    def test_pollution_proxy_score_none_when_no_terms_survive(self) -> None:
        out = compute_air_pollution_proxy_score(payload={}, selected=set())
        assert out["air.pollution_proxy_score"] is None


# ---------------------------------------------------------------------------
# compute_trend_score mode handling
# ---------------------------------------------------------------------------

class TestTrendScoreModeHandling:
    def test_screening_mode_returns_zero(self) -> None:
        # Zero regardless of inputs — the Trend term contributes nothing to
        # follow-up priority in screening mode.
        out = compute_trend_score(payload={}, selected=set(), mode="screening")
        assert out["air.trend_score"] == 0.0

    def test_screening_mode_returns_zero_even_with_trend_values_present(self) -> None:
        payload = {"air.no2.trend": 0.123}
        selected = {"air.no2.score"}
        out = compute_trend_score(payload, selected, mode="screening")
        assert out["air.trend_score"] == 0.0

    def test_trend_mode_returns_none_when_all_trend_values_are_none(self) -> None:
        # Trend values are still None pending engine/core/trend.py (M5+).
        payload = {"air.no2.trend": None, "air.so2.trend": None}
        selected = {"air.no2.score", "air.so2.score"}
        out = compute_trend_score(payload, selected, mode="trend")
        assert out["air.trend_score"] is None


# ---------------------------------------------------------------------------
# compute_air_audit_followup_priority — renormalisation on missing terms
# ---------------------------------------------------------------------------

class TestAirAuditFollowupPartialMissing:
    def test_renormalises_when_trend_aggregate_missing(self) -> None:
        # Trend missing (None) → drop the 0.20 weight, renormalise the rest.
        payload = {
            "air.pollution_proxy_score":          0.5,
            "air.spatiotemporal_anomaly_score":   0.4,
            "air.trend_score":                    None,
            "air.attribution_confidence_score":   0.7,
        }
        out = compute_air_audit_followup_priority(payload, mode="trend")
        # Surviving weights: proxy=0.35, anomaly=0.30, confidence=0.15, sum=0.80
        expected = (0.35 * 0.5 + 0.30 * 0.4 + 0.15 * 0.7) / 0.80
        assert out["air.audit_followup_priority"] == pytest.approx(expected)

    def test_returns_none_when_all_inputs_missing(self) -> None:
        out = compute_air_audit_followup_priority(payload={}, mode="screening")
        assert out["air.audit_followup_priority"] is None


# ---------------------------------------------------------------------------
# run_pillar
# ---------------------------------------------------------------------------

_MEASUREMENT_KEYS_FULL: tuple[str, ...] = (
    "site", "background", "anomaly", "z", "hf",
    "trend", "trend_p", "confidence", "score",
)


def _fake_snapshot(
    pollutant: str,
    *,
    score: float = 0.5,
    site:  float = 10.0,
    z:     float = 2.0,
) -> dict:
    """Build a synthetic compute_pollutant_snapshot return dict."""
    return {
        f"air.{pollutant}.site":       site,
        f"air.{pollutant}.background": site * 0.5,
        f"air.{pollutant}.anomaly":    site * 0.5,
        f"air.{pollutant}.z":          z,
        f"air.{pollutant}.hf":         0.3,
        f"air.{pollutant}.trend":      None,
        f"air.{pollutant}.trend_p":    None,
        f"air.{pollutant}.confidence": 0.8,
        f"air.{pollutant}.score":      score,
        f"_provenance.air.{pollutant}": {
            "asset_id":   "FAKE/ASSET",
            "time_range": _TIME_RANGE,
        },
    }


class TestRunPillar:
    def test_full_payload_with_three_pollutants(self, monkeypatch) -> None:
        def fake_compute(aoi, pollutant, time_range, mode, ee_client):
            return _fake_snapshot(pollutant)
        monkeypatch.setattr("engine.air.compute_pollutant_snapshot", fake_compute)

        result = run_pillar(
            aoi={"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 50},
            time_range=_TIME_RANGE,
            mode="screening",
            selected_indicators={"air.no2.score", "air.so2.score", "air.co.score"},
            ee_client=None,
        )

        # Every pollutant's nine canonical keys are present.
        for pol in ("no2", "so2", "co"):
            for measurement in _MEASUREMENT_KEYS_FULL:
                assert f"air.{pol}.{measurement}" in result, f"missing air.{pol}.{measurement}"

        # All five pillar aggregates present.
        for agg_id in (
            "air.pollution_proxy_score",
            "air.spatiotemporal_anomaly_score",
            "air.trend_score",
            "air.attribution_confidence_score",
            "air.audit_followup_priority",
        ):
            assert agg_id in result

        # Sub-aggregates: those whose deps are present should be non-None.
        # no2+co both present → industrial_combustion_proxy non-None.
        assert result["air.industrial_combustion_proxy"] is not None
        # pm25 not selected → pm_or_aerosol uses fallback path; aai also not
        # selected, so fallback returns None.
        assert result["air.pm_or_aerosol"] is None

        # No failures.
        assert "_failures" not in result

    def test_single_pollutant_failure_degrades_gracefully(self, monkeypatch) -> None:
        def fake_compute(aoi, pollutant, time_range, mode, ee_client):
            if pollutant == "so2":
                raise IndicatorComputeError(
                    indicator_id="air.so2",
                    reason="background ring has no valid pixels",
                )
            return _fake_snapshot(pollutant)
        monkeypatch.setattr("engine.air.compute_pollutant_snapshot", fake_compute)

        result = run_pillar(
            aoi={"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 50},
            time_range=_TIME_RANGE,
            mode="screening",
            selected_indicators={"air.no2.score", "air.so2.score", "air.co.score"},
            ee_client=None,
        )

        # The failing pollutant's IDs are all None.
        for measurement in _MEASUREMENT_KEYS_FULL:
            assert result[f"air.so2.{measurement}"] is None

        # The other two computed normally.
        assert result["air.no2.score"] == 0.5
        assert result["air.co.score"] == 0.5

        # _failures has the right entry.
        assert "_failures" in result
        assert len(result["_failures"]) == 1
        failure = result["_failures"][0]
        assert failure["pollutant"] == "so2"
        assert failure["indicator_id"] == "air.so2"
        assert "no valid pixels" in failure["reason"]

        # Pillar aggregates still computable from the two surviving pollutants.
        assert result["air.audit_followup_priority"] is not None

    def test_all_pollutants_failing_raises_pillar_compute_error(self, monkeypatch) -> None:
        def fake_compute(aoi, pollutant, time_range, mode, ee_client):
            raise IndicatorComputeError(
                indicator_id=f"air.{pollutant}",
                reason="no valid pixels",
            )
        monkeypatch.setattr("engine.air.compute_pollutant_snapshot", fake_compute)

        with pytest.raises(PillarComputeError) as excinfo:
            run_pillar(
                aoi={"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 50},
                time_range=_TIME_RANGE,
                mode="screening",
                selected_indicators={"air.no2.score", "air.so2.score", "air.co.score"},
                ee_client=None,
            )

        err = excinfo.value
        assert err.pillar == "air"
        # 3 pollutants × 9 measurements = 27 affected IDs.
        assert len(err.indicator_ids) == 3 * len(_MEASUREMENT_KEYS_FULL)
        # Spot-check that every expected ID is in the affected list.
        assert "air.no2.score" in err.indicator_ids
        assert "air.so2.confidence" in err.indicator_ids
        assert "air.co.trend_p" in err.indicator_ids
