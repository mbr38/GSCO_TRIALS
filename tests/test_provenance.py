"""Unit tests for engine.core.provenance.build_provenance.

The canonical provenance schema is a constructor + strict validation. These
tests pin the field order (downstream renderers rely on insertion order)
and the validation paths so a typo in `data_type`, `observations.unit`,
`column_to_surface_uncertainty`, or `temporal_mode` fails loudly at
construction time.

Per-pillar shape tests (i.e. "did this pollutant emit the canonical block?")
live in the pillar test files (tests/test_air.py::TestProvenanceShape, etc).
"""

from __future__ import annotations

import pytest

from engine.core.provenance import (
    _ALLOWED_COLUMN_TO_SURFACE_UNCERTAINTY,
    _ALLOWED_DATA_TYPES,
    _ALLOWED_OBSERVATION_UNITS,
    _ALLOWED_TEMPORAL_MODES,
    build_provenance,
)


_CANONICAL_KEYS = [
    "indicator_id",
    "asset_id", "band", "data_type", "data_source",
    "native_scale_m", "method_note", "time_range",
    "coverage_window", "skipped_reason", "observations",
    "column_to_surface_uncertainty", "temporal_mode",
    "sector_signal_anomaly", "extra",
]


class TestBuildProvenance:
    def test_returns_canonical_field_order(self) -> None:
        # Insertion order matters for downstream rendering (audit logs,
        # P-05 UI). If this test fails, the field order in build_provenance
        # has drifted from the documented schema.
        result = build_provenance(
            indicator_id="air.no2",
            asset_id="A",
            band="b",
            data_type="satellite_observation",
            data_source="ESA",
            native_scale_m=1000.0,
            time_range=("2023-01-01", "2023-04-01"),
        )
        assert list(result.keys()) == _CANONICAL_KEYS

    def test_extra_defaults_to_empty_dict_not_none(self) -> None:
        # Empty dict (rather than None) means downstream code can always
        # call `prov["extra"].get(...)` without a None-guard.
        result = build_provenance(
            indicator_id="nature.kba",
            asset_id="A", band=None, data_type="reference_dataset",
            data_source="X", native_scale_m=1.0,
            time_range=("2023-01-01", "2023-04-01"),
        )
        assert result["extra"] == {}

    def test_rejects_unknown_data_type(self) -> None:
        with pytest.raises(ValueError, match="unknown data_type"):
            build_provenance(
                indicator_id="air.no2",
                asset_id="A", band=None, data_type="bogus_type",
                data_source="X", native_scale_m=1.0,
                time_range=("2023-01-01", "2023-04-01"),
            )

    def test_rejects_unknown_observation_unit(self) -> None:
        with pytest.raises(ValueError, match="unknown observations.unit"):
            build_provenance(
                indicator_id="air.no2",
                asset_id="A", band=None, data_type="satellite_observation",
                data_source="X", native_scale_m=1.0,
                time_range=("2023-01-01", "2023-04-01"),
                observations={"count": 3, "unit": "weekly_grids"},
            )

    def test_rejects_negative_observation_count(self) -> None:
        with pytest.raises(ValueError, match="observations.count"):
            build_provenance(
                indicator_id="air.no2",
                asset_id="A", band=None, data_type="satellite_observation",
                data_source="X", native_scale_m=1.0,
                time_range=("2023-01-01", "2023-04-01"),
                observations={"count": -1, "unit": "daily_images"},
            )

    def test_accepts_zero_count_for_skip_path(self) -> None:
        # ODIAC's out-of-coverage skip uses observations.count=0; not an error.
        result = build_provenance(
            indicator_id="ghg.co2",
            asset_id="A", band=None, data_type="emissions_inventory_allocation",
            data_source="X", native_scale_m=1.0,
            time_range=("2026-01-01", "2026-04-01"),
            skipped_reason="out_of_coverage",
            observations={"count": 0, "unit": "monthly_grids"},
        )
        assert result["observations"]["count"] == 0
        assert result["skipped_reason"] == "out_of_coverage"

    def test_all_recognised_data_types_accepted(self) -> None:
        # Every value in _ALLOWED_DATA_TYPES round-trips without raising.
        for dt in _ALLOWED_DATA_TYPES:
            result = build_provenance(
                indicator_id="air.no2",
                asset_id="A", band=None, data_type=dt,
                data_source="X", native_scale_m=1.0,
                time_range=("2023-01-01", "2023-04-01"),
            )
            assert result["data_type"] == dt

    def test_all_recognised_observation_units_accepted(self) -> None:
        # Every value in _ALLOWED_OBSERVATION_UNITS is constructable.
        for unit in _ALLOWED_OBSERVATION_UNITS:
            result = build_provenance(
                indicator_id="air.no2",
                asset_id="A", band=None, data_type="satellite_observation",
                data_source="X", native_scale_m=1.0,
                time_range=("2023-01-01", "2023-04-01"),
                observations={"count": 1, "unit": unit},
            )
            assert result["observations"]["unit"] == unit

    # M-V1x-RECONCILE additions ----------------------------------------------

    def test_indicator_id_required(self) -> None:
        with pytest.raises(TypeError, match="indicator_id"):
            build_provenance(            # type: ignore[call-arg]
                asset_id="A", band=None, data_type="satellite_observation",
                data_source="X", native_scale_m=1.0,
                time_range=("2023-01-01", "2023-04-01"),
            )

    def test_column_to_surface_uncertainty_autoderives_from_indicator_id(self) -> None:
        no2 = build_provenance(
            indicator_id="air.no2",
            asset_id="A", band="b", data_type="satellite_observation",
            data_source="X", native_scale_m=1.0,
            time_range=("2023-01-01", "2023-04-01"),
        )
        assert no2["column_to_surface_uncertainty"] == "moderate"

        ch4 = build_provenance(
            indicator_id="ghg.ch4",
            asset_id="A", band="b", data_type="satellite_observation",
            data_source="X", native_scale_m=1.0,
            time_range=("2023-01-01", "2023-04-01"),
        )
        assert ch4["column_to_surface_uncertainty"] == "weak"

        kba = build_provenance(
            indicator_id="nature.kba",
            asset_id="A", band=None, data_type="reference_dataset",
            data_source="X", native_scale_m=0.0,
            time_range=("static", "static"),
        )
        assert kba["column_to_surface_uncertainty"] == "n_a"

    def test_temporal_mode_autoderives_standing_exposure_for_odiac_and_hansen(self) -> None:
        co2 = build_provenance(
            indicator_id="ghg.co2",
            asset_id="A", band="b1", data_type="emissions_inventory_allocation",
            data_source="X", native_scale_m=1000.0,
            time_range=("2023-01-01", "2023-12-31"),
        )
        assert co2["temporal_mode"] == "standing_exposure"

        hansen = build_provenance(
            indicator_id="nature.forest_loss",
            asset_id="A", band="lossyear", data_type="reference_dataset",
            data_source="X", native_scale_m=30.0,
            time_range=("2023-01-01", "2023-12-31"),
        )
        assert hansen["temporal_mode"] == "standing_exposure"

        ndvi = build_provenance(
            indicator_id="nature.ndvi",
            asset_id="A", band="NDVI", data_type="satellite_observation",
            data_source="X", native_scale_m=250.0,
            time_range=("2023-01-01", "2023-04-01"),
        )
        assert ndvi["temporal_mode"] == "live_window"

    def test_sector_signal_anomaly_defaults_none_in_v1(self) -> None:
        result = build_provenance(
            indicator_id="ghg.ch4",
            asset_id="A", band="b", data_type="satellite_observation",
            data_source="X", native_scale_m=1.0,
            time_range=("2023-01-01", "2023-04-01"),
        )
        assert result["sector_signal_anomaly"] is None

    def test_rejects_unknown_column_to_surface_uncertainty(self) -> None:
        with pytest.raises(ValueError, match="column_to_surface_uncertainty"):
            build_provenance(
                indicator_id="air.no2",
                asset_id="A", band="b", data_type="satellite_observation",
                data_source="X", native_scale_m=1.0,
                time_range=("2023-01-01", "2023-04-01"),
                column_to_surface_uncertainty="extremely_uncertain",
            )

    def test_rejects_unknown_temporal_mode(self) -> None:
        with pytest.raises(ValueError, match="temporal_mode"):
            build_provenance(
                indicator_id="air.no2",
                asset_id="A", band="b", data_type="satellite_observation",
                data_source="X", native_scale_m=1.0,
                time_range=("2023-01-01", "2023-04-01"),
                temporal_mode="continuous_realtime",
            )

    def test_all_recognised_column_to_surface_uncertainty_accepted(self) -> None:
        for v in _ALLOWED_COLUMN_TO_SURFACE_UNCERTAINTY:
            result = build_provenance(
                indicator_id="air.no2",
                asset_id="A", band="b", data_type="satellite_observation",
                data_source="X", native_scale_m=1.0,
                time_range=("2023-01-01", "2023-04-01"),
                column_to_surface_uncertainty=v,
            )
            assert result["column_to_surface_uncertainty"] == v

    def test_all_recognised_temporal_modes_accepted(self) -> None:
        for v in _ALLOWED_TEMPORAL_MODES:
            result = build_provenance(
                indicator_id="air.no2",
                asset_id="A", band="b", data_type="satellite_observation",
                data_source="X", native_scale_m=1.0,
                time_range=("2023-01-01", "2023-04-01"),
                temporal_mode=v,
            )
            assert result["temporal_mode"] == v
