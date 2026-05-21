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
# M-E1-INDICATOR-AWARE: selection-aware classification
# ---------------------------------------------------------------------------

class TestClassifySelectionAware:
    """Pin the post-M-E1-INDICATOR-AWARE behaviour: a single-indicator
    run whose one selected indicator succeeded must route to S2_Results
    even when the pillar's follow-up priority is None (M-FOLLOWUP-FALLBACK
    strict-None over the unselected sub-aggregates).

    Bug reproduced: KBA-only screening at Bahia returned
    nature.kba.proximity_score = 0.24 but the page showed E1_AllFailed
    because nature.followup_priority was None over unselected
    sub-aggregates.
    """

    def test_single_indicator_success_routes_to_s2_results(self):
        """The Bahia bug. Selected = one indicator; it succeeded; pillar
        aggregate is None — must be S2_Results, not E1_AllFailed."""
        payload = {
            "nature.kba.proximity_score": 0.24,
            # Pillar aggregate is None (strict-None over unselected
            # sub-aggregates) — what triggered the original bug.
            "nature.followup_priority":    None,
            "air.audit_followup_priority": None,
            "ghg.audit_followup_priority": None,
            "_meta": {"pillars_run": ["air", "ghg", "nature"]},
        }
        result = classify_result(
            payload, ["nature.kba.proximity_score"],
        )
        assert result == "S2_Results"

    def test_single_indicator_failure_routes_to_e1(self):
        """Same selection but the indicator returned None — E1."""
        payload = {
            "nature.kba.proximity_score":  None,
            "nature.followup_priority":    None,
            "_meta": {"pillars_run": ["nature"]},
        }
        result = classify_result(
            payload, ["nature.kba.proximity_score"],
        )
        assert result == "E1_AllFailed"

    def test_multi_indicator_partial_routes_to_s2_partial(self):
        """3 selected, 2 have values + 1 is None → S2_Partial."""
        payload = {
            "air.no2.score":              0.4,
            "ghg.ch4.score":              0.5,
            "nature.kba.proximity_score": None,
            "_meta": {"pillars_run": ["air", "ghg", "nature"]},
        }
        selected = [
            "air.no2.score", "ghg.ch4.score", "nature.kba.proximity_score",
        ]
        assert classify_result(payload, selected) == "S2_Partial"

    def test_multi_indicator_all_success_routes_to_s2_results(self):
        payload = {
            "air.no2.score":              0.4,
            "ghg.ch4.score":              0.5,
            "nature.kba.proximity_score": 0.3,
            "_meta": {"pillars_run": ["air", "ghg", "nature"]},
        }
        selected = [
            "air.no2.score", "ghg.ch4.score", "nature.kba.proximity_score",
        ]
        assert classify_result(payload, selected) == "S2_Results"

    def test_multi_indicator_all_failed_routes_to_e1(self):
        """Acre-style: every selected indicator skipped → E1.
        M-RING-UX's detect_e1_reason still fires the methodology-aware
        message in this branch."""
        payload = {
            "air.no2.score":              None,
            "ghg.ch4.score":              None,
            "nature.kba.proximity_score": None,
        }
        selected = [
            "air.no2.score", "ghg.ch4.score", "nature.kba.proximity_score",
        ]
        assert classify_result(payload, selected) == "E1_AllFailed"

    def test_failures_block_alongside_full_success_routes_to_s2_partial(self):
        """All selected indicators delivered, but ``_failures`` carries
        a non-empty entry → still S2_Partial."""
        payload = {
            "air.no2.score": 0.4,
            "_failures": {
                "air": [{"indicator_id": "air.so2.score", "reason": "x"}],
            },
        }
        assert classify_result(payload, ["air.no2.score"]) == "S2_Partial"

    def test_no_selection_falls_back_to_pillar_aggregate_logic(self):
        """Defensive: omitted selection → pre-M-E1-INDICATOR-AWARE
        behaviour. Test fixture from above asserts on this path
        (test_clean_payload_classifies_as_s2_results et al.)."""
        # Direct exercise — explicit None.
        assert classify_result(_payload()) == "S2_Results"
        assert classify_result(_payload(), None) == "S2_Results"

    def test_empty_selection_falls_back_to_pillar_aggregate_logic(self):
        """Defensive: empty list also routes to the fallback."""
        assert classify_result(_payload(), []) == "S2_Results"


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
