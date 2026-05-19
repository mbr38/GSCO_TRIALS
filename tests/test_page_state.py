"""Tests for ui.page_state (M-UI-E.1).

Pure-Python state-machine tests. No Streamlit, no Earth Engine — these
only exercise the ``classify_result`` decision logic and the
``PageState`` dataclass shape.
"""

# M-UI-E.1
from __future__ import annotations

import dataclasses

import pytest

from ui.page_state import PageState, classify_result


# ---------------------------------------------------------------------------
# Payload fixtures — synthetic engine outputs mimicking ScreeningRun.run()
# ---------------------------------------------------------------------------

def _payload(
    *,
    pillars_run: list[str] | None = None,
    air_priority: float | None = 0.42,
    ghg_priority: float | None = 0.51,
    nature_priority: float | None = 0.33,
    failures: dict | None = None,
) -> dict:
    """Build a minimal payload shaped like a ScreeningRun result."""
    out: dict = {
        "air.audit_followup_priority":    air_priority,
        "ghg.audit_followup_priority":    ghg_priority,
        "nature.followup_priority":       nature_priority,
        "_meta": {
            "pillars_run": (
                pillars_run if pillars_run is not None
                else ["air", "ghg", "nature"]
            ),
        },
    }
    if failures is not None:
        out["_failures"] = failures
    return out


# ---------------------------------------------------------------------------
# classify_result
# ---------------------------------------------------------------------------

def test_clean_payload_classifies_as_s2_results():
    """No _failures, all three pillar aggregates non-None -> S2_Results."""
    assert classify_result(_payload()) == "S2_Results"


def test_partial_failures_classify_as_s2_partial():
    """_failures.air non-empty, all aggregates still non-None -> S2_Partial."""
    payload = _payload(
        failures={"air": [{"indicator_id": "air.pm10.score", "reason": "no scenes"}]},
    )
    assert classify_result(payload) == "S2_Partial"


def test_all_pillar_aggregates_none_classifies_as_e1_all_failed():
    """All three pillar aggregates None -> E1_AllFailed."""
    payload = _payload(
        air_priority=None,
        ghg_priority=None,
        nature_priority=None,
        failures={
            "air":    [{"type": "pillar_wide", "reason": "EE down"}],
            "ghg":    [{"type": "pillar_wide", "reason": "EE down"}],
            "nature": [{"type": "pillar_wide", "reason": "EE down"}],
        },
    )
    assert classify_result(payload) == "E1_AllFailed"


def test_empty_failures_dict_classifies_as_s2_results():
    """_failures = {} (orchestrator wrote no failures) -> S2_Results."""
    assert classify_result(_payload(failures={})) == "S2_Results"


def test_empty_pillars_run_does_not_trigger_all_failed():
    """pillars_run = [] -> S2_Results, not E1_AllFailed.

    The all-failed branch only fires when there were pillars that all
    failed; an empty list means no pillar was even attempted.
    """
    payload = _payload(pillars_run=[])
    # Aggregates can be anything here — exercise the guard explicitly
    # by also setting them to None to prove pillars_run is the gate.
    payload["air.audit_followup_priority"]    = None
    payload["ghg.audit_followup_priority"]    = None
    payload["nature.followup_priority"]       = None
    assert classify_result(payload) == "S2_Results"


def test_partial_with_only_one_failed_pillar_aggregate_is_still_partial():
    """One pillar's aggregate is None (pillar-wide failure) and another
    pillar succeeded -> still S2_Partial, not E1_AllFailed, because
    not every pillar in pillars_run failed.
    """
    payload = _payload(
        air_priority=None,
        ghg_priority=0.4,
        nature_priority=0.6,
        failures={"air": [{"type": "pillar_wide", "reason": "EE down"}]},
    )
    assert classify_result(payload) == "S2_Partial"


def test_failures_with_only_empty_lists_is_not_partial():
    """Defensive: if a pillar key maps to [] it doesn't count as a failure."""
    payload = _payload(failures={"air": [], "ghg": []})
    assert classify_result(payload) == "S2_Results"


# ---------------------------------------------------------------------------
# PageState
# ---------------------------------------------------------------------------

def test_page_state_is_frozen():
    """PageState is a frozen dataclass — attribute assignment raises."""
    state = PageState(name="S1_Computing", run_id="abc")
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.name = "S2_Results"  # type: ignore[misc]


def test_page_state_round_trip_each_state_name():
    """Every StateName constructs cleanly with the right optional fields."""
    s1 = PageState(name="S1_Computing", run_id="r1")
    assert s1.result is None and s1.error is None and s1.failures is None

    s2 = PageState(
        name="S2_Results",
        run_id="r2",
        result={"composite.overall_screening": 0.5},
    )
    assert s2.result == {"composite.overall_screening": 0.5}

    s2p = PageState(
        name="S2_Partial",
        run_id="r3",
        result={"composite.overall_screening": 0.5},
        failures={"air": [{"indicator_id": "air.pm10.score"}]},
    )
    assert s2p.failures == {"air": [{"indicator_id": "air.pm10.score"}]}

    e1 = PageState(name="E1_AllFailed", run_id="r4", error="EE service down")
    assert e1.error == "EE service down"
