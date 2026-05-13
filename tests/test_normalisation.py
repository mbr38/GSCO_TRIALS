"""Tests for engine.core.normalisation.to_score (IC_v4 §0.4)."""

from __future__ import annotations

import pytest

from engine.constants import NORMALISATION_K
from engine.core.normalisation import to_score


class TestHigherIsWorse:
    def test_value_at_background_scores_zero(self) -> None:
        assert to_score(value=5.0, bg_median=5.0, bg_std=1.0) == 0.0

    def test_value_one_sigma_above_scores_one_third_with_default_k(self) -> None:
        # raw = 1·σ, denom = k·σ = 3σ → score = 1/3
        score = to_score(value=6.0, bg_median=5.0, bg_std=1.0)
        assert score == pytest.approx(1 / 3)

    def test_value_k_sigma_above_saturates_to_one(self) -> None:
        score = to_score(value=5.0 + NORMALISATION_K, bg_median=5.0, bg_std=1.0)
        assert score == 1.0

    def test_value_far_above_clamps_to_one(self) -> None:
        assert to_score(value=100.0, bg_median=5.0, bg_std=1.0) == 1.0

    def test_value_below_background_clamps_to_zero(self) -> None:
        assert to_score(value=3.0, bg_median=5.0, bg_std=1.0) == 0.0


class TestLowerIsWorse:
    def test_value_one_sigma_below_scores_one_third_with_default_k(self) -> None:
        score = to_score(
            value=4.0, bg_median=5.0, bg_std=1.0, direction="lower_is_worse",
        )
        assert score == pytest.approx(1 / 3)

    def test_value_k_sigma_below_saturates_to_one(self) -> None:
        score = to_score(
            value=5.0 - NORMALISATION_K, bg_median=5.0, bg_std=1.0,
            direction="lower_is_worse",
        )
        assert score == 1.0

    def test_value_above_background_clamps_to_zero(self) -> None:
        score = to_score(
            value=10.0, bg_median=5.0, bg_std=1.0, direction="lower_is_worse",
        )
        assert score == 0.0


class TestEdgeCases:
    def test_zero_bg_std_returns_none(self) -> None:
        assert to_score(value=10.0, bg_median=5.0, bg_std=0.0) is None

    def test_negative_bg_std_returns_none(self) -> None:
        # σ is non-negative by construction; defensive guard against
        # numerically negative input.
        assert to_score(value=10.0, bg_median=5.0, bg_std=-1.0) is None

    def test_custom_k_changes_saturation_point(self) -> None:
        # With k=1, raw = 1σ saturates immediately.
        assert to_score(value=6.0, bg_median=5.0, bg_std=1.0, k=1.0) == 1.0

    def test_default_k_matches_constants_module(self) -> None:
        # 3σ exceedance saturates → confirms the default k pulled from constants.
        assert (
            to_score(value=5.0 + 3.0, bg_median=5.0, bg_std=1.0) == 1.0
            and NORMALISATION_K == 3.0
        )
