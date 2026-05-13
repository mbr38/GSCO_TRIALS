"""Synthetic-payload tests for engine.core.repeatable_core.

Pure-math functions only. The EE-touching functions (`site_value`,
`background_value`, `six_step`) are deferred to milestone 3+ with real
integration tests against known clean/industrial reference points.
"""

from __future__ import annotations

import pytest

from engine.constants import ANOMALY_Z_THRESHOLD
from engine.core.repeatable_core import anomaly_z_hf
from engine.exceptions import IndicatorComputeError, PillarComputeError


class TestAnomalyZHfHappyPath:
    def test_site_equals_background_gives_zero_signal(self) -> None:
        result = anomaly_z_hf(
            site=5.0, bg_median=5.0, bg_std=1.0,
            time_series=[5.0, 5.0, 5.0],
        )
        assert result["anomaly"] == 0.0
        assert result["z"] == 0.0
        assert result["hf"] == 0.0

    def test_z_is_anomaly_divided_by_std(self) -> None:
        result = anomaly_z_hf(
            site=8.0, bg_median=5.0, bg_std=1.5, time_series=[5.0],
        )
        assert result["anomaly"] == pytest.approx(3.0)
        assert result["z"] == pytest.approx(2.0)

    def test_hf_counts_dates_at_or_above_threshold(self) -> None:
        # bg=5, std=1, z_threshold=2 → anomaly observation requires value ≥ 7.
        # 4 of these 10 dates qualify.
        series = [3, 4, 5, 5, 6, 7, 8, 9, 7.5, 5]
        result = anomaly_z_hf(
            site=6.0, bg_median=5.0, bg_std=1.0,
            time_series=series, z_threshold=2.0,
        )
        assert result["hf"] == pytest.approx(4 / 10)

    def test_default_z_threshold_pulled_from_constants(self) -> None:
        # Two values exactly at 2σ → both count.
        series = [7.0, 7.0]
        result = anomaly_z_hf(
            site=7.0, bg_median=5.0, bg_std=1.0, time_series=series,
        )
        assert ANOMALY_Z_THRESHOLD == 2.0
        assert result["hf"] == 1.0

    def test_negative_anomaly_still_returns_signed_z(self) -> None:
        # "Higher is worse" direction is enforced by to_score, not anomaly_z_hf;
        # the raw anomaly/z here keep their signs.
        result = anomaly_z_hf(
            site=2.0, bg_median=5.0, bg_std=1.0, time_series=[2.0],
        )
        assert result["anomaly"] == pytest.approx(-3.0)
        assert result["z"] == pytest.approx(-3.0)
        # No date in the series clears the +2σ threshold:
        assert result["hf"] == 0.0


class TestAnomalyZHfEdgeCases:
    def test_zero_std_returns_anomaly_but_no_z_or_hf(self) -> None:
        result = anomaly_z_hf(
            site=7.0, bg_median=5.0, bg_std=0.0, time_series=[5.0, 6.0],
        )
        assert result["anomaly"] == 2.0
        assert result["z"] is None
        assert result["hf"] is None

    def test_negative_std_treated_as_degenerate(self) -> None:
        # σ is non-negative by construction; defensive against numerical slop.
        result = anomaly_z_hf(
            site=7.0, bg_median=5.0, bg_std=-0.1, time_series=[5.0],
        )
        assert result["z"] is None
        assert result["hf"] is None

    def test_empty_time_series_keeps_anomaly_and_z_but_drops_hf(self) -> None:
        result = anomaly_z_hf(
            site=7.0, bg_median=5.0, bg_std=1.0, time_series=[],
        )
        assert result["anomaly"] == 2.0
        assert result["z"] == 2.0
        assert result["hf"] is None

    def test_all_identical_values_yield_zero_hf(self) -> None:
        result = anomaly_z_hf(
            site=5.0, bg_median=5.0, bg_std=1.0,
            time_series=[5.0] * 5,
        )
        assert result["hf"] == 0.0

    def test_iterable_input_accepted(self) -> None:
        # Generators / iterators must be supported (the orchestrator passes
        # mapped values, not always lists).
        result = anomaly_z_hf(
            site=7.0, bg_median=5.0, bg_std=1.0,
            time_series=(v for v in [7.0, 7.0]),
        )
        assert result["hf"] == 1.0


class TestExceptionTypes:
    def test_indicator_compute_error_carries_id_and_reason(self) -> None:
        err = IndicatorComputeError(indicator_id="air.no2", reason="no pixels")
        assert err.indicator_id == "air.no2"
        assert err.reason == "no pixels"
        assert "air.no2" in str(err)
        assert "no pixels" in str(err)

    def test_pillar_compute_error_carries_affected_ids(self) -> None:
        err = PillarComputeError(
            pillar="air",
            indicator_ids=["air.no2.score", "air.so2.score"],
            reason="EE unavailable",
        )
        assert err.pillar == "air"
        assert err.indicator_ids == ["air.no2.score", "air.so2.score"]
        assert "air" in str(err)


# ---------------------------------------------------------------------------
# Deferred — real EE integration tests live in milestone 3+.
# Stubs are kept so future runs surface them as skipped (not missing).
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="real EE integration test — see milestone 3")
def test_site_value_against_known_clean_rural_point() -> None:
    """E.g. a mid-Atlantic Ocean point should give near-zero NO₂."""


@pytest.mark.skip(reason="real EE integration test — see milestone 3")
def test_background_value_against_known_industrial_point() -> None:
    """E.g. Ruhr valley NO₂ background statistics in a 25 km ring."""


@pytest.mark.skip(reason="real EE integration test — see milestone 3")
def test_six_step_end_to_end_for_no2_at_known_industrial_point() -> None:
    """Full six-step run; assert composite shape and plausible score band."""
