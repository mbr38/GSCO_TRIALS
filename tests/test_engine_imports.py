"""Milestone 1 smoke test.

Confirms `engine.constants` and `engine.ids` import cleanly and that a small
set of structural invariants hold. Catches the kinds of mistakes (typo'd ID,
weight dict that doesn't sum to 1, accidentally-overlapping DW buckets) that
would silently propagate through later milestones.
"""

from __future__ import annotations

import math

from engine import constants, ids


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

def test_modules_import_cleanly() -> None:
    assert constants is not None
    assert ids is not None


# ---------------------------------------------------------------------------
# engine.constants invariants
# ---------------------------------------------------------------------------

def test_traffic_light_thresholds_are_strictly_increasing_within_unit_interval() -> None:
    lo, hi = constants.TRAFFIC_LIGHT_THRESHOLDS
    assert 0.0 < lo < hi < 1.0


def test_air_pollution_proxy_weights_sum_to_one() -> None:
    total = sum(constants.AIR_POLLUTION_PROXY_WEIGHTS.values())
    assert math.isclose(total, 1.0, abs_tol=1e-9), f"sum was {total}"


def test_air_followup_weights_sum_to_one() -> None:
    total = sum(constants.AIR_FOLLOWUP_WEIGHTS.values())
    assert math.isclose(total, 1.0, abs_tol=1e-9), f"sum was {total}"


def test_core_ghg_audit_support_weights_sum_to_one() -> None:
    total = sum(constants.CORE_GHG_AUDIT_SUPPORT_WEIGHTS.values())
    assert math.isclose(total, 1.0, abs_tol=1e-9), f"sum was {total}"


def test_ghg_data_quality_attribution_weights_sum_to_one() -> None:
    # IC_v4 §2.3 corrected v3's broken rescale (sum 0.90 → 1.00).
    total = sum(constants.GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS.values())
    assert math.isclose(total, 1.0, abs_tol=1e-9), f"sum was {total}"


def test_ghg_data_quality_attribution_weight_keys_match_v1_quality_ids() -> None:
    # The dict keys must be exactly the four canonical v1 quality IDs.
    assert set(constants.GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS.keys()) == set(
        ids.GHG_QUALITY_SUB_SCORES
    )


def test_air_pollutant_weights_alias_matches_canonical_dict() -> None:
    # Skeleton §2.1 imports AIR_POLLUTANT_WEIGHTS; §5 defines the same dict
    # as AIR_POLLUTION_PROXY_WEIGHTS. The alias keeps both names live.
    assert constants.AIR_POLLUTANT_WEIGHTS is constants.AIR_POLLUTION_PROXY_WEIGHTS


def test_dw_class_buckets_are_disjoint() -> None:
    natural = set(constants.DW_NATURAL_CLASSES)
    non_natural = set(constants.DW_NON_NATURAL_CLASSES)
    excluded = set(constants.DW_EXCLUDED_CLASSES)
    water = {constants.DW_WATER_CLASS}
    buckets = [natural, non_natural, excluded, water]
    for i, a in enumerate(buckets):
        for b in buckets[i + 1:]:
            assert a.isdisjoint(b), f"overlap between {a} and {b}"


# ---------------------------------------------------------------------------
# engine.ids invariants
# ---------------------------------------------------------------------------

def test_make_id_with_and_without_measurement() -> None:
    assert ids.make_id("air", "no2", "site") == "air.no2.site"
    assert ids.make_id("nature", "vegetation_condition") == "nature.vegetation_condition"


def test_all_indicator_ids_is_a_nonempty_frozenset() -> None:
    assert isinstance(ids.ALL_INDICATOR_IDS, frozenset)
    assert len(ids.ALL_INDICATOR_IDS) > 0


def test_known_canonical_ids_are_present() -> None:
    must_contain = (
        # Air — single-value × measurements
        "air.no2.site",
        "air.no2.score",
        "air.o3.site",
        "air.o3.score",
        # Air — sub-aggregates and pillar aggregates
        "air.pm_or_aerosol",
        "air.pollution_proxy_score",
        "air.audit_followup_priority",
        # GHG — three different measurement shapes (§3.1)
        "ghg.ch4.score",
        "ghg.co2.mean",
        "ghg.co2.total",
        "ghg.viirs.site",
        "ghg.audit_followup_priority",
        # GHG quality sub-scores — promoted to v1 in schema v2 (Bug 1 fix)
        "ghg.temporal_coverage",
        "ghg.spatial_resolution_suitability",
        "ghg.retrieval_inventory_quality",
        "ghg.nearby_source_isolation",
        # Nature — KBA / DW / habitat / aggregates
        "nature.kba.proximity_score",
        "nature.dw.trees_pct",
        "nature.dw.shrub_ha",          # shrub_and_scrub → shrub slug
        "nature.dw.flooded_veg_pct",   # flooded_vegetation → flooded_veg slug
        "nature.dw.snow_ha",           # snow_and_ice → snow slug
        "nature.habitat.conversion_score",
        # Nature sub-aggregates (schema v2 §4.9, Bug 2 fix)
        "nature.biodiversity_exposure",
        "nature.vegetation_condition",
        "nature.followup_priority",
        # Composite
        "composite.overall_screening",
        "composite.confidence",
    )
    missing = [i for i in must_contain if i not in ids.ALL_INDICATOR_IDS]
    assert not missing, f"missing canonical IDs: {missing}"


def test_reserved_v1x_ids_are_not_in_all_indicator_ids() -> None:
    overlap = ids.RESERVED_FOR_V1X & ids.ALL_INDICATOR_IDS
    assert not overlap, f"reserved IDs leaking into v1: {overlap}"


def test_schema_v2_bug1_ghg_quality_promoted_to_v1() -> None:
    # The four IDs were wrongly listed as v1.x deferred in schema v1 §3.4.
    # Schema v2 promotes them — they must be in v1 indicators and OUT of reserved.
    promoted = {
        "ghg.temporal_coverage",
        "ghg.spatial_resolution_suitability",
        "ghg.retrieval_inventory_quality",
        "ghg.nearby_source_isolation",
    }
    assert promoted.issubset(ids.ALL_INDICATOR_IDS)
    assert promoted.isdisjoint(ids.RESERVED_FOR_V1X)
    assert set(ids.GHG_QUALITY_SUB_SCORES) == promoted


def test_schema_v2_bug2_biodiversity_exposure_is_sub_aggregate_not_quality() -> None:
    # Was wrongly grouped in §4.8 quality in schema v1; v2 moves it to §4.9.
    assert "nature.biodiversity_exposure" in ids.NATURE_SUB_AGGREGATES
    assert "nature.biodiversity_exposure" not in ids.NATURE_QUALITY


def test_nature_sub_aggregates_contains_the_three_followup_terms() -> None:
    # IC_v4 §3.3: the three exposure-side terms that feed nature.followup_priority.
    assert set(ids.NATURE_SUB_AGGREGATES) == {
        "nature.biodiversity_exposure",
        "nature.habitat.conversion_score",
        "nature.vegetation_condition",
    }
    # The latter two also remain in their domain groups (schema v2 §4.9 note).
    assert "nature.habitat.conversion_score" in ids.NATURE_HABITAT
    assert "nature.vegetation_condition" in ids.NATURE_NDVI


def test_is_valid_id_accepts_canonical_and_rejects_bogus() -> None:
    assert ids.is_valid_id("air.no2.score") is True
    assert ids.is_valid_id("air.no2.bogus") is False


def test_pillar_order_excludes_composite_and_matches_three_pillars() -> None:
    # CLAUDE.md §7 fixes the order; composite is computed last, not a pillar.
    assert ids.PILLAR_ORDER == ("air", "ghg", "nature")
    assert ids.PILLAR_COMPOSITE not in ids.PILLAR_ORDER
