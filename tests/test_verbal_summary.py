"""Tests for engine.verbal_summary (M-UI-E.0).

Coverage:
- Bucketing (boundaries, None propagation).
- Dominant-contributor lookup per pillar (above/below threshold,
  tie-breaks, empty payloads).
- Dominant-pillar resolution for the overview.
- Limiting-factor lookup per pillar.
- Per-pillar dominant-slot formatters.
- Template selection across spot-checked (pillar, priority, confidence,
  path) combinations.
- End-to-end worked example from
  docs/Verbal_Summary_Templates_v1.md §9 — the canonical regression test.
- End-to-end on a realistic engine-shaped payload.
- Direction-stripping when {dominant_direction} is None.

Pure-Python; no EE, no Streamlit.
"""

from __future__ import annotations

import pytest

from engine.verbal_summary import (
    VerbalSummary,
    _AIR_DOMINANT_CANDIDATES,
    _GHG_DOMINANT_CANDIDATES,
    _NATURE_DOMINANT_CANDIDATES,
    _OVERVIEW_TEMPLATES,
    _PER_PILLAR_TEMPLATES,
    _air_dominant_slots,
    _bucket,
    _composite_shape,
    _ghg_dominant_slots,
    _moderate_pillar_list_phrase,
    _nature_dominant_slots,
    _render_pillar,
    _resolve_air_limiting_factor,
    _resolve_dominant,
    _resolve_quality_limiting_factor,
    _GHG_LIMITING_FACTOR_PROSE,
    _NATURE_LIMITING_FACTOR_PROSE,
    generate_verbal_summary,
)


# ---------------------------------------------------------------------------
# Bucketing  (doc §1)
# ---------------------------------------------------------------------------

class TestBucket:
    def test_exact_high_threshold_is_high(self) -> None:
        # Doc §1 — 0.66 exactly lands in "high".
        assert _bucket(0.66) == "high"

    def test_just_below_high_is_moderate(self) -> None:
        assert _bucket(0.659) == "moderate"

    def test_exact_low_threshold_is_moderate(self) -> None:
        # 0.33 exactly lands in "moderate".
        assert _bucket(0.33) == "moderate"

    def test_just_below_low_is_low(self) -> None:
        assert _bucket(0.329) == "low"

    def test_zero_is_low(self) -> None:
        assert _bucket(0.0) == "low"

    def test_one_is_high(self) -> None:
        assert _bucket(1.0) == "high"

    def test_none_propagates(self) -> None:
        assert _bucket(None) is None


# ---------------------------------------------------------------------------
# Dominant-contributor lookup  (doc §3)
# ---------------------------------------------------------------------------

class TestResolveDominant:
    def test_air_no2_dominant_when_share_above_threshold(self) -> None:
        # NO₂ contribution 0.30·0.8 = 0.24; others tiny → share well above 0.40.
        payload = {
            "air.no2.score":     0.8,
            "air.so2.score":     0.05,
            "air.co.score":      0.05,
            "air.hcho.score":    0.05,
            "air.pm_or_aerosol": 0.05,
            "air.o3.score":      0.05,
        }
        result = _resolve_dominant(payload, _AIR_DOMINANT_CANDIDATES)
        assert result is not None
        assert result[0] == "air.no2.score"
        assert result[1] == "NO₂"

    def test_air_no_dominant_when_all_balanced(self) -> None:
        # All six pollutants equal → top share = 0.30 < 0.40 threshold.
        payload = {
            "air.no2.score":     0.5,
            "air.so2.score":     0.5,
            "air.co.score":      0.5,
            "air.hcho.score":    0.5,
            "air.pm_or_aerosol": 0.5,
            "air.o3.score":      0.5,
        }
        assert _resolve_dominant(payload, _AIR_DOMINANT_CANDIDATES) is None

    def test_ghg_co2_dominant_when_share_above_threshold(self) -> None:
        payload = {
            "ghg.co2_context":          0.9,
            "ghg.ch4_context_adjusted": 0.1,
            "ghg.combustion_proxy":     0.1,
            "ghg.activity_score":       0.1,
        }
        result = _resolve_dominant(payload, _GHG_DOMINANT_CANDIDATES)
        assert result is not None
        assert result[0] == "ghg.co2_context"

    def test_ghg_below_threshold_returns_none(self) -> None:
        # M-CH4-A1: candidates are co2 (0.39), combustion (0.22), activity (0.11).
        # Choose scores that make the three weight×value contributions roughly
        # equal so the top share stays below the 0.40 dominant threshold:
        #   co2 0.39·0.28 = 0.1092; combustion 0.22·0.50 = 0.110;
        #   activity 0.11·1.00 = 0.110; total ≈ 0.329; max share ≈ 0.334 < 0.40.
        payload = {
            "ghg.co2_context":      0.28,
            "ghg.combustion_proxy": 0.50,
            "ghg.activity_score":   1.00,
        }
        result = _resolve_dominant(payload, _GHG_DOMINANT_CANDIDATES)
        assert result is None

    def test_nature_habitat_dominant(self) -> None:
        payload = {
            "nature.biodiversity_exposure":    0.1,
            "nature.habitat.conversion_score": 0.9,
            "nature.vegetation_condition":     0.1,
        }
        result = _resolve_dominant(payload, _NATURE_DOMINANT_CANDIDATES)
        assert result is not None
        assert result[0] == "nature.habitat.conversion_score"

    def test_empty_payload_returns_none(self) -> None:
        assert _resolve_dominant({}, _AIR_DOMINANT_CANDIDATES) is None

    def test_zero_total_returns_none(self) -> None:
        # All scores 0 → total = 0 → division-by-zero guard.
        payload = {k: 0.0 for k in _AIR_DOMINANT_CANDIDATES}
        assert _resolve_dominant(payload, _AIR_DOMINANT_CANDIDATES) is None

    def test_tie_break_prefers_higher_weight(self) -> None:
        # Two terms with identical contribution but different weights.
        # NO₂ (0.30) and SO₂ (0.20) — set their scores so the contributions
        # are equal: NO₂ 0.30·0.20 = 0.06, SO₂ 0.20·0.30 = 0.06.
        payload = {
            "air.no2.score":     0.20,
            "air.so2.score":     0.30,
            "air.co.score":      0.0,
            "air.hcho.score":    0.0,
            "air.pm_or_aerosol": 0.0,
            "air.o3.score":      0.0,
        }
        # Tie-break prefers higher raw weight → NO₂. But share check:
        # NO₂ 0.06 / total 0.12 = 0.50 > 0.40, so dominant fires.
        result = _resolve_dominant(payload, _AIR_DOMINANT_CANDIDATES)
        assert result is not None
        # Could be either NO₂ or SO₂ on contribution (tied); tie-break
        # by descending weight should pick NO₂.
        assert result[0] == "air.no2.score"


# ---------------------------------------------------------------------------
# Limiting-factor lookup  (doc §5)
# ---------------------------------------------------------------------------

class TestAirLimitingFactor:
    def test_picks_lowest_confidence_pollutant(self) -> None:
        payload = {
            "air.no2.confidence":  0.80,
            "air.so2.confidence":  0.31,  # Lowest.
            "air.co.confidence":   0.70,
            "air.hcho.confidence": 0.65,
        }
        result = _resolve_air_limiting_factor(payload)
        assert result == "weak retrieval quality for SO₂ at these concentrations"

    def test_returns_none_when_no_confidence_values(self) -> None:
        assert _resolve_air_limiting_factor({}) is None

    def test_handles_pm25_lowest(self) -> None:
        payload = {
            "air.no2.confidence":  0.80,
            "air.pm25.confidence": 0.40,  # Lowest.
        }
        result = _resolve_air_limiting_factor(payload)
        assert "CAMS PM₂.₅" in result


class TestQualityLimitingFactor:
    def test_ghg_picks_lowest_score(self) -> None:
        payload = {
            "ghg.temporal_coverage":              0.80,
            "ghg.spatial_resolution_suitability": 0.34,  # Lowest.
            "ghg.retrieval_inventory_quality":    0.70,
            "ghg.nearby_source_isolation":        0.85,
        }
        result = _resolve_quality_limiting_factor(
            payload, _GHG_LIMITING_FACTOR_PROSE,
        )
        assert result == "the coarse spatial resolution of the GHG retrievals relative to the buffer"

    def test_nature_picks_lowest_score(self) -> None:
        payload = {
            "nature.valid_pixel_coverage":      0.90,
            "nature.cloud_observation_quality": 0.60,
            "nature.dw.class_confidence":       0.85,
            "nature.seasonal_comparability":    0.20,  # Lowest.
            "nature.supplier_spatial_link":     0.70,
            "nature.external_driver_screening": 0.95,
        }
        result = _resolve_quality_limiting_factor(
            payload, _NATURE_LIMITING_FACTOR_PROSE,
        )
        assert result == "seasonal mismatch between the baseline and current composites"

    def test_returns_none_when_empty(self) -> None:
        assert _resolve_quality_limiting_factor(
            {}, _GHG_LIMITING_FACTOR_PROSE,
        ) is None


# ---------------------------------------------------------------------------
# Per-pillar dominant slot formatters  (doc §4)
# ---------------------------------------------------------------------------

class TestAirDominantSlots:
    def test_no2_positive_anomaly_direction_above(self) -> None:
        payload = {
            "air.no2.site":    42.0,
            "air.no2.z":       2.3,
            "air.no2.anomaly": 1.1e-5,
        }
        slots = _air_dominant_slots(payload, "air.no2.score", "NO₂")
        assert slots.value == "42 µmol m⁻²"
        assert slots.z == "2.3σ"
        assert slots.direction == "above"

    def test_no2_negative_anomaly_direction_at(self) -> None:
        payload = {
            "air.no2.site":    10.0,
            "air.no2.z":       -0.5,
            "air.no2.anomaly": -1e-6,
        }
        slots = _air_dominant_slots(payload, "air.no2.score", "NO₂")
        assert slots.direction == "at"

    def test_o3_uses_du_unit(self) -> None:
        payload = {"air.o3.site": 280.0, "air.o3.z": 1.0, "air.o3.anomaly": 5.0}
        slots = _air_dominant_slots(payload, "air.o3.score", "ozone (context)")
        assert "DU" in slots.value

    def test_pm_or_aerosol_resolves_to_pm25_when_present(self) -> None:
        payload = {
            "air.pm25.score":   0.5,
            "air.pm25.site":    25.0,
            "air.pm25.z":       1.5,
            "air.pm25.anomaly": 1e-8,
        }
        slots = _air_dominant_slots(payload, "air.pm_or_aerosol", "PM₂.₅ / aerosols")
        assert "µg m⁻³" in slots.value
        assert slots.direction == "above"


class TestGhgDominantSlots:
    def test_co2_uses_total_and_relative_intensity(self) -> None:
        payload = {
            "ghg.co2.total":              1_250_000.0,
            "ghg.co2.relative_intensity": 4.2,
        }
        slots = _ghg_dominant_slots(
            payload, "ghg.co2_context", "fossil CO₂ context (ODIAC)",
        )
        assert "1,250,000 t CO₂ yr⁻¹" in slots.value
        assert "4.2× the regional median" in slots.z
        assert slots.direction == "above"

    # M-CH4-A1: test_ch4_value_ppb_and_anomaly_z_string removed — CH₄ is
    # reference data and is no longer a dominant GHG contributor, so the
    # ghg.ch4_context_adjusted slot formatter no longer exists.

    def test_combustion_proxy_canned_phrase(self) -> None:
        payload = {"ghg.combustion_proxy": 0.48}
        slots = _ghg_dominant_slots(
            payload, "ghg.combustion_proxy", "combustion proxy (NO₂ + CO)",
        )
        assert slots.value == "score 0.48"
        assert slots.z == "combined NO₂ + CO signal"
        assert slots.direction is None

    def test_activity_score_uses_viirs_site_and_z(self) -> None:
        payload = {"ghg.viirs.site": 18.5, "ghg.viirs.z": 1.7}
        slots = _ghg_dominant_slots(
            payload, "ghg.activity_score", "nighttime-light activity",
        )
        assert "18.5 nW cm⁻² sr⁻¹" in slots.value
        assert "1.7σ above background" in slots.z

    def test_activity_score_falls_back_when_viirs_z_missing(self) -> None:
        # VIIRS lacks z in v1 (Schema_v2 §3.1 reduced 5-key set).
        payload = {"ghg.viirs.site": 18.5}
        slots = _ghg_dominant_slots(
            payload, "ghg.activity_score", "nighttime-light activity",
        )
        assert slots.z == "above the regional background"


class TestNatureDominantSlots:
    def test_biodiversity_inside_kba_uses_overlap(self) -> None:
        payload = {
            "nature.kba.overlap_pct": 24.0,
            "nature.kba.dist_km":     0.0,
        }
        slots = _nature_dominant_slots(
            payload, "nature.biodiversity_exposure",
            "proximity to Key Biodiversity Areas",
        )
        assert "24% of buffer overlaps a Key Biodiversity Area" in slots.value
        assert slots.direction is None

    def test_biodiversity_outside_kba_uses_distance(self) -> None:
        payload = {
            "nature.kba.overlap_pct": 0.0,
            "nature.kba.dist_km":     7.3,
        }
        slots = _nature_dominant_slots(
            payload, "nature.biodiversity_exposure",
            "proximity to Key Biodiversity Areas",
        )
        assert "7.3 km away" in slots.value

    def test_habitat_renders_three_clauses(self) -> None:
        payload = {
            "nature.habitat.natural_loss_ha":  12.4,
            "nature.habitat.natural_loss_pct": 2.5,
            "nature.habitat.annualised_rate":  2.5,
        }
        slots = _nature_dominant_slots(
            payload, "nature.habitat.conversion_score", "habitat conversion",
        )
        # Em-dash separators per doc §4.3 ("readable rather than nested parens").
        assert slots.value.count("—") == 2
        assert "12.4 ha" in slots.value
        assert "2.5% of buffer" in slots.value
        assert "2.5 ha yr⁻¹" in slots.value

    def test_vegetation_renders_anomaly_and_degraded_pct(self) -> None:
        payload = {
            "nature.ndvi.anomaly":  -0.07,
            "nature.low_ndvi.pct":  18.0,
        }
        slots = _nature_dominant_slots(
            payload, "nature.vegetation_condition", "vegetation condition",
        )
        assert "-0.07" in slots.value
        assert "18% of natural-cover pixels degraded" in slots.value


# ---------------------------------------------------------------------------
# Composite shape  (doc §7.1)
# ---------------------------------------------------------------------------

class TestCompositeShape:
    def test_all_low_returns_zero(self) -> None:
        assert _composite_shape(
            {"air": "low", "ghg": "low", "nature": "low"},
        ) == "0"

    def test_one_moderate_returns_m(self) -> None:
        assert _composite_shape(
            {"air": "moderate", "ghg": "low", "nature": "low"},
        ) == "M"

    def test_one_high_returns_one(self) -> None:
        assert _composite_shape(
            {"air": "high", "ghg": "low", "nature": "low"},
        ) == "1"

    def test_two_high_returns_two(self) -> None:
        assert _composite_shape(
            {"air": "high", "ghg": "high", "nature": "moderate"},
        ) == "2"

    def test_three_high_returns_three(self) -> None:
        assert _composite_shape(
            {"air": "high", "ghg": "high", "nature": "high"},
        ) == "3"


class TestModeratePillarListPhrase:
    def test_one_pillar(self) -> None:
        result = _moderate_pillar_list_phrase(["Air Pollution"])
        assert result == "Concern centres on Air Pollution"

    def test_two_pillars(self) -> None:
        result = _moderate_pillar_list_phrase(["Air Pollution", "GHG emissions"])
        assert result == "Concern centres on Air Pollution and GHG emissions"

    def test_three_pillars(self) -> None:
        result = _moderate_pillar_list_phrase(["a", "b", "c"])
        assert result == "Concern is spread across all three pillars"


# ---------------------------------------------------------------------------
# Template grid integrity  (doc §6 / §7)
# ---------------------------------------------------------------------------

class TestTemplateGrid:
    def test_per_pillar_grid_has_45_templates(self) -> None:
        # 3 pillars × (9 main + 6 fallback) = 45. Doc §6 header.
        assert len(_PER_PILLAR_TEMPLATES) == 45

    @pytest.mark.parametrize("pillar", ["air", "ghg", "nature"])
    def test_each_pillar_has_9_main_templates(self, pillar: str) -> None:
        main = [k for k in _PER_PILLAR_TEMPLATES if k[0] == pillar and k[3] == "main"]
        assert len(main) == 9

    @pytest.mark.parametrize("pillar", ["air", "ghg", "nature"])
    def test_each_pillar_has_6_fallback_templates(self, pillar: str) -> None:
        # Fallback only exists for high/moderate priority cells.
        fallback = [k for k in _PER_PILLAR_TEMPLATES if k[0] == pillar and k[3] == "fallback"]
        assert len(fallback) == 6

    def test_overview_grid_has_15_templates(self) -> None:
        # 5 shapes × 3 confidence buckets = 15. Doc §7.4 header.
        assert len(_OVERVIEW_TEMPLATES) == 15


# ---------------------------------------------------------------------------
# Per-pillar template selection — spot checks
# ---------------------------------------------------------------------------

class TestPillarTemplateSelection:
    def test_low_priority_picks_main_path(self) -> None:
        # Air low/low — no dominant resolution needed; "main" path fires
        # the low/low template (doc §6.2 says fallback doesn't exist for
        # low priority).
        payload = {
            "air.audit_followup_priority":      0.10,
            "air.measurement_quality_score": 0.20,
            "air.no2.confidence":               0.20,
        }
        rendered, template_id, bucket = _render_pillar("air", payload)
        assert bucket == "low"
        assert template_id == "air/low/low/main"
        assert "background levels" in rendered

    def test_high_priority_no_dominant_picks_fallback(self) -> None:
        # M-CH4-A1: three GHG candidates (co2/combustion/activity). Balance the
        # weight×value contributions so no single term's share clears 0.40 →
        # no dominant → fallback path. (Equal scores would let co2 dominate at
        # 0.39/0.72; instead make the contributions roughly equal.)
        payload = {
            "ghg.audit_followup_priority":  0.80,
            "ghg.data_quality_attribution": 0.80,
            "ghg.co2_context":              0.28,
            "ghg.combustion_proxy":         0.50,
            "ghg.activity_score":           1.00,
        }
        _, template_id, _ = _render_pillar("ghg", payload)
        assert template_id == "ghg/high/high/fallback"

    def test_high_priority_with_dominant_picks_main(self) -> None:
        payload = {
            "air.audit_followup_priority":      0.80,
            "air.measurement_quality_score": 0.80,
            "air.no2.score":     0.9,
            "air.no2.site":      42.0,
            "air.no2.z":         2.3,
            "air.no2.anomaly":   1.1e-5,
            "air.no2.confidence": 0.80,
            "air.so2.score":     0.05,
            "air.co.score":      0.05,
            "air.hcho.score":    0.05,
            "air.pm_or_aerosol": 0.05,
            "air.o3.score":      0.05,
        }
        rendered, template_id, _ = _render_pillar("air", payload)
        assert template_id == "air/high/high/main"
        assert "NO₂" in rendered

    def test_nature_low_high_path(self) -> None:
        payload = {
            "nature.followup_priority":    0.21,
            "nature.measurement_quality":  0.71,
        }
        rendered, template_id, _ = _render_pillar("nature", payload)
        assert template_id == "nature/low/high/main"
        assert rendered == (
            "Nature/Land is at baseline across the monitored land-cover "
            "indicators at this location. Data quality is high."
        )

    def test_moderate_moderate_fires_correct_template(self) -> None:
        # Build a payload that lands ghg in (moderate, moderate, main, ch4).
        payload = {
            "ghg.audit_followup_priority":  0.48,
            "ghg.data_quality_attribution": 0.50,
            "ghg.co2_context":              0.10,
            "ghg.ch4_context_adjusted":     0.50,
            "ghg.combustion_proxy":         0.10,
            "ghg.activity_score":           0.10,
            "ghg.ch4.site":                 1888.0,
            "ghg.ch4.anomaly":              0.42,
            "ghg.spatial_resolution_suitability": 0.34,
            "ghg.temporal_coverage":              0.80,
            "ghg.retrieval_inventory_quality":    0.70,
            "ghg.nearby_source_isolation":        0.85,
        }
        rendered, template_id, _ = _render_pillar("ghg", payload)
        assert template_id == "ghg/moderate/moderate/main"
        assert "contributing most" in rendered

    def test_moderate_low_fires_data_quality_phrasing(self) -> None:
        payload = {
            "air.audit_followup_priority":      0.50,
            "air.measurement_quality_score": 0.10,
            "air.no2.score":     0.9,
            "air.no2.site":      40.0,
            "air.no2.z":         1.5,
            "air.no2.anomaly":   1e-5,
            "air.no2.confidence": 0.10,
            "air.so2.score":     0.05,
            "air.co.score":      0.05,
            "air.hcho.score":    0.05,
            "air.pm_or_aerosol": 0.05,
            "air.o3.score":      0.05,
        }
        rendered, template_id, _ = _render_pillar("air", payload)
        assert template_id == "air/moderate/low/main"
        assert "data quality is poor" in rendered


# ---------------------------------------------------------------------------
# Direction stripping  (doc §8)
# ---------------------------------------------------------------------------

class TestDirectionStripping:
    def test_ghg_ch4_strips_orphan_background(self) -> None:
        # CH₄ slot has direction=None — the rendered prose must not
        # contain "  background" or " None background".
        payload = {
            "ghg.audit_followup_priority":  0.70,
            "ghg.data_quality_attribution": 0.70,
            "ghg.co2_context":              0.10,
            "ghg.ch4_context_adjusted":     0.50,
            "ghg.combustion_proxy":         0.10,
            "ghg.activity_score":           0.10,
            "ghg.ch4.site":                 1900.0,
            "ghg.ch4.anomaly":              5.0,
            "ghg.temporal_coverage":        0.80,
            "ghg.spatial_resolution_suitability": 0.85,
            "ghg.retrieval_inventory_quality":    0.80,
            "ghg.nearby_source_isolation":  0.85,
        }
        rendered, _, _ = _render_pillar("ghg", payload)
        assert "  background" not in rendered
        assert "None background" not in rendered
        # The CH₄ z-phrase ends at "above background)" — once, not twice.
        assert rendered.count("above background") == 1

    def test_nature_strips_when_direction_none(self) -> None:
        payload = {
            "nature.followup_priority":   0.70,
            "nature.measurement_quality": 0.80,
            "nature.biodiversity_exposure":    0.9,
            "nature.habitat.conversion_score": 0.05,
            "nature.vegetation_condition":     0.05,
            "nature.kba.overlap_pct": 24.0,
            "nature.kba.dist_km":     0.0,
        }
        rendered, _, _ = _render_pillar("nature", payload)
        assert "  background" not in rendered
        assert "None background" not in rendered

    def test_air_keeps_direction_phrase(self) -> None:
        # Air's direction is never None — the phrase stays intact.
        payload = {
            "air.audit_followup_priority":      0.80,
            "air.measurement_quality_score": 0.80,
            "air.no2.score":     0.9,
            "air.no2.site":      42.0,
            "air.no2.z":         2.3,
            "air.no2.anomaly":   1.1e-5,
            "air.no2.confidence": 0.80,
        }
        rendered, _, _ = _render_pillar("air", payload)
        assert "above background" in rendered


# ---------------------------------------------------------------------------
# End-to-end — worked example from doc §9
# ---------------------------------------------------------------------------

_WORKED_EXAMPLE_PAYLOAD: dict = {
    # Composite
    "composite.overall_screening": 0.58,
    "composite.confidence":        0.51,

    # Air — high priority, moderate confidence, NO₂ dominant.
    "air.audit_followup_priority":      0.72,
    "air.measurement_quality_score": 0.41,
    "air.no2.score":     0.55,
    "air.no2.site":      42.0,
    "air.no2.z":         2.3,
    "air.no2.anomaly":   1.1e-5,
    "air.no2.confidence": 0.80,
    "air.so2.score":     0.20,
    "air.so2.confidence": 0.31,   # Lowest → limiting factor.
    "air.co.score":      0.10,
    "air.co.confidence": 0.80,
    "air.hcho.score":    0.05,
    "air.o3.score":      0.05,
    "air.pm_or_aerosol": 0.05,

    # GHG — moderate priority, moderate confidence, CO₂ (ODIAC) dominant.
    # M-CH4-A1: CH₄ is reference data and is never a dominant contributor; with
    # CH₄ out, fossil CO₂ context (ODIAC) is the dominant GHG term here.
    "ghg.audit_followup_priority":   0.48,
    "ghg.data_quality_attribution":  0.62,
    "ghg.co2_context":               0.30,
    "ghg.combustion_proxy":          0.20,
    "ghg.activity_score":            0.10,
    "ghg.co2.total":                 12000.0,
    "ghg.co2.relative_intensity":    1.8,
    "ghg.spatial_resolution_suitability": 0.34,  # Lowest → limiting.
    "ghg.temporal_coverage":              0.80,
    "ghg.retrieval_inventory_quality":    0.70,
    "ghg.nearby_source_isolation":        0.85,

    # Nature — low priority, high confidence.
    "nature.followup_priority":   0.21,
    "nature.measurement_quality": 0.71,
}


_WORKED_EXAMPLE_OUTPUT = (
    "Overall priority is moderate (composite 0.58), driven by "
    "Air Pollution. Composite confidence is moderate.\n\n"

    "Air pollution is elevated at this location, driven primarily by "
    "NO₂ (42 µmol m⁻², 2.3σ above background). Confidence is moderate — "
    "interpretation is limited by weak retrieval quality for SO₂ at "
    "these concentrations.\n\n"

    "Greenhouse gases show moderate elevation at this location, with "
    "fossil CO₂ context (ODIAC) contributing most (12,000 t CO₂ yr⁻¹, "
    "1.8× the regional median above background). Confidence is mixed — the "
    "coarse spatial resolution of the GHG retrievals relative to the buffer "
    "is a limiting factor.\n\n"

    "Nature/Land is at baseline across the monitored land-cover "
    "indicators at this location. Data quality is high."
)


class TestWorkedExample:
    def test_overall_output_matches_doc_section_9(self) -> None:
        # This is the canonical regression test. If a templated string
        # drifts or a slot resolution changes, this test catches it.
        result = generate_verbal_summary(_WORKED_EXAMPLE_PAYLOAD)
        assert result.joined() == _WORKED_EXAMPLE_OUTPUT

    def test_template_ids_match_expected(self) -> None:
        result = generate_verbal_summary(_WORKED_EXAMPLE_PAYLOAD)
        assert result.template_ids == {
            "overview": "overview/1/moderate",
            "air":      "air/high/moderate/main",
            "ghg":      "ghg/moderate/moderate/main",
            "nature":   "nature/low/high/main",
        }

    def test_summary_object_is_frozen(self) -> None:
        result = generate_verbal_summary(_WORKED_EXAMPLE_PAYLOAD)
        with pytest.raises(Exception):  # FrozenInstanceError
            result.overview = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Integration with the engine-shaped payload
# ---------------------------------------------------------------------------

class TestEngineShapedPayload:
    """End-to-end on a payload shaped like ScreeningRun.run() output —
    the keys and values match what the live engine actually emits.
    """

    def test_engine_payload_renders_four_paragraphs(self) -> None:
        # Reasonable mid-range values from a fictional clean-but-not-pristine
        # supplier — all four paragraphs must render without errors.
        payload = {
            "composite.overall_screening": 0.35,
            "composite.confidence":        0.60,
            "air.audit_followup_priority":      0.40,
            "air.measurement_quality_score": 0.60,
            "air.no2.score":     0.4,
            "air.no2.site":      28.0,
            "air.no2.z":         1.2,
            "air.no2.anomaly":   8e-6,
            "air.no2.confidence": 0.60,
            "air.so2.score":     0.1,
            "air.co.score":      0.1,
            "air.hcho.score":    0.1,
            "air.pm_or_aerosol": 0.1,
            "air.o3.score":      0.1,
            "ghg.audit_followup_priority":   0.30,
            "ghg.data_quality_attribution":  0.65,
            "ghg.ch4_context_adjusted":      0.3,
            "ghg.combustion_proxy":          0.1,
            "ghg.activity_score":            0.1,
            "ghg.co2_context":               None,
            "nature.followup_priority":   0.35,
            "nature.measurement_quality": 0.55,
            "nature.biodiversity_exposure":    0.4,
            "nature.habitat.conversion_score": 0.1,
            "nature.vegetation_condition":     0.1,
            "nature.kba.overlap_pct": 0.0,
            "nature.kba.dist_km":     6.5,
        }
        result = generate_verbal_summary(payload)
        assert result.overview
        assert result.air
        assert result.ghg
        assert result.nature
        # No leftover format slots.
        for paragraph in (result.overview, result.air, result.ghg, result.nature):
            assert "{" not in paragraph and "}" not in paragraph

    def test_handles_all_none_pillars_gracefully(self) -> None:
        # Total degradation — every pillar score is None. The buckets
        # collapse to "low" so the low/low templates fire across the board.
        payload = {
            "composite.overall_screening": None,
            "composite.confidence":        None,
            "air.audit_followup_priority":      None,
            "air.measurement_quality_score": None,
            "ghg.audit_followup_priority":  None,
            "ghg.data_quality_attribution": None,
            "nature.followup_priority":     None,
            "nature.measurement_quality":   None,
        }
        result = generate_verbal_summary(payload)
        # All low/low-shape outputs.
        assert "background" in result.air
        assert "background" in result.ghg
        assert "baseline" in result.nature
        # Overview shape is "0" (zero high pillars).
        assert result.template_ids["overview"].startswith("overview/0/")

    def test_three_high_pillars_uses_shape_three(self) -> None:
        payload = {
            "composite.overall_screening": 0.85,
            "composite.confidence":        0.80,
            "air.audit_followup_priority":      0.80,
            "air.measurement_quality_score": 0.80,
            "ghg.audit_followup_priority":  0.80,
            "ghg.data_quality_attribution": 0.80,
            "nature.followup_priority":     0.80,
            "nature.measurement_quality":   0.80,
        }
        result = generate_verbal_summary(payload)
        assert result.template_ids["overview"] == "overview/3/high"
        assert "all three pillars" in result.overview
        assert "clear flag for follow-up" in result.overview

    def test_two_high_pillars_lists_in_air_ghg_nature_order(self) -> None:
        # Air + Nature high, GHG moderate → shape "2", lists "Air
        # Pollution and Nature/Land" (display order, NOT score order).
        payload = {
            "composite.overall_screening": 0.65,
            "composite.confidence":        0.80,
            "air.audit_followup_priority":      0.80,
            "air.measurement_quality_score": 0.80,
            "ghg.audit_followup_priority":  0.50,
            "ghg.data_quality_attribution": 0.80,
            "nature.followup_priority":     0.80,
            "nature.measurement_quality":   0.80,
        }
        result = generate_verbal_summary(payload)
        assert result.template_ids["overview"] == "overview/2/high"
        # Air Pollution comes first, Nature/Land second (PILLAR_ORDER).
        assert "Air Pollution and Nature/Land" in result.overview
