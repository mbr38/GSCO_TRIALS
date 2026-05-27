"""Unit tests for the pure fallback logic (M-FALLBACK-A1).

Covers `engine.core.fallback` (window math, the §4.5 composition decision
table, aoi_scale_class, the provenance.extra builder) and the two new
confidence multipliers in `engine.core.confidence`. No Earth Engine — all
synthetic, per the spec's §7.3 / §7.4 plan.
"""

from __future__ import annotations

import pytest

from engine.constants import (
    CLIMATOLOGY_FALLBACK_MULTIPLIER,
    SLIDING_LOOKBACK_MAX_STEPS,
    SLIDING_LOOKBACK_STEP_DAYS,
    TEMPORAL_FALLBACK_MULTIPLIER,
)
from engine.core.confidence import compute_indicator_confidence
from engine.core.fallback import (
    aoi_scale_class,
    build_fallback_extra,
    resolve_fallback_plan,
    sliding_lookback_windows,
    sppy_window,
)


# ---------------------------------------------------------------------------
# §4.1 — SPPY window math
# ---------------------------------------------------------------------------

class TestSppyWindow:
    def test_shifts_back_exactly_one_year(self) -> None:
        assert sppy_window(("2026-03-01", "2026-05-31")) == (
            "2025-03-01", "2025-05-31",
        )

    def test_preserves_calendar_period_only_year_changes(self) -> None:
        start, end = sppy_window(("2026-01-15", "2026-04-15"))
        assert start.endswith("-01-15") and end.endswith("-04-15")
        assert start.startswith("2025") and end.startswith("2025")

    def test_leap_day_clamps_to_feb_28(self) -> None:
        # 2024-02-29 has no Feb-29 in 2023 → clamp to Feb-28.
        assert sppy_window(("2024-02-29", "2024-03-31")) == (
            "2023-02-28", "2023-03-31",
        )


class TestSlidingLookbackWindows:
    def test_returns_max_steps_windows(self) -> None:
        windows = sliding_lookback_windows(("2026-03-01", "2026-05-30"))
        assert len(windows) == SLIDING_LOOKBACK_MAX_STEPS

    def test_first_window_shifted_one_step_back(self) -> None:
        windows = sliding_lookback_windows(
            ("2026-03-01", "2026-05-30"), step_days=90, max_steps=3,
        )
        # First candidate is the original window shifted back 90 days
        # (2026-03-01 → 2025-12-01; 2026-05-30 → 2026-03-01).
        assert windows[0] == ("2025-12-01", "2026-03-01")

    def test_windows_preserve_length_and_step_back(self) -> None:
        from datetime import date

        tr = ("2026-03-01", "2026-05-30")
        orig_len = (date.fromisoformat(tr[1]) - date.fromisoformat(tr[0])).days
        windows = sliding_lookback_windows(tr, step_days=30, max_steps=4)
        prev_start = date.fromisoformat(tr[0])
        for w in windows:
            s, e = date.fromisoformat(w[0]), date.fromisoformat(w[1])
            assert (e - s).days == orig_len           # length preserved
            assert s < prev_start                       # strictly backward
            prev_start = s

    def test_default_step_is_the_constant(self) -> None:
        windows = sliding_lookback_windows(("2026-03-01", "2026-05-30"))
        from datetime import date
        first_start = date.fromisoformat(windows[0][0])
        orig_start = date.fromisoformat("2026-03-01")
        assert (orig_start - first_start).days == SLIDING_LOOKBACK_STEP_DAYS


# ---------------------------------------------------------------------------
# §4.7 — aoi_scale_class
# ---------------------------------------------------------------------------

class TestAoiScaleClass:
    @pytest.mark.parametrize("radius_km,expected", [
        (5, "site"),
        (25, "site"),       # boundary inclusive
        (26, "regional"),
        (100, "regional"),  # boundary inclusive
        (101, "biome"),
        (250, "biome"),
    ])
    def test_classification(self, radius_km, expected) -> None:
        assert aoi_scale_class(radius_km) == expected


# ---------------------------------------------------------------------------
# §4.5 — composition decision table (one assertion per row)
# ---------------------------------------------------------------------------

class TestResolveFallbackPlan:
    def test_normal_no_fallback(self) -> None:
        plan = resolve_fallback_plan(
            site_current_ok=True, ring_current_ok=True,
            ring_is_water=False, strict_audit_mode=False,
        )
        assert plan.mode == "normal"
        assert not any(
            (plan.attempt_sppy_site, plan.attempt_sppy_ring, plan.use_climatology)
        )

    def test_mode_a_site_fails_background_fine(self) -> None:
        plan = resolve_fallback_plan(
            site_current_ok=False, ring_current_ok=True,
            ring_is_water=False, strict_audit_mode=False,
        )
        assert plan.mode == "mode_a"
        assert plan.attempt_sppy_site is True
        assert plan.attempt_sppy_ring is False
        assert plan.use_climatology is False

    def test_mode_b_background_fails_site_fine_auto_climatology(self) -> None:
        plan = resolve_fallback_plan(
            site_current_ok=True, ring_current_ok=False,
            ring_is_water=False, strict_audit_mode=False,
        )
        assert plan.mode == "mode_b"
        assert plan.attempt_sppy_site is False
        assert plan.use_climatology is True

    def test_mode_c_both_fail_compound(self) -> None:
        plan = resolve_fallback_plan(
            site_current_ok=False, ring_current_ok=False,
            ring_is_water=False, strict_audit_mode=False,
        )
        assert plan.mode == "mode_c"
        assert plan.attempt_sppy_site is True
        assert plan.attempt_sppy_ring is True
        assert plan.use_climatology is True

    def test_mode_1_water_ring_fires_climatology_directly(self) -> None:
        # Water ring, site fine → climatology directly, no SPPY.
        plan = resolve_fallback_plan(
            site_current_ok=True, ring_current_ok=False,
            ring_is_water=True, strict_audit_mode=False,
        )
        assert plan.mode == "mode_1_water"
        assert plan.attempt_sppy_site is False
        assert plan.attempt_sppy_ring is False
        assert plan.use_climatology is True

    def test_mode_1_water_with_site_failure_compounds_sppy_site(self) -> None:
        plan = resolve_fallback_plan(
            site_current_ok=False, ring_current_ok=False,
            ring_is_water=True, strict_audit_mode=False,
        )
        assert plan.mode == "mode_1_water"
        assert plan.attempt_sppy_site is True   # site co-failed → SPPY it
        assert plan.use_climatology is True

    @pytest.mark.parametrize("site_ok,ring_ok,water", [
        (False, False, True), (True, False, False), (False, True, False),
    ])
    def test_strict_audit_disables_everything(self, site_ok, ring_ok, water) -> None:
        plan = resolve_fallback_plan(
            site_current_ok=site_ok, ring_current_ok=ring_ok,
            ring_is_water=water, strict_audit_mode=True,
        )
        assert plan.mode == "strict_skip"
        assert not any(
            (plan.attempt_sppy_site, plan.attempt_sppy_ring, plan.use_climatology)
        )


# ---------------------------------------------------------------------------
# §4.7 — provenance.extra builder
# ---------------------------------------------------------------------------

class TestBuildFallbackExtra:
    def test_no_fallback_emits_all_keys_with_falsey_detail(self) -> None:
        extra = build_fallback_extra(radius_km=5)
        assert extra["aoi_scale_class"] == "site"
        assert extra["temporal_fallback_used"] is False
        assert extra["temporal_fallback_strategy"] is None
        assert extra["temporal_fallback_source_window"] is None
        assert extra["climatology_fallback_used"] is False
        assert extra["climatology_fallback_vintage"] is None

    def test_temporal_fallback_formats_source_window(self) -> None:
        extra = build_fallback_extra(
            radius_km=10,
            temporal_fallback_used=True,
            temporal_fallback_strategy="sppy",
            temporal_fallback_source_window=("2025-03-01", "2025-05-31"),
        )
        assert extra["temporal_fallback_used"] is True
        assert extra["temporal_fallback_strategy"] == "sppy"
        assert extra["temporal_fallback_source_window"] == "2025-03-01/2025-05-31"

    def test_climatology_fallback_records_vintage(self) -> None:
        extra = build_fallback_extra(
            radius_km=150,
            climatology_fallback_used=True,
            climatology_fallback_vintage="2026",
        )
        assert extra["climatology_fallback_used"] is True
        assert extra["climatology_fallback_vintage"] == "2026"
        assert extra["aoi_scale_class"] == "biome"


# ---------------------------------------------------------------------------
# §4.6 — confidence multiplier chain
# ---------------------------------------------------------------------------

class TestConfidenceFallbackMultipliers:
    _BASE = dict(
        indicator_id="air.no2",
        qa=1.0, n_valid=1.0, anomaly_strength=1.0, spatial_context=1.0,
        column_to_surface_uncertainty="n_a",  # multiplier 1.0 → isolate fallback
    )

    def test_no_fallback_flags_default_to_no_op(self) -> None:
        assert compute_indicator_confidence(**self._BASE) == pytest.approx(1.0)

    def test_temporal_fallback_applies_060(self) -> None:
        c = compute_indicator_confidence(
            **self._BASE, temporal_fallback_applied=True,
        )
        assert c == pytest.approx(TEMPORAL_FALLBACK_MULTIPLIER)  # 0.60

    def test_climatology_fallback_applies_075(self) -> None:
        c = compute_indicator_confidence(
            **self._BASE, climatology_fallback_applied=True,
        )
        assert c == pytest.approx(CLIMATOLOGY_FALLBACK_MULTIPLIER)  # 0.75

    def test_compound_fallback_is_045(self) -> None:
        c = compute_indicator_confidence(
            **self._BASE,
            temporal_fallback_applied=True,
            climatology_fallback_applied=True,
        )
        assert c == pytest.approx(0.45)

    def test_compound_with_column_multiplier_lands_below_sparse(self) -> None:
        # FB21 — a column-relevant indicator (moderate, 0.95) under compound
        # fallback lands at 0.95 × 0.45 ≈ 0.4275; with realistic sub-1.0
        # terms it dips under the 0.40 Sparse threshold. Here we pin the
        # multiplier composition order.
        c = compute_indicator_confidence(
            indicator_id="air.no2",
            qa=1.0, n_valid=1.0, anomaly_strength=1.0, spatial_context=1.0,
            column_to_surface_uncertainty="moderate",  # 0.95
            temporal_fallback_applied=True,
            climatology_fallback_applied=True,
        )
        assert c == pytest.approx(0.95 * 0.45)

    def test_strict_none_still_wins_over_fallback_flags(self) -> None:
        # A missing term collapses to None regardless of fallback flags.
        c = compute_indicator_confidence(
            indicator_id="air.no2",
            qa=None, n_valid=1.0, anomaly_strength=1.0, spatial_context=1.0,
            column_to_surface_uncertainty="n_a",
            temporal_fallback_applied=True,
            climatology_fallback_applied=True,
        )
        assert c is None
