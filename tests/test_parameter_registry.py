"""Tests for the parameter transparency registry (M-UX-A1 item 2.8).

Covers the parser (field extraction, optional fields, applies_to parsing,
malformed-block detection), the per-indicator lookup (shared constants render
under each referencing indicator), the code-path format, and the UX12 lint
(warning-only per locked decision Q-UX-2).
"""

# M-UX-A1
from __future__ import annotations

import warnings

import pytest

from engine import parameter_registry as pr
from engine.parameter_registry import (
    ParameterRecord,
    VALID_TIERS,
    _parse_annotation_block,
    _parse_applies_to,
    get_parameters_for_indicator,
    inventory_names,
    lint_inventory,
    load_registry,
)


# ---------------------------------------------------------------------------
# Inventory scope (UX8) — 17 constants locked at Step B.
# ---------------------------------------------------------------------------

class TestInventoryScope:
    def test_inventory_size_in_target_range(self) -> None:
        # UX8: ~15-30 user-facing thresholds. Step B locked 17.
        assert 15 <= len(inventory_names()) <= 30

    def test_step_b_locked_set(self) -> None:
        # 15 UX8-named + TRAFFIC_LIGHT_THRESHOLDS + NORMALISATION_K.
        assert "TRAFFIC_LIGHT_THRESHOLDS" in inventory_names()
        assert "NORMALISATION_K" in inventory_names()
        # The two first-pass additions were dropped at Step B.
        assert "NDVI_NEGATIVE_TREND_THRESHOLD" not in inventory_names()
        assert "HANSEN_VERBAL_MENTION_THRESHOLD" not in inventory_names()


# ---------------------------------------------------------------------------
# Parser — field extraction from real annotations.
# ---------------------------------------------------------------------------

class TestParser:
    def test_all_inventory_constants_parse_valid(self) -> None:
        for rec in load_registry():
            assert rec.is_valid, f"{rec.code_path} failed to parse: {rec.missing_fields}"

    def test_required_fields_present(self) -> None:
        for rec in load_registry():
            assert rec.tier
            assert rec.rationale
            assert rec.source

    def test_tiers_are_valid(self) -> None:
        for rec in load_registry():
            assert rec.tier in VALID_TIERS

    def test_multiline_rationale_joined(self) -> None:
        # ANOMALY_Z_THRESHOLD's rationale spans several continuation lines.
        rec = _by_name("ANOMALY_Z_THRESHOLD")
        assert "anomalous day" in rec.rationale
        assert "M-DIAG-A1" in rec.rationale
        # Continuation lines were joined into one paragraph (no stray '#').
        assert "#" not in rec.rationale

    def test_live_value_read_from_module(self) -> None:
        # The value is the live constant, not re-typed in the annotation.
        assert _by_name("ANOMALY_Z_THRESHOLD").value == 2.0
        assert _by_name("TRAFFIC_LIGHT_THRESHOLDS").value == (0.33, 0.66)

    def test_optional_last_reviewed_present(self) -> None:
        # M-DIAG-A2 Step C.3 (29 May 2026) re-reviewed ANOMALY_Z_THRESHOLD
        # against the post-fix detector and promoted its tier from
        # "first-pass" to "spec-mandated" (per IC §0.4 2σ convention). The
        # last_reviewed date moves forward accordingly.
        assert _by_name("ANOMALY_Z_THRESHOLD").last_reviewed == "2026-05-29"

    def test_applies_to_parsed(self) -> None:
        rec = _by_name("WIND_SPEED_HIGH_MAX_MS")
        assert set(rec.applies_to) == {
            "air.no2", "air.so2", "air.hcho", "air.aai", "air.aod"
        }

    def test_honest_tier_distribution(self) -> None:
        # UX16 — most thresholds ship first-pass (the honest current state).
        # M-DIAG-A2 Step C.3 (29 May 2026) shifted the distribution by:
        #   - ANOMALY_Z_THRESHOLD: first-pass → spec-mandated (IC §0.4)
        #   - WIND_SPEED_LOW_MIN_MS: first-pass → calibrated (5.0 → 3.5)
        # Net: -2 first-pass, +1 spec-mandated, +1 calibrated.
        tiers = [r.tier for r in load_registry()]
        assert tiers.count("first-pass") == 13
        assert tiers.count("spec-mandated") == 3
        assert tiers.count("calibrated") == 1


# ---------------------------------------------------------------------------
# Parser — block-extraction edge cases (synthetic source lines).
# ---------------------------------------------------------------------------

class TestBlockExtraction:
    def test_well_formed_block_extracts_all_fields(self) -> None:
        lines = (
            "# @parameter",
            "# tier: calibrated",
            "# rationale: A reason that",
            "#     wraps to a second line.",
            "# source: a citation",
            "# last_reviewed: 2026-01-01",
            "# applies_to: [air.no2, ghg.ch4]",
            "FOO: float = 1.0",
        )
        block = _parse_annotation_block(lines, def_idx=7)
        assert block["tier"] == "calibrated"
        assert block["rationale"] == "A reason that wraps to a second line."
        assert block["source"] == "a citation"
        assert block["last_reviewed"] == "2026-01-01"
        assert block["applies_to"] == "[air.no2, ghg.ch4]"

    def test_no_marker_returns_none(self) -> None:
        # A constant with ordinary comments but no @parameter marker.
        lines = (
            "# just a normal comment",
            "BAR: int = 3",
        )
        assert _parse_annotation_block(lines, def_idx=1) is None

    def test_optional_fields_absent_is_fine(self) -> None:
        lines = (
            "# @parameter",
            "# tier: first-pass",
            "# rationale: short",
            "# source: x",
            "BAZ = 5",
        )
        block = _parse_annotation_block(lines, def_idx=4)
        assert "last_reviewed" not in block
        assert "applies_to" not in block

    @pytest.mark.parametrize("raw,expected", [
        ("[air.no2, air.so2]", ("air.no2", "air.so2")),
        ("[ air.no2 ]", ("air.no2",)),
        ("[]", ()),
        (None, ()),
        ("", ()),
    ])
    def test_parse_applies_to(self, raw, expected) -> None:
        assert _parse_applies_to(raw) == expected


# ---------------------------------------------------------------------------
# Per-indicator lookup (UX19) + code-path format (UX14).
# ---------------------------------------------------------------------------

class TestLookup:
    def test_full_id_matches_base_applies_to(self) -> None:
        # Card id is full-form; applies_to is base-form.
        names = [r.name for r in get_parameters_for_indicator("air.no2.score")]
        assert "ANOMALY_Z_THRESHOLD" in names
        assert "SEVERITY_BANDS" in names

    def test_indicator_with_no_parameters_returns_empty(self) -> None:
        # UX17 negative case — ODIAC CO2 has no annotated parameters.
        assert get_parameters_for_indicator("ghg.co2.score") == []

    def test_shared_constant_renders_under_each_indicator(self) -> None:
        # UX19 — NORMALISATION_K applies to many indicators; it must appear
        # under each of them.
        for cid in ["air.no2.score", "ghg.ch4.score", "nature.ndvi.score"]:
            names = [r.name for r in get_parameters_for_indicator(cid)]
            assert "NORMALISATION_K" in names

    def test_shared_count_for_multi_indicator_constant(self) -> None:
        rec = _by_name("NORMALISATION_K")
        assert rec.shared_count == len(rec.applies_to) - 1
        assert rec.shared_count > 0

    def test_single_indicator_constant_not_shared(self) -> None:
        assert _by_name("KBA_DISTANCE_DECAY_KM").shared_count == 0

    def test_code_path_format(self) -> None:
        # UX14 — module/path.py::CONSTANT_NAME.
        assert _by_name("ANOMALY_Z_THRESHOLD").code_path == (
            "engine/constants.py::ANOMALY_Z_THRESHOLD"
        )
        # The severity-bands constant lives in the UI layer.
        assert _by_name("SEVERITY_BANDS").code_path == (
            "ui/components/severity.py::SEVERITY_BANDS"
        )


# ---------------------------------------------------------------------------
# UX12 lint — warning-only (Q-UX-2 locked).
# ---------------------------------------------------------------------------

class TestLint:
    def test_inventory_is_fully_annotated_warns_only(self) -> None:
        # Per Q-UX-2 the lint is a warning, not a hard gate: surface any
        # problem as a warning rather than failing. With the inventory fully
        # annotated this list is empty today.
        problems = lint_inventory()
        if problems:
            warnings.warn(
                "Unannotated inventory constants:\n" + "\n".join(problems),
                stacklevel=2,
            )
        # The test does not fail on problems (warning-only), but we assert the
        # current expected state so a regression is visible.
        assert problems == []

    def test_lint_detects_missing_annotation(self, monkeypatch) -> None:
        # Deliberately add a real-but-unannotated constant to the inventory
        # and confirm the lint catches it (test-plan 6.3 / §7 UX12).
        patched = pr._INVENTORY + (("HABITAT_BASELINE_YEARS", "engine.constants"),)
        monkeypatch.setattr(pr, "_INVENTORY", patched)
        load_registry.cache_clear()
        try:
            problems = lint_inventory()
            assert any("HABITAT_BASELINE_YEARS" in p for p in problems)
            assert any("@parameter" in p for p in problems)
        finally:
            load_registry.cache_clear()  # restore clean cache for other tests

    def test_lint_detects_missing_constant(self, monkeypatch) -> None:
        patched = pr._INVENTORY + (("NO_SUCH_CONSTANT", "engine.constants"),)
        monkeypatch.setattr(pr, "_INVENTORY", patched)
        load_registry.cache_clear()
        try:
            problems = lint_inventory()
            assert any("NO_SUCH_CONSTANT" in p for p in problems)
        finally:
            load_registry.cache_clear()


# ---------------------------------------------------------------------------
# ParameterRecord validity logic.
# ---------------------------------------------------------------------------

class TestParameterRecord:
    def test_missing_required_field_is_invalid(self) -> None:
        rec = ParameterRecord(
            name="X", module="engine.constants", value=1.0,
            tier="first-pass", rationale="r", source="",
            missing_fields=("source",),
        )
        assert not rec.is_valid

    def test_unknown_tier_is_invalid(self) -> None:
        rec = ParameterRecord(
            name="X", module="engine.constants", value=1.0,
            tier="made-up", rationale="r", source="s",
        )
        assert not rec.is_valid

    def test_unannotated_is_invalid(self) -> None:
        rec = ParameterRecord(
            name="X", module="engine.constants", value=1.0,
            tier="", rationale="", source="", annotated=False,
        )
        assert not rec.is_valid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _by_name(name: str) -> ParameterRecord:
    for rec in load_registry():
        if rec.name == name:
            return rec
    raise AssertionError(f"{name} not in registry")
