"""Synthetic-payload tests for engine.air (Milestone 3a, single-value indicators).

Tests do not touch Earth Engine. `ee.ImageCollection` is stubbed with a
chain-friendly fake; `engine.air.six_step` is monkey-patched per test.

Real-EE smoke tests live in tests/test_air_integration.py (skipped unless
`RUN_EE_TESTS=1` is set).
"""

from __future__ import annotations

import pytest

from engine.air import (
    AIR_POLLUTANT_CONFIG,
    PollutantConfig,
    apply_aod_qa_mask,
    compute_pollutant_snapshot,
)
from engine.constants import O3_SCORE_CAP
from engine.exceptions import IndicatorComputeError


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
