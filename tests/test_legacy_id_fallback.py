"""Tests for the M-ATTRIB-A1 dual-emit reader shim (Q-AT-3 window).

Saved analyses created before M-ATTRIB-A1 carry only the legacy IDs
(`air.attribution_confidence_score`, `nature.quality_attribution`). The
engine now emits BOTH ids on fresh runs, but the UI was migrated to
read the new ids only — which silently broke replay of old saved
analyses. `payload_read` restores the dual-emit contract on the read
side: prefer new, fall back to legacy.
"""

from __future__ import annotations

import pytest

from ui.components.legacy_id_fallback import payload_read


class TestPayloadReadFallback:
    # Air aggregate rename
    def test_air_prefers_new_id_when_both_present(self):
        # Engine dual-emit: both ids carry identical value. Reader must pick new.
        v = payload_read(
            {
                "air.measurement_quality_score":    0.81,
                "air.attribution_confidence_score": 0.81,
            },
            "air.measurement_quality_score",
        )
        assert v == 0.81

    def test_air_falls_back_to_legacy_when_new_absent(self):
        # Old saved analysis: only the legacy id is present.
        v = payload_read(
            {"air.attribution_confidence_score": 0.6988},
            "air.measurement_quality_score",
        )
        assert v == 0.6988

    def test_air_none_when_neither_present(self):
        assert payload_read({}, "air.measurement_quality_score") is None

    # Nature aggregate rename
    def test_nature_prefers_new_id_when_both_present(self):
        v = payload_read(
            {
                "nature.measurement_quality": 0.81,
                "nature.quality_attribution": 0.81,
            },
            "nature.measurement_quality",
        )
        assert v == 0.81

    def test_nature_falls_back_to_legacy_when_new_absent(self):
        v = payload_read(
            {"nature.quality_attribution": 0.69},
            "nature.measurement_quality",
        )
        assert v == 0.69

    def test_nature_none_when_neither_present(self):
        assert payload_read({}, "nature.measurement_quality") is None

    # Non-renamed IDs pass through unchanged
    def test_non_renamed_id_passthrough(self):
        # Per-indicator confidence IDs were not renamed — no fallback.
        v = payload_read({"nature.habitat.confidence": 0.955}, "nature.habitat.confidence")
        assert v == 0.955

    def test_non_renamed_id_absent_returns_none(self):
        # And don't accidentally find a fallback target for unrelated keys.
        assert payload_read({"nature.habitat.confidence": 0.955}, "ghg.data_quality_attribution") is None

    # Defensive
    def test_non_dict_payload_returns_none(self):
        assert payload_read(None, "air.measurement_quality_score") is None
        assert payload_read("a string", "nature.measurement_quality") is None

    def test_legacy_value_zero_still_returned(self):
        # Guard against `if value is None or not value:` style bugs — a
        # legacy 0.0 is a real value and must be returned, not skipped.
        v = payload_read(
            {"air.attribution_confidence_score": 0.0},
            "air.measurement_quality_score",
        )
        assert v == 0.0
