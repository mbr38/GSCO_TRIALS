"""Tests for ui.components.c9_partial_banner (M-UI-E.5).

Pure-Python — no Streamlit. All assertions go through ``_collect_missing``
which is the renderer's pure helper. The render function only adds
Streamlit-side chrome and short-circuits when the list is empty.
"""

# M-UI-E.5
from __future__ import annotations

import pytest

from ui.components.c9_partial_banner import _collect_missing


# ---------------------------------------------------------------------------
# Clean payload
# ---------------------------------------------------------------------------

def test_clean_payload_returns_empty_list():
    """No failures, no skipped provenance → nothing missing."""
    assert _collect_missing({}) == []
    assert _collect_missing({"composite.overall_screening": 0.5}) == []


# ---------------------------------------------------------------------------
# Explicit failures
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pillar,indicator_id", [
    ("air",    "air.pm10"),
    ("ghg",    "ghg.ch4"),
    ("nature", "nature.kba"),
])
def test_explicit_failure_picked_up(pillar, indicator_id):
    payload = {
        "_failures": {
            pillar: [{"indicator_id": indicator_id, "reason": "computed"}],
        },
    }
    rows = _collect_missing(payload)
    assert [r.indicator_id for r in rows] == [indicator_id]
    assert rows[0].source == "failure"


def test_failure_without_reason_falls_back_to_generic():
    payload = {"_failures": {"air": [{"indicator_id": "air.pm10"}]}}
    rows = _collect_missing(payload)
    assert rows[0].reason == "Failed (no reason recorded)."


def test_failure_without_indicator_id_is_skipped():
    """Defensive: a malformed entry with no indicator_id is silently dropped."""
    payload = {"_failures": {"air": [{"reason": "huh?"}]}}
    assert _collect_missing(payload) == []


def test_failures_entry_that_isnt_a_list_is_skipped():
    """Defensive: a string or dict under a pillar key doesn't crash."""
    payload = {"_failures": {"air": "not a list"}}
    assert _collect_missing(payload) == []


# ---------------------------------------------------------------------------
# Silent skips via provenance
# ---------------------------------------------------------------------------

def test_silent_skip_via_provenance_skipped_reason():
    payload = {
        "_provenance.ghg.co2": {"skipped_reason": "out_of_coverage"},
    }
    rows = _collect_missing(payload)
    assert len(rows) == 1
    assert rows[0].indicator_id == "ghg.co2"
    assert rows[0].source == "skipped"
    assert "coverage window" in rows[0].reason.lower()


def test_unknown_skipped_reason_passes_through_verbatim():
    """Codes not in the translation table become the row's reason as-is."""
    payload = {"_provenance.air.no2": {"skipped_reason": "novel_code_v2"}}
    rows = _collect_missing(payload)
    assert rows[0].reason == "novel_code_v2"


# ---------------------------------------------------------------------------
# De-duplication
# ---------------------------------------------------------------------------

def test_failure_wins_when_indicator_in_both_paths():
    """An indicator that's both in _failures and carries skipped_reason
    in provenance is reported once, with the failure entry's reason —
    the engine's specific message is more useful than the silent-skip
    generic translation.
    """
    payload = {
        "_failures": {
            "ghg": [{"indicator_id": "ghg.co2", "reason": "specific message"}],
        },
        "_provenance.ghg.co2": {"skipped_reason": "out_of_coverage"},
    }
    rows = _collect_missing(payload)
    assert len(rows) == 1
    assert rows[0].source == "failure"
    assert rows[0].reason == "specific message"


# ---------------------------------------------------------------------------
# Sort order
# ---------------------------------------------------------------------------

def test_sort_order_is_pillar_then_indicator_id():
    """Result ordering is air → ghg → nature; within a pillar, alpha."""
    payload = {
        "_failures": {
            "nature": [{"indicator_id": "nature.kba", "reason": "n"}],
            "air":    [
                {"indicator_id": "air.pm25", "reason": "a"},
                {"indicator_id": "air.pm10", "reason": "b"},
            ],
            "ghg":    [{"indicator_id": "ghg.co2", "reason": "g"}],
        },
    }
    rows = _collect_missing(payload)
    assert [r.indicator_id for r in rows] == [
        "air.pm10", "air.pm25", "ghg.co2", "nature.kba",
    ]


# ---------------------------------------------------------------------------
# End-to-end on the São Paulo payload shape
# ---------------------------------------------------------------------------

def test_e2e_sao_paulo_returns_three_entries():
    """Synthetic payload matching São Paulo: PM10 + PM25 failures, CO₂
    silently skipped via the coverage_window check."""
    payload = {
        "_failures": {
            "air": [
                {"indicator_id": "air.pm10", "reason": "site buffer (5 km) smaller than pm10 native pixel (44.5 km)"},
                {"indicator_id": "air.pm25", "reason": "site buffer (5 km) smaller than pm25 native pixel (44.5 km)"},
            ],
        },
        "_provenance.ghg.co2": {"skipped_reason": "out_of_coverage"},
    }
    rows = _collect_missing(payload)
    assert [r.indicator_id for r in rows] == [
        "air.pm10", "air.pm25", "ghg.co2",
    ]
    assert [r.source for r in rows] == ["failure", "failure", "skipped"]
