"""Canary tests — every emitted indicator carries the canonical 15-field
provenance shape, plus correct lookup-table-driven defaults for the four
v1.x epistemic tags.

Approach: avoid EE by constructing provenance blocks directly via
`build_provenance` against the per-indicator configs (which is the same
code path the engine takes — `build_provenance` is the only constructor).
This pins:

1. The exact 15-key shape and ordering.
2. `indicator_id` self-describes the outer payload key.
3. The audit §1.5 column-to-surface uncertainty per gas.
4. The audit §9.3 standing-exposure / live-window split.
5. `sector_signal_anomaly` stays None in v1 (lights up with Tier C2).

Added by M-V1x-RECONCILE per the spec's §6 / §5 step 14.
"""

from __future__ import annotations

from engine.core.provenance import build_provenance


_CANONICAL_KEYS = [
    "indicator_id",
    "asset_id", "band", "data_type", "data_source",
    "native_scale_m", "method_note", "time_range",
    "coverage_window", "skipped_reason", "observations",
    "column_to_surface_uncertainty", "temporal_mode",
    "sector_signal_anomaly", "extra",
]


# Every indicator the engine emits a `_provenance.<pillar>.<indicator>` block
# for. Maintained alongside the per-pillar config dicts.
_ALL_INDICATOR_IDS: list[str] = [
    # Air pillar
    "air.no2", "air.so2", "air.co", "air.hcho", "air.o3", "air.aai",
    "air.pm25", "air.pm10", "air.aod",
    # GHG pillar
    "ghg.ch4", "ghg.co2", "ghg.viirs",
    # Nature pillar
    "nature.kba", "nature.dw", "nature.habitat", "nature.forest_loss",
    "nature.ndvi", "nature.water", "nature.recovery",
    "nature.regional_loss_evidence",
]


def _build_for(indicator_id: str) -> dict:
    """Construct a provenance block for `indicator_id` with the minimal
    required args. Mirrors how the engine constructs blocks at runtime."""
    return build_provenance(
        indicator_id=indicator_id,
        asset_id="X/Y/Z",
        band="b",
        # `reference_dataset` works for all 20 — bypasses the data_type
        # enum check, which is orthogonal to the shape tests here.
        data_type="reference_dataset",
        data_source="test-source",
        native_scale_m=10.0,
        time_range=("2023-01-01", "2023-04-01"),
    )


class TestProvenanceShape:
    def test_every_provenance_block_has_15_fields(self) -> None:
        for indicator_id in _ALL_INDICATOR_IDS:
            prov = _build_for(indicator_id)
            assert list(prov.keys()) == _CANONICAL_KEYS, (
                f"{indicator_id}: provenance shape drifted from canonical"
            )

    def test_indicator_id_self_describes_correctly(self) -> None:
        # The `indicator_id` field must match what was passed — round-trip check.
        for indicator_id in _ALL_INDICATOR_IDS:
            prov = _build_for(indicator_id)
            assert prov["indicator_id"] == indicator_id

    def test_column_to_surface_uncertainty_matches_audit_table(self) -> None:
        # Audit §1.5 per-gas table, surfaced via the lookup in
        # engine.core.provenance._COLUMN_TO_SURFACE_UNCERTAINTY.
        expected = {
            "air.no2":   "moderate",
            "air.so2":   "moderate_weak",
            "air.co":    "weak",
            "air.hcho":  "moderate",
            "air.o3":    "n_a",
            "air.aai":   "n_a",
            "ghg.ch4":   "weak",
        }
        for indicator_id, expected_tag in expected.items():
            prov = _build_for(indicator_id)
            assert prov["column_to_surface_uncertainty"] == expected_tag, (
                f"{indicator_id}: column_to_surface_uncertainty drifted from "
                f"audit §1.5 — expected {expected_tag}, got "
                f"{prov['column_to_surface_uncertainty']}"
            )

        # Every non-column / non-air indicator defaults to "n_a".
        for indicator_id in _ALL_INDICATOR_IDS:
            if indicator_id in expected:
                continue
            prov = _build_for(indicator_id)
            assert prov["column_to_surface_uncertainty"] == "n_a", (
                f"{indicator_id}: should default to n_a; got "
                f"{prov['column_to_surface_uncertainty']}"
            )

    def test_temporal_mode_standing_for_odiac_hansen_and_regional_loss(self) -> None:
        # Audit §9.3: standing-exposure indicators are ODIAC CO₂, Hansen
        # forest_loss, and the regional_loss_evidence helper (which reads
        # Hansen with a fixed 5-year lookback). Everything else is live_window.
        standing = {
            "ghg.co2",
            "nature.forest_loss",
            "nature.regional_loss_evidence",
        }
        for indicator_id in _ALL_INDICATOR_IDS:
            prov = _build_for(indicator_id)
            expected_mode = (
                "standing_exposure" if indicator_id in standing else "live_window"
            )
            assert prov["temporal_mode"] == expected_mode, (
                f"{indicator_id}: temporal_mode drifted — expected "
                f"{expected_mode}, got {prov['temporal_mode']}"
            )

    def test_sector_signal_anomaly_is_none_in_v1(self) -> None:
        # v1 never fires this flag; lights up with Tier C2 per audit §9.2.
        for indicator_id in _ALL_INDICATOR_IDS:
            prov = _build_for(indicator_id)
            assert prov["sector_signal_anomaly"] is None, (
                f"{indicator_id}: sector_signal_anomaly should be None in v1 "
                f"(lights up Tier C2)"
            )
