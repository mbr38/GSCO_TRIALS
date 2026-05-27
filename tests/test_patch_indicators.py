"""Tests for the FB18 patch-on-existing re-screening (M-FALLBACK-A1 §5.3).

`engine.orchestrator.patch_indicators` recomputes only the targeted
indicator(s) with a forced fallback strategy, splices them into a copy of an
existing screening payload, and refreshes the affected pillar's aggregates +
the composite — preserving every other indicator (R7). Pillar snapshots are
stubbed so no Earth Engine is needed.
"""

from __future__ import annotations

import pytest

from engine import air
from engine.ids import PILLAR_AIR, make_id
from engine.orchestrator import (
    compute_composite_overall,
    patch_indicators,
)

_M = ("site", "background", "anomaly", "z", "hf", "trend", "trend_p",
      "confidence", "score")


def _air_snapshot(pol: str, *, score: float, z: float = 2.0, conf: float = 0.5,
                  temporal: bool = True) -> dict:
    """Minimal canonical air snapshot for one pollutant."""
    d: dict = {make_id(PILLAR_AIR, pol, m): None for m in _M}
    d[make_id(PILLAR_AIR, pol, "score")] = score
    d[make_id(PILLAR_AIR, pol, "z")] = z
    d[make_id(PILLAR_AIR, pol, "confidence")] = conf
    d[make_id(PILLAR_AIR, pol, "site")] = 100.0
    d[f"_provenance.air.{pol}"] = {
        "extra": {
            "temporal_fallback_used": temporal,
            "temporal_fallback_strategy": "sppy" if temporal else None,
            "aoi_scale_class": "site",
        }
    }
    return d


def _baseline_payload() -> dict:
    """no2 computed (0.40); so2 failed (all None)."""
    payload: dict = {}
    payload.update(_air_snapshot("no2", score=0.40, temporal=False))
    payload.update({make_id(PILLAR_AIR, "so2", m): None for m in _M})
    payload[f"_provenance.air.so2"] = {"skipped_reason": "no_s5p_pixels", "extra": {}}
    payload["_meta"] = {
        "aoi": {"centre": {"lat": -13.5, "lon": -58.8}, "radius_km": 50},
        "time_range": ["2026-03-01", "2026-05-30"],
        "selected_indicators": ["air.no2.score", "air.so2.score"],
    }
    return payload


_SELECTED = {"air.no2.score", "air.so2.score"}
_AOI = {"centre": {"lat": -13.5, "lon": -58.8}, "radius_km": 50}
_TR = ("2026-03-01", "2026-05-30")


def test_patch_recovers_target_and_preserves_others(monkeypatch) -> None:
    monkeypatch.setattr(
        air, "compute_pollutant_snapshot",
        lambda aoi, name, tr, mode, ee, fallback=None: _air_snapshot("so2", score=0.62),
    )
    baseline = _baseline_payload()
    patched = patch_indicators(
        baseline, aoi=_AOI, indicator_ids={"air.so2"},
        selected_indicators=_SELECTED, time_range=_TR, ee_client=None,
        strategy="sppy",
    )
    # Target recovered.
    assert patched["air.so2.score"] == 0.62
    # Other indicator preserved untouched.
    assert patched["air.no2.score"] == 0.40
    # Provenance fallback flag spliced in.
    assert patched["_provenance.air.so2"]["extra"]["temporal_fallback_used"] is True


def test_patch_refreshes_pillar_aggregate_and_composite(monkeypatch) -> None:
    monkeypatch.setattr(
        air, "compute_pollutant_snapshot",
        lambda aoi, name, tr, mode, ee, fallback=None: _air_snapshot("so2", score=0.62),
    )
    baseline = _baseline_payload()
    # Before: proxy score from no2 only.
    air.recompute_air_aggregates(dict(baseline), _SELECTED, "screening")
    patched = patch_indicators(
        baseline, aoi=_AOI, indicator_ids={"air.so2"},
        selected_indicators=_SELECTED, time_range=_TR, ee_client=None,
    )
    # Aggregate now reflects both no2 and the recovered so2.
    assert patched["air.pollution_proxy_score"] is not None
    # Composite recomputed (None here because ghg/nature priorities absent —
    # the point is the key is present and consistent with strict-None).
    assert "composite.overall_screening" in patched
    assert patched["composite.overall_screening"] == compute_composite_overall(patched)


def test_patch_does_not_mutate_input(monkeypatch) -> None:
    monkeypatch.setattr(
        air, "compute_pollutant_snapshot",
        lambda aoi, name, tr, mode, ee, fallback=None: _air_snapshot("so2", score=0.62),
    )
    baseline = _baseline_payload()
    patch_indicators(
        baseline, aoi=_AOI, indicator_ids={"air.so2"},
        selected_indicators=_SELECTED, time_range=_TR, ee_client=None,
    )
    # Original still shows the failure.
    assert baseline["air.so2.score"] is None


def test_patch_failed_recovery_leaves_indicator_none(monkeypatch) -> None:
    from engine.exceptions import SiteBufferNoDataError

    def _still_empty(aoi, name, tr, mode, ee, fallback=None):
        raise SiteBufferNoDataError(indicator_id="air.so2", reason="still no pixels")

    monkeypatch.setattr(air, "compute_pollutant_snapshot", _still_empty)
    baseline = _baseline_payload()
    patched = patch_indicators(
        baseline, aoi=_AOI, indicator_ids={"air.so2"},
        selected_indicators=_SELECTED, time_range=_TR, ee_client=None,
    )
    # SPPY also empty → tile stays failed.
    assert patched["air.so2.score"] is None


def test_patch_non_patchable_indicator_is_noop(monkeypatch) -> None:
    # co2 (ODIAC) isn't a six_step indicator → not patchable; snapshot must
    # never be called, and the payload is returned unchanged (bar composite).
    called = {"n": 0}

    def _should_not_run(*a, **k):
        called["n"] += 1
        raise AssertionError("co2 must not be patched")

    monkeypatch.setattr(air, "compute_pollutant_snapshot", _should_not_run)
    baseline = _baseline_payload()
    patched = patch_indicators(
        baseline, aoi=_AOI, indicator_ids={"ghg.co2"},
        selected_indicators=_SELECTED, time_range=_TR, ee_client=None,
    )
    assert called["n"] == 0
    assert patched["air.no2.score"] == 0.40
