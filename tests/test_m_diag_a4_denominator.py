"""M-DIAG-A4 — climatology-baseline temporal denominator.

Covers:
- the pure window-math helper (`_climatology_window`, DGC1: `max(90,
  screening_window_length)` trailing) at 30/90/180-day cases + the non-ISO guard;
- the pure temporal-std helper (`_temporal_std`, population σ, < 2-day floor);
- the `six_step` override wiring — `bg_std` is replaced by the temporal σ and
  the replacement flows GLOBALLY into the aggregate z AND the composite severity
  score (`to_score`), with the `clim_denominator_extra` provenance block;
- the graceful-degrade path (EE failure → spatial std kept, applied=False);
- the saved-trend `methodology_version` field + stale-data banner predicate (DGC5).

These are synthetic / stub tests — no Earth Engine. The live behaviour is
re-validated in Phase 2 (AAI + O3 control re-run) and Phase 3 (seed regen).
"""

from __future__ import annotations

import pytest

import engine.core.repeatable_core as rc
from engine.constants import (
    CLIMATOLOGY_BASELINE_SPARSE_MIN_VALID_DAYS,
    ENGINE_METHODOLOGY_VERSION,
    NORMALISATION_K,
)
from ui.components.trend_record import (
    STALE_TREND_BANNER,
    is_stale_trend_record,
    make_trend_entry,
)


# ---------------------------------------------------------------------------
# Pure helper — trailing climatology window (DGC1)
# ---------------------------------------------------------------------------

class TestClimatologyWindow:
    def test_30_day_screening_floors_to_90(self) -> None:
        clim_start, clim_end, baseline_days = rc._climatology_window(
            ("2023-04-01", "2023-05-01"),
        )
        assert baseline_days == 90               # max(90, 30) → floor
        assert clim_end == "2023-04-01"          # trailing: ends at screening start
        assert clim_start == "2023-01-01"        # exactly 90 days before

    def test_90_day_screening_matches_floor(self) -> None:
        _start, _end, baseline_days = rc._climatology_window(
            ("2023-01-01", "2023-04-01"),
        )
        assert baseline_days == 90               # 90-day window == floor

    def test_180_day_screening_grows_baseline(self) -> None:
        _start, _end, baseline_days = rc._climatology_window(
            ("2023-01-01", "2023-07-01"),
        )
        assert baseline_days > 90                # baseline grows with screening
        assert baseline_days == 181              # inclusive day count

    def test_non_iso_range_returns_none(self) -> None:
        # The ("static", "static") reference-data sentinel never reaches the
        # denominator via six_step, but the helper stays total.
        assert rc._climatology_window(("static", "static")) is None


# ---------------------------------------------------------------------------
# Pure helper — temporal std
# ---------------------------------------------------------------------------

class TestTemporalStd:
    def test_population_std_matches_ee_reducer(self) -> None:
        std, n = rc._temporal_std([1.0, 2.0, 3.0, 4.0])
        assert n == 4
        # population (ddof=0) std, matching ee.Reducer.stdDev()
        assert std == pytest.approx(1.1180339887498949)

    def test_uniform_series_gives_zero_std(self) -> None:
        # A temporally-flat site → σ 0 → downstream bg_std<=0 guards strict-None
        # z/score, which is the correct "uniform site" behaviour.
        std, n = rc._temporal_std([3.0, 3.0, 3.0])
        assert std == 0.0 and n == 3

    def test_single_day_uncomputable(self) -> None:
        assert rc._temporal_std([5.0]) == (None, 1)

    def test_empty_series_uncomputable(self) -> None:
        assert rc._temporal_std([]) == (None, 0)


# ---------------------------------------------------------------------------
# six_step override wiring — global replacement reaches z AND to_score
# ---------------------------------------------------------------------------

def _run_six_step(monkeypatch, clim_return, *, site=10.0, bg_median=5.0,
                  spatial_std=0.1, indicator_id="air.no2"):
    """Run six_step with all EE-touching internals stubbed and a controllable
    `_climatology_bg_std` return. Returns the result dict."""

    class _SpyIc:
        def filterDate(self, *_a):  return self
        def filterBounds(self, *_a): return self

    class _Env:
        def bounds(self): return self

    monkeypatch.setattr(rc, "site_buffer", lambda *_a, **_k: _Env())
    monkeypatch.setattr(rc, "_site_value_reduction", lambda *_a, **_k: object())
    monkeypatch.setattr(rc, "_background_value_reduction", lambda *_a, **_k: object())

    class _FakeDict:
        def __init__(self, _m): pass
        def getInfo(self): return {"site": {}, "background": {}}

    monkeypatch.setattr(rc.ee, "Dictionary", _FakeDict)
    monkeypatch.setattr(
        rc, "site_value",
        lambda aoi, ic, band, scale, _precomputed=None: site,
    )
    monkeypatch.setattr(
        rc, "background_value",
        lambda aoi, ic, band, seasonal, scale, *, ring,
               _precomputed=None: (bg_median, spatial_std),
    )
    monkeypatch.setattr(
        rc, "background_ring",
        lambda centre, radius_km: {
            "geometry": object(), "mask": None, "land_fraction": 1.0,
            "land_mask_applied": True, "land_mask_asset": "MODIS/006/MOD44W",
        },
    )
    monkeypatch.setattr(
        rc, "_server_side_hf",
        lambda *a, **kw: rc.ServerSideHfResult(5, 0.3, 100),
    )
    monkeypatch.setattr(rc, "_climatology_bg_std", lambda *a, **kw: clim_return)
    monkeypatch.setattr(
        rc, "_confidence_terms_from_six_step_state",
        lambda **kw: {"qa": 0.9, "n_valid": 1.0,
                      "anomaly_strength": 0.0, "spatial_context": 1.0},
    )
    monkeypatch.setattr(rc, "compute_indicator_confidence", lambda **kw: 0.8)

    aoi = {"centre": {"lat": -15.78, "lon": -47.80}, "radius_km": 43.1}
    return rc.six_step(
        aoi=aoi, image_collection=_SpyIc(), band="b",
        time_range=("2026-01-01", "2026-04-01"), ee_client=None,
        indicator_id=indicator_id,
    )


class TestSixStepDenominatorOverride:
    def test_temporal_sigma_replaces_spatial_in_aggregate_z(self, monkeypatch) -> None:
        # temporal σ = 2.0 → z = (10 − 5) / 2.0 = 2.5, NOT (10−5)/0.1 = 50.
        result = _run_six_step(monkeypatch, (2.0, 40, 90))
        assert result["z"] == pytest.approx(2.5)

    def test_global_replacement_reaches_composite_score(self, monkeypatch) -> None:
        # DGC11 / operator "global" decision: to_score(severity) consumes the
        # SAME replaced bg_std. With spatial 0.1 the score saturates to 1.0;
        # with temporal 2.0 it is raw / (k · 2.0) — strictly below 1.0. The
        # contrast proves severity moves, not just the per-day hot flags.
        temporal = _run_six_step(monkeypatch, (2.0, 40, 90))
        spatial = _run_six_step(monkeypatch, (None, 0, 90))  # keeps spatial 0.1
        assert spatial["score"] == pytest.approx(1.0)
        expected = 5.0 / (NORMALISATION_K * 2.0)
        assert temporal["score"] == pytest.approx(min(1.0, expected))
        assert temporal["score"] < spatial["score"]

    def test_provenance_extra_applied(self, monkeypatch) -> None:
        result = _run_six_step(monkeypatch, (2.0, 40, 90))
        extra = result["clim_denominator_extra"]
        assert extra["clim_baseline_applied"] is True
        assert extra["clim_baseline_days"] == 90
        assert extra["clim_baseline_valid_days"] == 40
        assert extra["clim_baseline_sparse"] is False
        assert extra["bg_std_temporal"] == 2.0
        assert extra["bg_std_spatial"] == 0.1

    def test_sparse_flag_fires_below_threshold(self, monkeypatch) -> None:
        n_days = CLIMATOLOGY_BASELINE_SPARSE_MIN_VALID_DAYS - 1
        result = _run_six_step(monkeypatch, (2.0, n_days, 90))
        assert result["clim_denominator_extra"]["clim_baseline_sparse"] is True

    def test_graceful_degrade_keeps_spatial_std(self, monkeypatch) -> None:
        # _climatology_bg_std returns (None, 0, days) on EE failure → spatial
        # std retained, applied=False (loud fallback, not silent default).
        result = _run_six_step(monkeypatch, (None, 0, 90))
        extra = result["clim_denominator_extra"]
        assert extra["clim_baseline_applied"] is False
        assert extra["bg_std_temporal"] is None
        assert extra["bg_std_spatial"] == 0.1
        # z falls back to the spatial denominator: (10 − 5) / 0.1 = 50.
        assert result["z"] == pytest.approx(50.0)

    def test_zero_temporal_sigma_strict_nones_z(self, monkeypatch) -> None:
        # A computed σ of 0 IS applied (temporally-uniform site); the existing
        # bg_std<=0 guard then strict-Nones z rather than reverting to spatial.
        result = _run_six_step(monkeypatch, (0.0, 40, 90))
        assert result["z"] is None
        assert result["clim_denominator_extra"]["clim_baseline_applied"] is True

    def test_viirs_excluded_keeps_spatial_denominator(self, monkeypatch) -> None:
        # Operator decision (Phase 3 / E2): VIIRS is excluded from the temporal
        # swap (its temporal σ collapses at stably-lit sites). Even if the clim
        # sample WOULD return a value, VIIRS keeps the spatial std and is flagged
        # excluded. z falls back to spatial: (10 − 5) / 0.1 = 50.
        result = _run_six_step(monkeypatch, (2.0, 40, 90), indicator_id="ghg.viirs")
        extra = result["clim_denominator_extra"]
        assert extra["clim_baseline_excluded"] is True
        assert extra["clim_baseline_applied"] is False
        assert extra["bg_std_temporal"] is None       # EE sample skipped entirely
        assert extra["bg_std_spatial"] == 0.1
        assert result["z"] == pytest.approx(50.0)

    def test_non_excluded_indicator_not_flagged_excluded(self, monkeypatch) -> None:
        result = _run_six_step(monkeypatch, (2.0, 40, 90), indicator_id="air.no2")
        assert result["clim_denominator_extra"]["clim_baseline_excluded"] is False


class TestClimatologyBgStdGracefulDegrade:
    def test_ee_failure_warns_and_returns_none(self, monkeypatch) -> None:
        # _server_side_day_means raising → caught, RuntimeWarning, None σ.
        class _Ic:
            def filterDate(self, *_a): return self
            def filterBounds(self, *_a): return self

        class _Env:
            def bounds(self): return self

        import engine.core.trend as trend_mod
        monkeypatch.setattr(
            trend_mod, "_server_side_day_means",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("EE boom")),
        )
        with pytest.warns(RuntimeWarning, match="degraded to spatial std"):
            std, n, baseline_days = rc._climatology_bg_std(
                {"centre": {"lat": 0, "lon": 0}, "radius_km": 10.0},
                _Ic(), _Env(), "b", ("2026-01-01", "2026-04-01"), None,
                indicator_id="air.no2",
            )
        assert std is None and n == 0 and baseline_days == 90


# ---------------------------------------------------------------------------
# DGC5 — saved-trend methodology_version + stale-data banner
# ---------------------------------------------------------------------------

class TestMethodologyVersion:
    def test_new_trend_record_carries_current_version(self) -> None:
        entry = make_trend_entry(
            entry_id="t1", name="n", indicator_id="air.no2",
            display_name="NO₂", screening_setup={}, result={},
            date_saved_iso="2026-05-31T00:00:00",
        )
        assert entry["methodology_version"] == ENGINE_METHODOLOGY_VERSION

    def test_new_record_is_not_stale(self) -> None:
        entry = make_trend_entry(
            entry_id="t1", name="n", indicator_id="air.no2",
            display_name="NO₂", screening_setup={}, result={},
            date_saved_iso="2026-05-31T00:00:00",
        )
        assert is_stale_trend_record(entry) is False

    def test_pre_milestone_record_without_field_is_stale(self) -> None:
        # Backward-compat: a record written before the field existed.
        assert is_stale_trend_record({"type": "trend"}) is True

    def test_older_version_is_stale(self) -> None:
        assert is_stale_trend_record({"methodology_version": 0}) is True

    def test_banner_copy_present(self) -> None:
        assert "re-run" in STALE_TREND_BANNER.lower()
