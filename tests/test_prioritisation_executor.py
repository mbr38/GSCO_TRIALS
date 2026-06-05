"""Tests for engine.prioritisation_executor (M-P08.1).

Mocks ``ScreeningRun`` via monkeypatching the symbol on the executor
module (which captures the reference at import time). No Earth Engine.
"""

# M-P08.1
from __future__ import annotations

import pytest

from engine import prioritisation_executor
from engine.prioritisation_executor import (
    _classify_per_supplier,
    _has_failures,
    run_batch,
)
from ui.prioritisation_state import (
    PrioritisationState,
    PrioritisationStateKind,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _supplier(i: int) -> dict:
    return {
        "id":     f"s{i}",
        "name":   f"Supplier {i}",
        "lat":    float(i),
        "lon":    float(i),
        "source": "ad_hoc",
    }


def _setup(n: int = 3) -> dict:
    return {
        "suppliers":  [_supplier(i) for i in range(1, n + 1)],
        "radius_km":  5,
        "time_range": ["2026-01-01", "2026-04-01"],
        "indicators": ["air.no2.score", "ghg.ch4.score"],
        "mode":       "prioritisation",
    }


def _success_payload(score: float = 0.5) -> dict:
    """Engine payload with all three pillar priorities + composite set.

    M-E1-INDICATOR-AWARE: also carries the per-indicator score keys
    that match ``_setup()``'s ``indicators`` list, since the classifier
    now keys on those rather than the pillar aggregates.
    """
    return {
        "air.audit_followup_priority": score,
        "ghg.audit_followup_priority": score,
        "nature.followup_priority":    score,
        "composite.overall_screening": score,
        # Per-indicator keys (must match the IDs in _setup()'s
        # ``indicators`` list — see M-E1-INDICATOR-AWARE).
        "air.no2.score":               score,
        "ghg.ch4.score":               score,
    }


class _FakeScreeningRun:
    """Drop-in stand-in for engine.orchestrator.ScreeningRun.

    The class-level ``call_log`` and ``script`` fields are reset per
    test via the ``patched_screening_run`` fixture below.
    """
    call_log: list[dict] = []
    script:   list = []  # one entry per call: payload dict OR Exception

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def run(self) -> dict:
        _FakeScreeningRun.call_log.append(self.kwargs)
        idx = len(_FakeScreeningRun.call_log) - 1
        if idx >= len(_FakeScreeningRun.script):
            return _success_payload()
        item = _FakeScreeningRun.script[idx]
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def patched_screening_run(monkeypatch):
    """Reset the fake's per-test state + install it on the executor."""
    _FakeScreeningRun.call_log = []
    _FakeScreeningRun.script   = []
    monkeypatch.setattr(
        prioritisation_executor, "ScreeningRun", _FakeScreeningRun,
    )
    return _FakeScreeningRun


def _noop_progress(*args, **kwargs):  # pragma: no cover — trivial
    pass


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_happy_path_three_suppliers_all_success(patched_screening_run):
    setup = _setup(3)
    state = PrioritisationState(
        kind=PrioritisationStateKind.S2_RUNNING, setup=setup,
    )
    progress_calls: list[tuple] = []
    run_batch(
        state, setup,
        on_progress=lambda r, done, total: progress_calls.append(
            (r.name, done, total),
        ),
    )
    assert state.kind == PrioritisationStateKind.S3_RESULTS
    assert len(state.supplier_results) == 3
    assert all(r.status == "success" for r in state.supplier_results)
    assert state.completed_count == 3
    assert state.total_count == 3
    # Callback invoked once per supplier with running totals.
    assert progress_calls == [
        ("Supplier 1", 1, 3),
        ("Supplier 2", 2, 3),
        ("Supplier 3", 3, 3),
    ]
    # ScreeningRun called exactly three times.
    assert len(patched_screening_run.call_log) == 3


# ---------------------------------------------------------------------------
# Per-supplier failure
# ---------------------------------------------------------------------------

def test_per_supplier_failure_continues(patched_screening_run):
    """Supplier 2 raises; supplier 3 still runs."""
    setup = _setup(3)
    state = PrioritisationState(
        kind=PrioritisationStateKind.S2_RUNNING, setup=setup,
    )
    patched_screening_run.script = [
        _success_payload(),
        RuntimeError("EE timed out"),
        _success_payload(0.7),
    ]
    run_batch(state, setup, on_progress=_noop_progress)
    assert state.kind == PrioritisationStateKind.S3_RESULTS
    statuses = [r.status for r in state.supplier_results]
    assert statuses == ["success", "failed", "success"]
    failed = state.supplier_results[1]
    assert failed.error == "EE timed out"
    assert failed.result is None
    # All three ScreeningRuns attempted (even though one raised).
    assert len(patched_screening_run.call_log) == 3


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------

def test_cancellation_after_first_supplier(patched_screening_run):
    """Cancel after supplier 1 completes — supplier 2 + 3 marked cancelled."""
    setup = _setup(3)
    state = PrioritisationState(
        kind=PrioritisationStateKind.S2_RUNNING, setup=setup,
    )

    def cancel_after_first(latest, done, total):
        if done == 1:
            state.cancelled = True

    run_batch(state, setup, on_progress=cancel_after_first)
    assert state.kind == PrioritisationStateKind.S3_RESULTS
    statuses = [r.status for r in state.supplier_results]
    assert statuses == ["success", "cancelled", "cancelled"]
    # ScreeningRun only invoked for the first supplier; the remaining
    # two were short-circuited by the cancel check.
    assert len(patched_screening_run.call_log) == 1
    # Cancelled entries carry no result + no error.
    for r in state.supplier_results[1:]:
        assert r.result is None
        assert r.error is None


# ---------------------------------------------------------------------------
# Mixed outcomes — success / partial / failed
# ---------------------------------------------------------------------------

def test_mixed_outcomes_status_per_supplier(patched_screening_run):
    """One success, one partial (real pillar scores but ``_failures``
    populated), one failed (every requested indicator None).

    M-E1-INDICATOR-AWARE: payloads carry the per-indicator keys
    matching ``_setup()``'s indicators list, since the classifier
    now keys on those.
    """
    setup = _setup(3)
    state = PrioritisationState(
        kind=PrioritisationStateKind.S2_RUNNING, setup=setup,
    )
    patched_screening_run.script = [
        _success_payload(),                # success
        {                                  # partial — all requested indicators
                                           # delivered + _failures populated.
            "air.audit_followup_priority": 0.4,
            "ghg.audit_followup_priority": 0.3,
            "nature.followup_priority":    0.5,
            "composite.overall_screening": 0.4,
            "air.no2.score":               0.4,
            "ghg.ch4.score":               0.3,
            "_failures": {"air": [{"indicator_id": "air.so2.score"}]},
        },
        {                                  # failed — every requested indicator None
            "air.audit_followup_priority": None,
            "ghg.audit_followup_priority": None,
            "nature.followup_priority":    None,
            "composite.overall_screening": None,
            "air.no2.score":               None,
            "ghg.ch4.score":               None,
        },
    ]
    run_batch(state, setup, on_progress=_noop_progress)
    assert [r.status for r in state.supplier_results] == [
        "success", "partial", "failed",
    ]


# ---------------------------------------------------------------------------
# Empty supplier list — defensive
# ---------------------------------------------------------------------------

def test_empty_supplier_list_transitions_to_s3_no_calls(patched_screening_run):
    setup = {
        "suppliers":  [],
        "radius_km":  5,
        "time_range": ["2026-01-01", "2026-04-01"],
        "indicators": ["air.no2.score"],
        "mode":       "prioritisation",
    }
    state = PrioritisationState(
        kind=PrioritisationStateKind.S2_RUNNING, setup=setup,
    )
    callbacks: list = []
    run_batch(state, setup, on_progress=lambda *a, **k: callbacks.append(a))
    assert state.kind == PrioritisationStateKind.S3_RESULTS
    assert state.supplier_results == []
    assert callbacks == []
    assert patched_screening_run.call_log == []


# ---------------------------------------------------------------------------
# Pure classifier
# ---------------------------------------------------------------------------

# Parametrised classifier tests. With M-P07-PILLAR-CONSTRAINT the
# composite-driven heuristic doesn't apply (composite is None whenever
# any pillar wasn't selected); status is decided from per-pillar scores
# + the _failures / skipped_reason inspection done by _has_failures.
@pytest.mark.parametrize("payload, expected", [
    # All populated, no failures → success.
    (_success_payload(), "success"),
    # Single-pillar selection (Air-only), no failures → success.
    (
        {
            "air.audit_followup_priority": 0.5,
            "ghg.audit_followup_priority": None,
            "nature.followup_priority":    None,
            "composite.overall_screening": None,
        },
        "success",
    ),
    # Pillar scores OK but _failures non-empty → partial.
    (
        {
            "air.audit_followup_priority": 0.5,
            "ghg.audit_followup_priority": 0.5,
            "nature.followup_priority":    0.5,
            "composite.overall_screening": 0.5,
            "_failures": {"air": [{"indicator_id": "air.no2.score"}]},
        },
        "partial",
    ),
    # Pillar scores OK and a provenance skipped_reason present, but no
    # _failures → success. M-PRIO-STATUS: skipped_reason marks a normal
    # defensive skip, NOT a failure (mirrors ui.page_state.classify_result).
    (
        {
            "air.audit_followup_priority": 0.5,
            "ghg.audit_followup_priority": 0.5,
            "nature.followup_priority":    0.5,
            "composite.overall_screening": 0.5,
            "_provenance.nature.kba": {"skipped_reason": "no_dw_pixels"},
        },
        "success",
    ),
    # All pillars None → failed.
    (
        {
            "air.audit_followup_priority": None,
            "ghg.audit_followup_priority": None,
            "nature.followup_priority":    None,
            "composite.overall_screening": None,
        },
        "failed",
    ),
    # No pillar keys at all → failed (defensive).
    ({}, "failed"),
])
def test_classify_per_supplier(payload, expected):
    assert _classify_per_supplier(payload) == expected


# ---------------------------------------------------------------------------
# M-E1-INDICATOR-AWARE: selection-aware classifier
# ---------------------------------------------------------------------------

class TestClassifyPerSupplierSelectionAware:
    """Pin the post-M-E1-INDICATOR-AWARE behaviour of the executor's
    per-supplier classifier. Selection-aware: 'failed' means every
    requested indicator returned None, not 'every pillar aggregate is
    None'.
    """

    def test_single_indicator_success_is_success(self):
        """A subset run where one selected indicator delivered with no
        failures → success, even when pillar aggregates are None."""
        payload = {
            "nature.kba.proximity_score":  0.24,
            "nature.followup_priority":    None,
            "air.audit_followup_priority": None,
            "ghg.audit_followup_priority": None,
        }
        assert _classify_per_supplier(
            payload, ["nature.kba.proximity_score"],
        ) == "success"

    def test_partial_when_some_selected_indicators_missing(self):
        """3 requested, 2 succeeded → partial."""
        payload = {
            "air.no2.score":              0.4,
            "ghg.ch4.score":              0.5,
            "nature.kba.proximity_score": None,
        }
        selected = [
            "air.no2.score", "ghg.ch4.score", "nature.kba.proximity_score",
        ]
        assert _classify_per_supplier(payload, selected) == "partial"

    def test_failed_when_every_selected_indicator_none(self):
        payload = {
            "air.no2.score":              None,
            "ghg.ch4.score":              None,
            "nature.kba.proximity_score": None,
        }
        selected = [
            "air.no2.score", "ghg.ch4.score", "nature.kba.proximity_score",
        ]
        assert _classify_per_supplier(payload, selected) == "failed"

    def test_partial_when_all_succeed_but_failures_block_populated(self):
        """All requested delivered, but ``_failures`` carries an entry
        for an unselected sibling — still partial."""
        payload = {
            "air.no2.score": 0.4,
            "_failures": {"air": [{"indicator_id": "air.so2.score"}]},
        }
        assert _classify_per_supplier(
            payload, ["air.no2.score"],
        ) == "partial"

    def test_no_selection_falls_back_to_pillar_aggregate_logic(self):
        """Defensive: ``None`` selection → pre-M-E1-INDICATOR-AWARE
        path (the parametrised tests below still cover that)."""
        payload = {"air.audit_followup_priority": 0.5}
        assert _classify_per_supplier(payload, None) == "success"


# _has_failures coverage.
@pytest.mark.parametrize("payload, expected", [
    ({}, False),
    ({"_failures": {}}, False),
    ({"_failures": {"air": []}}, False),
    ({"_failures": {"air": [{"indicator_id": "air.no2.score"}]}}, True),
    # M-PRIO-STATUS: provenance skipped_reason is a normal defensive skip,
    # NOT a failure (mirrors ui.page_state.classify_result, which ignores it).
    (
        {"_provenance.air.no2": {"skipped_reason": "no_s5p_pixels"}},
        False,
    ),
    # Provenance without a skipped_reason key → not a failure.
    ({"_provenance.air.no2": {"data_type": "satellite_observation"}}, False),
    # Mixed: _failures empty (no real failure), one prov skip → not a failure.
    (
        {
            "_failures": {"air": []},
            "_provenance.ghg.ch4": {"skipped_reason": "no_s5p_pixels"},
        },
        False,
    ),
])
def test_has_failures(payload, expected):
    assert _has_failures(payload) is expected


# ---------------------------------------------------------------------------
# ScreeningRun is invoked with the expected per-supplier args
# ---------------------------------------------------------------------------

def test_screening_run_receives_per_supplier_aoi(patched_screening_run):
    """Each ScreeningRun gets that supplier's lat/lon in the AOI and the
    supplier id + name threaded onto centre_metadata."""
    setup = _setup(2)
    state = PrioritisationState(
        kind=PrioritisationStateKind.S2_RUNNING, setup=setup,
    )
    run_batch(state, setup, on_progress=_noop_progress)
    calls = patched_screening_run.call_log
    assert len(calls) == 2
    first = calls[0]
    assert first["aoi"] == {"centre": {"lat": 1.0, "lon": 1.0}, "radius_km": 5}
    assert first["centre_metadata"]["node_id"]   == "s1"
    assert first["centre_metadata"]["node_name"] == "Supplier 1"
    assert "P-08 batch" in first["centre_metadata"]["source"]
    assert first["time_range"] == ("2026-01-01", "2026-04-01")
    assert first["selected_indicators"] == {"air.no2.score", "ghg.ch4.score"}


# ---------------------------------------------------------------------------
# Per-supplier radius override (Regional-analysis region buffers)
# ---------------------------------------------------------------------------

def test_per_supplier_radius_overrides_shared_radius(patched_screening_run):
    """A supplier carrying its own ``radius_km`` (a region's area-matched
    buffer) screens at that radius; suppliers without one fall back to the
    shared page-level radius."""
    setup = {
        "suppliers": [
            {
                "id": "region_A", "name": "Region A", "lat": 1.0, "lon": 1.0,
                "source": "region", "radius_km": 120.0,
            },
            {
                "id": "ad_1", "name": "Ad hoc 1", "lat": 2.0, "lon": 2.0,
                "source": "ad_hoc", "radius_km": None,
            },
        ],
        "radius_km":  5,
        "time_range": ["2026-01-01", "2026-04-01"],
        "indicators": ["air.no2.score"],
        "mode":       "prioritisation",
    }
    state = PrioritisationState(
        kind=PrioritisationStateKind.S2_RUNNING, setup=setup,
    )
    run_batch(state, setup, on_progress=_noop_progress)
    calls = patched_screening_run.call_log
    assert calls[0]["aoi"]["radius_km"] == 120.0   # region's own buffer
    assert calls[1]["aoi"]["radius_km"] == 5        # shared fallback


def test_missing_radius_key_falls_back_to_shared(patched_screening_run):
    """Legacy supplier dicts with no ``radius_km`` key at all still work —
    ``.get`` returns None → shared radius."""
    setup = _setup(1)  # _supplier() emits no radius_km key
    state = PrioritisationState(
        kind=PrioritisationStateKind.S2_RUNNING, setup=setup,
    )
    run_batch(state, setup, on_progress=_noop_progress)
    assert patched_screening_run.call_log[0]["aoi"]["radius_km"] == 5
