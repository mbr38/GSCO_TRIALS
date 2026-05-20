"""Tests for ``ui.page_state.detect_e1_reason`` (M-RING-UX).

Pure-Python — no Streamlit, no Earth Engine. The helper walks the
flat ``_provenance.<pillar>.<indicator>`` keys in an engine payload
and categorises the population of ``skipped_reason`` codes into the
bucket the E1_AllFailed page should render.
"""

# M-RING-UX
from __future__ import annotations

import pytest

from ui.page_state import detect_e1_reason


# ---------------------------------------------------------------------------
# All-ring-empty → "ring_empty"
# ---------------------------------------------------------------------------

def test_all_ring_empty_returns_ring_empty():
    """Acre-style payload — every Air pollutant skipped via ring-empty."""
    payload = {
        "_provenance.air.no2":  {"skipped_reason": "background_ring_no_data"},
        "_provenance.air.so2":  {"skipped_reason": "background_ring_no_data"},
        "_provenance.air.co":   {"skipped_reason": "background_ring_no_data"},
        "_provenance.air.hcho": {"skipped_reason": "background_ring_no_data"},
        "_provenance.air.o3":   {"skipped_reason": "background_ring_no_data"},
        "_provenance.air.aai":  {"skipped_reason": "background_ring_no_data"},
        "_provenance.air.pm25": {"skipped_reason": "background_ring_no_data"},
        "_provenance.air.pm10": {"skipped_reason": "background_ring_no_data"},
        "_provenance.air.aod":  {"skipped_reason": "background_ring_no_data"},
        # Pillar follow-up priority None — but the helper doesn't use it.
        "air.audit_followup_priority": None,
    }
    assert detect_e1_reason(payload) == "ring_empty"


def test_single_ring_empty_indicator_returns_ring_empty():
    """One indicator selected, ring-empty → still 'ring_empty' (all of
    one is still all of them)."""
    payload = {
        "_provenance.air.no2": {"skipped_reason": "background_ring_no_data"},
    }
    assert detect_e1_reason(payload) == "ring_empty"


# ---------------------------------------------------------------------------
# Mixed no-data codes → "no_data_at_all"
# ---------------------------------------------------------------------------

def test_mixed_no_data_codes_returns_no_data_at_all():
    """Ocean / sparse-asset payload — different reducers, different
    no_* codes for each. All in the no-data bucket → catch-all."""
    payload = {
        "_provenance.air.no2":         {"skipped_reason": "no_s5p_pixels"},
        "_provenance.air.pm25":        {"skipped_reason": "no_cams_pixels"},
        "_provenance.air.aod":         {"skipped_reason": "no_maiac_pixels"},
        "_provenance.ghg.viirs":       {"skipped_reason": "no_viirs_pixels"},
        "_provenance.ghg.co2":         {"skipped_reason": "out_of_coverage"},
        "_provenance.nature.dw":       {"skipped_reason": "no_dw_pixels"},
        "_provenance.nature.forest_loss": {"skipped_reason": "no_hansen_pixels"},
        "_provenance.nature.ndvi":     {"skipped_reason": "no_modis_pixels"},
    }
    assert detect_e1_reason(payload) == "no_data_at_all"


def test_ring_empty_plus_no_data_codes_returns_no_data_at_all():
    """A mix of ring-empty AND asset-empty codes is still 'no data at
    all' — the catch-all bucket. ring_empty alone would have returned
    the more specific 'ring_empty'."""
    payload = {
        "_provenance.air.no2":     {"skipped_reason": "background_ring_no_data"},
        "_provenance.air.aod":     {"skipped_reason": "no_maiac_pixels"},
        "_provenance.nature.dw":   {"skipped_reason": "no_dw_pixels"},
    }
    assert detect_e1_reason(payload) == "no_data_at_all"


# ---------------------------------------------------------------------------
# Defensive / "unknown" cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", [
    None,
    {},
    {"composite.overall_screening": 0.5},  # no provenance keys at all
])
def test_empty_or_no_provenance_returns_unknown(payload):
    assert detect_e1_reason(payload) == "unknown"


def test_provenance_without_skipped_reason_returns_unknown():
    """A payload with provenance blocks but no skipped_reason (i.e.
    every indicator actually computed) → 'unknown'. In practice this
    shouldn't reach E1 — but defensively, we don't pretend to know."""
    payload = {
        "_provenance.air.no2": {
            "asset_id": "COPERNICUS/S5P/OFFL/L3_NO2",
            # No skipped_reason — the indicator ran successfully.
        },
    }
    assert detect_e1_reason(payload) == "unknown"


def test_unrecognised_skipped_reason_returns_unknown():
    """A novel skipped_reason code that isn't in our taxonomy can't be
    bucketed — fall back to the generic message."""
    payload = {
        "_provenance.air.no2": {"skipped_reason": "novel_v2_code"},
    }
    assert detect_e1_reason(payload) == "unknown"


def test_malformed_provenance_block_is_ignored():
    """Defensive: a provenance value that isn't a dict (string,
    list, etc.) doesn't crash the helper. With no valid skip codes
    found, returns 'unknown'."""
    payload = {
        "_provenance.air.no2": "not a dict",
        "_provenance.ghg.ch4": ["also not a dict"],
    }
    assert detect_e1_reason(payload) == "unknown"


def test_non_provenance_keys_are_skipped():
    """Only ``_provenance.*`` keys are inspected; other top-level keys
    are ignored even when they happen to carry a 'skipped_reason'."""
    payload = {
        "air.audit_followup_priority": None,
        "_failures": {"air": [{"indicator_id": "air.no2", "skipped_reason": "x"}]},
        "_provenance.air.no2": {"skipped_reason": "background_ring_no_data"},
    }
    # Only the one valid _provenance block contributes → ring_empty.
    assert detect_e1_reason(payload) == "ring_empty"
