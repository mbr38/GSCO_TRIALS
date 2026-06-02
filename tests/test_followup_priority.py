"""Tests for the M-FOLLOWUP-FALLBACK strict-None semantics.

Three pillars (Air / GHG / Nature) plus the composite computation in
``engine.orchestrator.ScreeningRun`` all moved from "silent
renormalise over surviving sub-aggregates" to "any None → None". This
file parametrises the strict-None behaviour and the happy-path
regressions across all four computations.

Pure-Python — no EE.
"""

# M-FOLLOWUP-FALLBACK
from __future__ import annotations

import pytest

from engine.air import compute_air_audit_followup_priority
from engine.constants import (
    AIR_FOLLOWUP_WEIGHTS,
    AIR_SEVERITY_CORE_WEIGHTS,
    FOLLOWUP_QUALITY_WEIGHT,
    GHG_FOLLOWUP_WEIGHTS,
    NATURE_FOLLOWUP_WEIGHTS,
    NATURE_SEVERITY_CORE_WEIGHTS,
    VEGETATION_CONDITION_WEIGHTS,
)
from engine.ghg import compute_ghg_audit_followup_priority
from engine.nature import (
    compute_nature_followup_priority,
    compute_vegetation_condition,
)


# ---------------------------------------------------------------------------
# M-WEIGHTS-HARMONISE-A1 — every pillar follow-up is now the uniform two-level
# form  0.80·severity_core + 0.20·measurement_quality.  The strict-None /
# happy-path canaries below are expressed via each pillar's EFFECTIVE per-leaf
# weights (severity-core weight × the in-core weight, plus the shared 0.20 on
# the quality leaf). Each effective map sums to 1.0. Air and Nature compute the
# core from leaf inputs inside the follow-up fn; GHG's core is the already-
# aggregated `ghg.core_audit_support`, so it has a single core leaf.
# ---------------------------------------------------------------------------

_SC = AIR_FOLLOWUP_WEIGHTS["severity_core"]   # 0.80, shared across pillars
_Q = FOLLOWUP_QUALITY_WEIGHT                   # 0.20, shared across pillars

_AIR_EFF = {
    "air.pollution_proxy_score":        _SC * AIR_SEVERITY_CORE_WEIGHTS["proxy"],
    "air.spatiotemporal_anomaly_score": _SC * AIR_SEVERITY_CORE_WEIGHTS["anomaly"],
    "air.measurement_quality_score":    _Q,   # M-ATTRIB-A1 (AT16)
}
_GHG_EFF = {
    "ghg.core_audit_support":  _SC,           # GHG core is pre-aggregated
    "ghg.measurement_quality": _Q,            # M-WEIGHTS-HARMONISE-A1
}
_NATURE_EFF = {
    "nature.biodiversity_exposure":    _SC * NATURE_SEVERITY_CORE_WEIGHTS["biodiversity_exposure"],
    "nature.habitat.conversion_score": _SC * NATURE_SEVERITY_CORE_WEIGHTS["habitat_conversion"],
    "nature.vegetation_condition":     _SC * NATURE_SEVERITY_CORE_WEIGHTS["vegetation_condition"],
    "nature.measurement_quality":      _Q,    # M-ATTRIB-A1 (AT13)
}

_AIR_CONFIG = (compute_air_audit_followup_priority, _AIR_EFF, "air.audit_followup_priority")
_GHG_CONFIG = (compute_ghg_audit_followup_priority, _GHG_EFF, "ghg.audit_followup_priority")
_NATURE_CONFIG = (compute_nature_followup_priority, _NATURE_EFF, "nature.followup_priority")


@pytest.fixture(params=[_AIR_CONFIG, _GHG_CONFIG, _NATURE_CONFIG],
                ids=["air", "ghg", "nature"])
def pillar(request):
    """Parametrise tests across all three pillars."""
    compute_fn, eff, out_key = request.param
    return {"compute_fn": compute_fn, "eff": eff, "out_key": out_key}


def _call(pillar, payload: dict):
    """Invoke the parametrised pillar's compute function."""
    return pillar["compute_fn"](payload, mode="screening")


# ---------------------------------------------------------------------------
# Per-pillar canaries
# ---------------------------------------------------------------------------

class TestStrictNonePropagation:
    def test_all_populated_returns_weighted_sum(self, pillar):
        """Every leaf input present → priority is the effective-weighted sum."""
        payload = {k: 0.5 for k in pillar["eff"]}
        out = _call(pillar, payload)
        expected = sum(w * 0.5 for w in pillar["eff"].values())
        assert out[pillar["out_key"]] == pytest.approx(expected)

    def test_one_subaggregate_none_returns_none(self, pillar):
        """M-FOLLOWUP-FALLBACK: any single None leaf → priority is None
        (a None core leaf collapses the severity core; a None quality leaf
        collapses the follow-up). Regression for Rio's misleading 0.858."""
        keys = list(pillar["eff"])
        payload = {k: 0.5 for k in keys[:-1]}
        payload[keys[-1]] = None        # mid-loop / last-term None
        out = _call(pillar, payload)
        assert out[pillar["out_key"]] is None

    def test_all_subaggregates_none_returns_none(self, pillar):
        out = _call(pillar, payload={})
        assert out[pillar["out_key"]] is None

    def test_all_zeros_returns_zero(self, pillar):
        """All leaves 0.0 → priority is 0.0, NOT None. Distinct from
        "all None" which is the real-failure case."""
        payload = {k: 0.0 for k in pillar["eff"]}
        out = _call(pillar, payload)
        assert out[pillar["out_key"]] == 0.0

    def test_mixed_zero_and_real_returns_weighted_sum(self, pillar):
        """Mixed real + known-zero leaves (no Nones) → computes normally."""
        keys = list(pillar["eff"])
        payload = {k: 0.5 for k in keys}
        payload[keys[0]] = 0.0          # one known-zero
        out = _call(pillar, payload)
        expected = (
            pillar["eff"][keys[0]] * 0.0
            + sum(pillar["eff"][k] * 0.5 for k in keys[1:])
        )
        assert out[pillar["out_key"]] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# M-WEIGHTS-HARMONISE-A1 invariant — the uniform two-level shape.
# ---------------------------------------------------------------------------

class TestHarmonisationInvariant:
    @pytest.mark.parametrize(
        "followup_weights",
        [AIR_FOLLOWUP_WEIGHTS, GHG_FOLLOWUP_WEIGHTS, NATURE_FOLLOWUP_WEIGHTS],
        ids=["air", "ghg", "nature"],
    )
    def test_quality_weight_is_uniform_0_20(self, followup_weights):
        """w_q = 0.20 shared by intent across all three pillars; the severity
        portion (key `severity_core` for Air/Nature, `core_support` for GHG)
        takes the remaining 0.80; the dict sums to 1.0."""
        assert followup_weights["quality"] == pytest.approx(0.20)
        severity_portion = sum(
            v for k, v in followup_weights.items() if k != "quality"
        )
        assert severity_portion == pytest.approx(0.80)
        assert sum(followup_weights.values()) == pytest.approx(1.0)

    @pytest.mark.parametrize(
        "core_weights",
        [AIR_SEVERITY_CORE_WEIGHTS, NATURE_SEVERITY_CORE_WEIGHTS],
        ids=["air", "nature"],
    )
    def test_severity_core_weights_sum_to_one(self, core_weights):
        """Each renormalised severity-core dict sums to 1.0 (the 0.80
        follow-up weight then scales it)."""
        assert sum(core_weights.values()) == pytest.approx(1.0)

    def test_no_legacy_spurious_precision_literals(self):
        """The retired spurious-precision FOLLOW-UP splits must not reappear in
        the follow-up weight dicts. (0.375 legitimately survives in the
        severity-core dicts as 0.30/0.80, so those are out of scope here.)"""
        legacy = {0.4375, 0.3750, 0.1875, 0.7273, 0.2727}
        for wd in (AIR_FOLLOWUP_WEIGHTS, GHG_FOLLOWUP_WEIGHTS,
                   NATURE_FOLLOWUP_WEIGHTS):
            for v in wd.values():
                assert round(v, 4) not in legacy


# ---------------------------------------------------------------------------
# Vegetation condition (Nature only). M-TREND-A1 (TR17): the NDVI slope
# term is demoted to drill-down-only — the aggregate is now a strict
# weighted sum of inverted_anomaly + low_ndvi.pct_norm − recovery, with no
# negative_trend term and no zero-substitution.
# ---------------------------------------------------------------------------

class TestVegetationCondition:
    def test_computes_from_three_surviving_terms(self):
        """With the slope term gone, the aggregate is the strict weighted
        sum of the three surviving components."""
        payload = {
            "nature.ndvi.inverted_anomaly": 0.4,
            "nature.low_ndvi.pct_norm":     0.2,
            "nature.recovery.score":        0.1,
        }
        out = compute_vegetation_condition(payload)
        assert out["nature.vegetation_condition"] is not None
        expected_raw = (
            VEGETATION_CONDITION_WEIGHTS["nature.ndvi.inverted_anomaly"] * 0.4
            + VEGETATION_CONDITION_WEIGHTS["nature.low_ndvi.pct_norm"]     * 0.2
            + VEGETATION_CONDITION_WEIGHTS["nature.recovery.score"]        * 0.1
        )
        assert out["nature.vegetation_condition"] == pytest.approx(
            max(0.0, min(1.0, expected_raw)),
        )

    def test_slope_term_no_longer_in_weights(self):
        """TR17 guard: the demoted slope term is gone from the weights, so
        a stray ``negative_trend`` value in the payload is simply ignored."""
        assert "nature.ndvi.negative_trend" not in VEGETATION_CONDITION_WEIGHTS
        base = compute_vegetation_condition({
            "nature.ndvi.inverted_anomaly": 0.4,
            "nature.low_ndvi.pct_norm":     0.2,
            "nature.recovery.score":        0.1,
        })
        with_stray = compute_vegetation_condition({
            "nature.ndvi.inverted_anomaly": 0.4,
            "nature.ndvi.negative_trend":   0.9,  # ignored
            "nature.low_ndvi.pct_norm":     0.2,
            "nature.recovery.score":        0.1,
        })
        assert base["nature.vegetation_condition"] == pytest.approx(
            with_stray["nature.vegetation_condition"]
        )

    def test_real_upstream_failure_still_returns_none(self):
        """A genuinely missing dependency (e.g. NDVI indicator skipped on
        this AOI → ``nature.ndvi.inverted_anomaly`` is None) still
        propagates strict-null."""
        payload = {
            "nature.ndvi.inverted_anomaly": None,  # real upstream failure
            "nature.low_ndvi.pct_norm":     0.2,
            "nature.recovery.score":        0.1,
        }
        out = compute_vegetation_condition(payload)
        assert out["nature.vegetation_condition"] is None


# ---------------------------------------------------------------------------
# Composite strict-None (orchestrator)
# ---------------------------------------------------------------------------

class TestCompositeStrictNone:
    """The composite computation in ``engine.orchestrator`` mirrors the
    pillar-level fix. Test the protected methods directly with a stub
    instance — keeps the test fast (no full ScreeningRun setup)."""

    def _stub_run(self, payload: dict):
        from engine.orchestrator import ScreeningRun
        run = ScreeningRun.__new__(ScreeningRun)  # bypass __init__
        run.payload = payload
        return run

    def test_composite_priority_is_none_when_any_pillar_none(self):
        run = self._stub_run({
            "air.audit_followup_priority":   0.5,
            "ghg.audit_followup_priority":   0.6,
            "nature.followup_priority":      None,
        })
        run._compute_composite()
        assert run.payload["composite.overall_screening"] is None

    def test_composite_priority_mean_when_all_three_pillars_populated(self):
        run = self._stub_run({
            "air.audit_followup_priority":   0.5,
            "ghg.audit_followup_priority":   0.6,
            "nature.followup_priority":      0.4,
        })
        run._compute_composite()
        assert run.payload["composite.overall_screening"] == pytest.approx(
            (0.5 + 0.6 + 0.4) / 3,
        )

    def test_composite_confidence_is_none_when_any_pillar_none(self):
        run = self._stub_run({
            "air.measurement_quality_score": 0.7,  # M-ATTRIB-A1 (AT16)
            "ghg.measurement_quality":        None,  # M-WEIGHTS-HARMONISE-A1
            "nature.measurement_quality":     0.8,  # M-ATTRIB-A1 (AT13)
        })
        run._compute_composite_confidence()
        assert run.payload["composite.confidence"] is None

    def test_composite_confidence_min_when_all_three_populated(self):
        run = self._stub_run({
            "air.measurement_quality_score": 0.7,  # M-ATTRIB-A1 (AT16)
            "ghg.measurement_quality":        0.6,  # M-WEIGHTS-HARMONISE-A1
            "nature.measurement_quality":     0.8,  # M-ATTRIB-A1 (AT13)
        })
        run._compute_composite_confidence()
        assert run.payload["composite.confidence"] == pytest.approx(0.6)

    def test_composite_priority_none_when_all_three_pillars_none(self):
        run = self._stub_run({
            "air.audit_followup_priority":   None,
            "ghg.audit_followup_priority":   None,
            "nature.followup_priority":      None,
        })
        run._compute_composite()
        assert run.payload["composite.overall_screening"] is None
