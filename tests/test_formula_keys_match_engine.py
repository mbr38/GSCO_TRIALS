"""Canary tests for c5_drilldown formula keys (M-NATURE-KEYS).

Asserts that every ``payload_key`` declared in
``ui.components.c5_drilldown``'s pillar formulas is one the engine
actually emits. Catches both directions of drift:

1. "UI added a formula term but engine doesn't emit that key yet" —
   the bug this milestone was built to fix.
2. "Engine renamed an aggregate key but the UI's formula still points
   at the old name" — same blast radius, different cause.

The check is synthetic — every aggregate ``compute_*`` function in
``engine.{air,ghg,nature}`` takes a payload dict and returns a
single-key dict. Calling each with ``{}`` harvests the emitted key
without touching Earth Engine.
"""

# M-NATURE-KEYS
from __future__ import annotations

import pytest

from engine.air import (
    compute_air_pollution_proxy_score,
    compute_attribution_confidence_score,
    compute_spatiotemporal_anomaly_score,
)
from engine.ghg import (
    compute_core_ghg_audit_support,
    compute_ghg_data_quality_attribution,
    compute_ghg_spatiotemporal_anomaly,
)
from engine.nature import (
    compute_biodiversity_exposure,
    compute_habitat_conversion_score,
    compute_nature_measurement_quality,  # M-ATTRIB-A1 (AT13)
    compute_vegetation_condition,
)
from ui.components.c5_drilldown import (
    _AIR_FORMULA,
    _GHG_FORMULA,
    _NATURE_FORMULA,
)


# ---------------------------------------------------------------------------
# Harvest helpers — call each aggregate fn with {} to capture its key.
# ---------------------------------------------------------------------------

def _harvest_keys(callsites) -> set[str]:
    """Return the union of keys each call-site emits.

    Each entry is a zero-arg lambda that invokes one aggregate ``compute_*``
    function with empty payload + whatever extra args its signature
    requires (``selected`` for Air/GHG; ``mode`` for the trend reducers).
    Passing an empty payload exercises the strict-null branch but the
    canonical key is still emitted (with value ``None``) — that's all
    this canary cares about.
    """
    keys: set[str] = set()
    for fn in callsites:
        result = fn()
        keys.update(result.keys())
    return keys


# M-TREND-A1 (TR10): the aggregate trend reducers (compute_trend_score /
# compute_ghg_trend) are gone — trend is a per-indicator drill-down only.
_AIR_AGGREGATE_KEYS: set[str] = _harvest_keys([
    lambda: compute_air_pollution_proxy_score({}, set()),
    lambda: compute_spatiotemporal_anomaly_score({}, set()),
    lambda: compute_attribution_confidence_score({}, set()),
])
_GHG_AGGREGATE_KEYS: set[str] = _harvest_keys([
    lambda: compute_core_ghg_audit_support({}, set()),
    lambda: compute_ghg_spatiotemporal_anomaly({}, set()),
    lambda: compute_ghg_data_quality_attribution({}),
])
_NATURE_AGGREGATE_KEYS: set[str] = _harvest_keys([
    lambda: compute_biodiversity_exposure({}),
    lambda: compute_habitat_conversion_score({}),
    lambda: compute_vegetation_condition({}),
    lambda: compute_nature_measurement_quality({}),
])


# ---------------------------------------------------------------------------
# Per-pillar canary
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("term", _AIR_FORMULA, ids=lambda t: t.payload_key)
def test_air_formula_payload_keys_emitted_by_engine(term) -> None:
    """Every Air formula term points at a key ``engine.air`` emits."""
    assert term.payload_key in _AIR_AGGREGATE_KEYS, (
        f"_AIR_FORMULA term {term.display_name!r} reads "
        f"{term.payload_key!r}, which engine.air does not emit. "
        f"Engine emits: {sorted(_AIR_AGGREGATE_KEYS)}"
    )


@pytest.mark.parametrize("term", _GHG_FORMULA, ids=lambda t: t.payload_key)
def test_ghg_formula_payload_keys_emitted_by_engine(term) -> None:
    """Every GHG formula term points at a key ``engine.ghg`` emits."""
    assert term.payload_key in _GHG_AGGREGATE_KEYS, (
        f"_GHG_FORMULA term {term.display_name!r} reads "
        f"{term.payload_key!r}, which engine.ghg does not emit. "
        f"Engine emits: {sorted(_GHG_AGGREGATE_KEYS)}"
    )


@pytest.mark.parametrize("term", _NATURE_FORMULA, ids=lambda t: t.payload_key)
def test_nature_formula_payload_keys_emitted_by_engine(term) -> None:
    """Every Nature formula term points at a key ``engine.nature`` emits.

    This is the bug M-NATURE-KEYS was built to prevent: an earlier
    iteration of the Nature formula pointed at keys the engine didn't
    emit, surfacing as "—" rows that looked like a broken UI when the
    real problem was a UI/engine mismatch.
    """
    assert term.payload_key in _NATURE_AGGREGATE_KEYS, (
        f"_NATURE_FORMULA term {term.display_name!r} reads "
        f"{term.payload_key!r}, which engine.nature does not emit. "
        f"Engine emits: {sorted(_NATURE_AGGREGATE_KEYS)}"
    )


# ---------------------------------------------------------------------------
# Cardinality lock — per-pillar term counts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name,formula,expected",
    [
        # M-TREND-A1 (TR10): Air/GHG drop the aggregate trend term → 3 terms
        # each (proxy/anomaly/quality, core_support/anomaly/quality). Nature
        # never had a trend term and keeps its 4 (IC §3.3).
        ("_AIR_FORMULA",    _AIR_FORMULA,    3),
        ("_GHG_FORMULA",    _GHG_FORMULA,    3),
        ("_NATURE_FORMULA", _NATURE_FORMULA, 4),
    ],
)
def test_formula_has_expected_term_count(name: str, formula: tuple, expected: int) -> None:
    """Pin the per-pillar follow-up cardinality so an accidental term drop
    or addition fails loudly (Indicators_Computation_v4 §1.3 / §2.3 / §3.3,
    as amended by M-TREND-A1 TR10)."""
    assert len(formula) == expected, (
        f"{name} has {len(formula)} terms, expected {expected}"
    )
