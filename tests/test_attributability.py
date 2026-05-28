"""Unit tests for engine.core.attributability (M-ATTRIB-A1 §7.1).

Pure, EE-free: the categorical bucketing of the supplier→centroid offset
and the haversine helper. Boundary cases per AT12.
"""

from __future__ import annotations

import pytest

from engine.constants import (
    HABITAT_SPATIAL_LINK_HIGH_KM,
    HABITAT_SPATIAL_LINK_MOD_KM,
    N_MIN_PIXELS_FOR_CENTROID,
)
from engine.core.attributability import (
    ATTRIBUTABILITY_STATES,
    compute_habitat_attributability,
    haversine_km,
)


# ---------------------------------------------------------------------------
# compute_habitat_attributability — bucket boundaries (AT12)
# ---------------------------------------------------------------------------

class TestHabitatAttributabilityBuckets:
    @pytest.mark.parametrize("offset_km,expected", [
        (0.0,  "high"),
        (0.5,  "high"),
        (1.0,  "high"),       # boundary: ≤ HIGH → high
        (1.0001, "moderate"),
        (1.5,  "moderate"),
        (3.0,  "moderate"),   # boundary: ≤ MOD → moderate
        (3.0001, "low"),
        (3.5,  "low"),
        (10.0, "low"),
    ])
    def test_distance_buckets_with_enough_pixels(self, offset_km, expected):
        assert compute_habitat_attributability(offset_km, 20) == expected

    def test_high_boundary_uses_constant(self):
        assert compute_habitat_attributability(
            HABITAT_SPATIAL_LINK_HIGH_KM, 20,
        ) == "high"

    def test_moderate_boundary_uses_constant(self):
        assert compute_habitat_attributability(
            HABITAT_SPATIAL_LINK_MOD_KM, 20,
        ) == "moderate"

    def test_sparse_when_below_n_min_regardless_of_distance(self):
        assert compute_habitat_attributability(0.5, N_MIN_PIXELS_FOR_CENTROID - 1) == "sparse"
        assert compute_habitat_attributability(0.5, 0) == "sparse"

    def test_sparse_at_n_min_boundary_is_not_sparse(self):
        # n_change_pixels == n_min is sufficient (the gate is `< n_min`).
        assert compute_habitat_attributability(0.5, N_MIN_PIXELS_FOR_CENTROID) == "high"

    def test_sparse_when_centroid_offset_none(self):
        assert compute_habitat_attributability(None, 50) == "sparse"

    def test_sparse_when_both_none_and_low_pixels(self):
        assert compute_habitat_attributability(None, 3) == "sparse"

    def test_negative_distance_treated_as_sparse(self):
        # Distances are ≥ 0; a negative value is nonsensical → sparse, not
        # silently bucketed as "high".
        assert compute_habitat_attributability(-1.0, 50) == "sparse"

    def test_custom_thresholds_respected(self):
        assert compute_habitat_attributability(
            2.0, 50, high_threshold_km=5.0, moderate_threshold_km=20.0,
        ) == "high"
        assert compute_habitat_attributability(
            8.0, 50, high_threshold_km=5.0, moderate_threshold_km=20.0,
        ) == "moderate"

    def test_every_result_is_a_valid_state(self):
        for offset, n in [(0.5, 20), (2.0, 20), (5.0, 20), (None, 1)]:
            assert compute_habitat_attributability(offset, n) in ATTRIBUTABILITY_STATES


# ---------------------------------------------------------------------------
# haversine_km — geodesic distance
# ---------------------------------------------------------------------------

class TestHaversine:
    def test_zero_distance_for_identical_points(self):
        assert haversine_km(-13.5, -58.8, -13.5, -58.8) == pytest.approx(0.0)

    def test_one_degree_longitude_at_equator(self):
        # 1° of longitude at the equator ≈ 111.19 km.
        assert haversine_km(0.0, 0.0, 0.0, 1.0) == pytest.approx(111.19, abs=0.5)

    def test_one_degree_latitude(self):
        # 1° of latitude ≈ 111.19 km everywhere.
        assert haversine_km(0.0, 0.0, 1.0, 0.0) == pytest.approx(111.19, abs=0.5)

    def test_symmetry(self):
        a = haversine_km(-13.5, -58.8, -13.6, -58.9)
        b = haversine_km(-13.6, -58.9, -13.5, -58.8)
        assert a == pytest.approx(b)

    def test_small_offset_is_a_few_km(self):
        # ~0.05° offset near a tropical supplier → single-digit km.
        d = haversine_km(-13.5, -58.8, -13.55, -58.83)
        assert 0.0 < d < 10.0
