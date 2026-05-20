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
    GHG_FOLLOWUP_WEIGHTS,
    NATURE_FOLLOWUP_WEIGHTS,
    VEGETATION_CONDITION_WEIGHTS,
)
from engine.ghg import compute_ghg_audit_followup_priority
from engine.nature import (
    compute_nature_followup_priority,
    compute_vegetation_condition,
)


# ---------------------------------------------------------------------------
# Pillar configs — (compute_fn, weights_dict, payload_keys, out_key)
# ---------------------------------------------------------------------------

_AIR_CONFIG = (
    compute_air_audit_followup_priority,
    AIR_FOLLOWUP_WEIGHTS,
    {
        "proxy":      "air.pollution_proxy_score",
        "anomaly":    "air.spatiotemporal_anomaly_score",
        "trend":      "air.trend_score",
        "confidence": "air.attribution_confidence_score",
    },
    "air.audit_followup_priority",
)

_GHG_CONFIG = (
    compute_ghg_audit_followup_priority,
    GHG_FOLLOWUP_WEIGHTS,
    {
        "core_support": "ghg.core_audit_support",
        "anomaly":      "ghg.spatiotemporal_anomaly",
        "trend":        "ghg.trend",
        "quality":      "ghg.data_quality_attribution",
    },
    "ghg.audit_followup_priority",
)

_NATURE_CONFIG = (
    compute_nature_followup_priority,
    NATURE_FOLLOWUP_WEIGHTS,
    {
        "biodiversity_exposure": "nature.biodiversity_exposure",
        "habitat_conversion":    "nature.habitat.conversion_score",
        "vegetation_condition":  "nature.vegetation_condition",
        "quality_attribution":   "nature.quality_attribution",
    },
    "nature.followup_priority",
)


@pytest.fixture(params=[_AIR_CONFIG, _GHG_CONFIG, _NATURE_CONFIG],
                ids=["air", "ghg", "nature"])
def pillar(request):
    """Parametrise tests across all three pillars."""
    compute_fn, weights, key_map, out_key = request.param
    return {
        "compute_fn": compute_fn,
        "weights":    weights,
        "key_map":    key_map,
        "out_key":    out_key,
    }


def _build_payload(key_map: dict, values: dict) -> dict:
    """Map term-name → value into the canonical payload-key shape."""
    return {key_map[term]: v for term, v in values.items()}


def _call(pillar, payload: dict):
    """Invoke the parametrised pillar's compute function."""
    fn = pillar["compute_fn"]
    # Nature's signature is (payload, mode); Air/GHG also accept mode.
    return fn(payload, mode="screening")


# ---------------------------------------------------------------------------
# Per-pillar canaries
# ---------------------------------------------------------------------------

class TestStrictNonePropagation:
    def test_all_populated_returns_weighted_sum(self, pillar):
        """Every sub-aggregate present → priority is the weighted sum."""
        values = {term: 0.5 for term in pillar["weights"]}
        payload = _build_payload(pillar["key_map"], values)
        out = _call(pillar, payload)
        expected = sum(pillar["weights"][term] * 0.5 for term in pillar["weights"])
        assert out[pillar["out_key"]] == pytest.approx(expected)

    def test_one_subaggregate_none_returns_none(self, pillar):
        """M-FOLLOWUP-FALLBACK: any single None → priority is None.
        This is the explicit regression for Rio's misleading 0.858."""
        # Drop the LAST weight term so the test exercises mid-loop None
        # rather than just first-term-None.
        terms = list(pillar["weights"])
        values = {term: 0.5 for term in terms[:-1]}
        values[terms[-1]] = None
        payload = _build_payload(pillar["key_map"], values)
        out = _call(pillar, payload)
        assert out[pillar["out_key"]] is None

    def test_all_subaggregates_none_returns_none(self, pillar):
        out = _call(pillar, payload={})
        assert out[pillar["out_key"]] is None

    def test_all_zeros_returns_zero(self, pillar):
        """Known-zero case (e.g. Air trend = 0.0 in screening mode):
        all sub-aggregates 0.0 → priority is 0.0, NOT None. Distinct
        from "all None" which is the real-failure case.
        """
        values = {term: 0.0 for term in pillar["weights"]}
        payload = _build_payload(pillar["key_map"], values)
        out = _call(pillar, payload)
        assert out[pillar["out_key"]] == 0.0

    def test_mixed_zero_and_real_returns_weighted_sum(self, pillar):
        """Mixed: some real values, some 0.0 (known-zero). All terms
        present (no Nones) → the priority computes normally, including
        zero contributions where applicable. This is the standard
        screening-mode shape with Air/GHG trend = 0.0.
        """
        terms = list(pillar["weights"])
        values = {term: 0.5 for term in terms}
        values[terms[0]] = 0.0  # one known-zero
        payload = _build_payload(pillar["key_map"], values)
        out = _call(pillar, payload)
        expected = (
            pillar["weights"][terms[0]] * 0.0
            + sum(pillar["weights"][term] * 0.5 for term in terms[1:])
        )
        assert out[pillar["out_key"]] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Vegetation condition known-zero substitution (Nature only)
# ---------------------------------------------------------------------------

class TestVegetationConditionKnownZero:
    def test_negative_trend_none_substituted_with_zero(self):
        """M-FOLLOWUP-FALLBACK: ``nature.ndvi.negative_trend`` is always
        None in v1 (trend.py / M-TREND-ENGINE not built). The aggregate
        must still compute by substituting 0.0 for that term — otherwise
        ``nature.vegetation_condition`` would be perpetually None and
        the pillar priority would always be None under strict-None.
        """
        payload = {
            "nature.ndvi.inverted_anomaly": 0.4,
            "nature.ndvi.negative_trend":   None,  # always None in v1
            "nature.low_ndvi.pct_norm":     0.2,
            "nature.recovery.score":        0.1,
        }
        out = compute_vegetation_condition(payload)
        # The 0.25 weight on negative_trend × 0.0 contributes nothing,
        # but the other three terms feed normally — aggregate is not None.
        assert out["nature.vegetation_condition"] is not None
        expected_raw = (
            VEGETATION_CONDITION_WEIGHTS["nature.ndvi.inverted_anomaly"] * 0.4
            + VEGETATION_CONDITION_WEIGHTS["nature.ndvi.negative_trend"]   * 0.0
            + VEGETATION_CONDITION_WEIGHTS["nature.low_ndvi.pct_norm"]     * 0.2
            + VEGETATION_CONDITION_WEIGHTS["nature.recovery.score"]        * 0.1
        )
        # The function clamps to [0, 1] — for these inputs the raw is
        # already in range, so the result equals the raw weighted sum.
        assert out["nature.vegetation_condition"] == pytest.approx(
            max(0.0, min(1.0, expected_raw)),
        )

    def test_real_upstream_failure_still_returns_none(self):
        """A genuinely missing dependency (e.g. NDVI indicator skipped
        on this AOI → ``nature.ndvi.inverted_anomaly`` is None) still
        propagates strict-null. The known-zero substitution only covers
        the ``negative_trend`` term that's documented v1 gap.
        """
        payload = {
            "nature.ndvi.inverted_anomaly": None,  # real upstream failure
            "nature.ndvi.negative_trend":   None,
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
            "air.attribution_confidence_score": 0.7,
            "ghg.data_quality_attribution":      None,
            "nature.quality_attribution":        0.8,
        })
        run._compute_composite_confidence()
        assert run.payload["composite.confidence"] is None

    def test_composite_confidence_min_when_all_three_populated(self):
        run = self._stub_run({
            "air.attribution_confidence_score": 0.7,
            "ghg.data_quality_attribution":      0.6,
            "nature.quality_attribution":        0.8,
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
