"""Tests for the M-UI-A3 analysis-window-picker pure helpers.

No Streamlit involvement here — covers:

  - Profile fixture integrity (schema, value sanity)
  - Compute-estimate formula behaviour across AOI complexity tiers
    and batch-size multipliers
  - Validation messages and the order they appear
  - Format helper (seconds vs minutes)
  - Profile reusability (a second profile loaded from a synthetic
    fixture proves WP14)
  - WindowSelection ISO-tuple conversion (engine plumbing format)
  - p10_list._format_window_segment caption helper

The Streamlit render function (``render_analysis_window_picker``) is
NOT covered by unit tests — same convention as the rest of the codebase.
"""

# M-UI-A3
from __future__ import annotations

from datetime import date, timedelta

import pytest

from demo.window_picker_profiles import (
    ComputeEstimateCoefficients,
    Preset,
    WindowProfile,
    load_profile,
)
from engine.constants import (
    EARLIEST_SCREENING_DATE,
    SCREENING_WINDOW_DAYS_DEFAULT,
)
from ui.components.analysis_window_picker import (
    WindowSelection,
    complexity_factor_for,
    compute_estimate_seconds,
    format_estimate,
    validate_window,
)
from ui.components.p10_list import _format_window_segment


# ---------------------------------------------------------------------------
# Constants — single source of truth checks
# ---------------------------------------------------------------------------

def test_default_window_constant_is_90():
    """Documenting the canonical default. If this changes, downstream
    docs need updating (PLFS, Wireframes, Indicators_Computation §0.5)."""
    assert SCREENING_WINDOW_DAYS_DEFAULT == 90


def test_earliest_screening_date_is_2019():
    """Floor is the Sentinel-5P stable-CH4 date — second-most-restrictive
    dataset after ODIAC (which silent-skips when out of coverage)."""
    assert EARLIEST_SCREENING_DATE == "2019-01-01"


# ---------------------------------------------------------------------------
# Profile fixture integrity
# ---------------------------------------------------------------------------

def test_screening_profile_loads():
    profile = load_profile("screening")
    assert profile.name == "screening"
    assert profile.label  # non-empty string
    assert profile.default_preset == "90d"


def test_screening_profile_has_4_canonical_presets_plus_custom_handled_by_component():
    """Spec WP2 — exactly 30 d / 90 d / 6 mo / 12 mo (the Custom chip is
    added by the render function, not the fixture)."""
    profile = load_profile("screening")
    assert len(profile.presets) == 4
    expected = {("30d", 30), ("90d", 90), ("6mo", 180), ("12mo", 365)}
    actual = {(p.key, p.days) for p in profile.presets}
    assert actual == expected


def test_screening_profile_bounds_match_spec_wp8():
    """Spec WP8 — min 30, max 365."""
    profile = load_profile("screening")
    assert profile.min_days == 30
    assert profile.max_days == 365


def test_screening_profile_default_days_resolves_to_90():
    profile = load_profile("screening")
    assert profile.default_days() == SCREENING_WINDOW_DAYS_DEFAULT


def test_screening_profile_carries_all_validation_messages():
    """Each error type the validator emits needs a fixture message."""
    profile = load_profile("screening")
    required_keys = {
        "below_min", "above_max", "end_in_future",
        "start_after_end", "start_too_early",
    }
    assert required_keys.issubset(profile.validation_messages.keys())


def test_screening_profile_coefficients_present():
    """Spec WP10 — coefficients live in the fixture, not in code."""
    profile = load_profile("screening")
    coefs = profile.coefficients
    # Sanity checks on the placeholder values
    assert coefs.base_overhead_s > 0
    assert coefs.per_day_coef_s > 0
    assert coefs.complexity_small_max_km < coefs.complexity_medium_max_km
    assert coefs.complexity_factor_small < coefs.complexity_factor_large
    assert coefs.long_window_threshold_days > 0
    assert coefs.soft_warning_threshold_s > 0


def test_unknown_profile_raises_keyerror():
    with pytest.raises(KeyError, match="Unknown window-picker profile"):
        load_profile("does-not-exist")


# ---------------------------------------------------------------------------
# Complexity factor
# ---------------------------------------------------------------------------

def _coefs() -> ComputeEstimateCoefficients:
    return load_profile("screening").coefficients


def test_complexity_small_for_small_buffer():
    coefs = _coefs()
    assert complexity_factor_for(5, coefs) == coefs.complexity_factor_small


def test_complexity_medium_for_medium_buffer():
    coefs = _coefs()
    # Just above small threshold
    radius = coefs.complexity_small_max_km + 1
    assert complexity_factor_for(radius, coefs) == coefs.complexity_factor_medium


def test_complexity_large_for_large_buffer():
    coefs = _coefs()
    radius = coefs.complexity_medium_max_km + 1
    assert complexity_factor_for(radius, coefs) == coefs.complexity_factor_large


def test_complexity_unknown_falls_back_to_large():
    """None radius → assume worst case so the estimate over-promises
    rather than under-promises."""
    coefs = _coefs()
    assert complexity_factor_for(None, coefs) == coefs.complexity_factor_large


def test_complexity_at_boundary_is_inclusive():
    coefs = _coefs()
    # At-boundary defaults to the lower tier (small_max_km is small)
    assert complexity_factor_for(
        coefs.complexity_small_max_km, coefs,
    ) == coefs.complexity_factor_small
    assert complexity_factor_for(
        coefs.complexity_medium_max_km, coefs,
    ) == coefs.complexity_factor_medium


# ---------------------------------------------------------------------------
# Compute-estimate formula
# ---------------------------------------------------------------------------

def test_estimate_for_sapezal_90d_within_rule_of_thumb():
    """Sapezal-class (5 km, 90 d) should land within the ~30-60s
    rule-of-thumb from pages/05_Screening_Results.py:188."""
    seconds = compute_estimate_seconds(90, 5, _coefs())
    assert 20 <= seconds <= 80, (
        f"Sapezal 90d estimate {seconds:.0f}s outside calibration window"
    )


def test_estimate_for_brasilia_90d_within_rule_of_thumb():
    """Brasilia-class (45 km, 90 d) should land within the ~60-180s
    rule-of-thumb from pages/99_engine_scratch.py:192."""
    seconds = compute_estimate_seconds(90, 45, _coefs())
    assert 60 <= seconds <= 180, (
        f"Brasilia 90d estimate {seconds:.0f}s outside calibration window"
    )


def test_estimate_long_window_adds_penalty():
    """Window past the long_window_threshold gets an additive penalty."""
    coefs = _coefs()
    short = compute_estimate_seconds(coefs.long_window_threshold_days, 5, coefs)
    long_  = compute_estimate_seconds(coefs.long_window_threshold_days + 1, 5, coefs)
    # The +1-day delta would normally bump the linear term by ~per_day_coef;
    # the penalty piles on top.
    assert long_ - short >= coefs.long_window_penalty_s


def test_estimate_scales_linearly_with_n_suppliers():
    coefs = _coefs()
    single = compute_estimate_seconds(90, 5, coefs, n_suppliers=1)
    batch  = compute_estimate_seconds(90, 5, coefs, n_suppliers=20)
    assert batch == single * 20


def test_estimate_n_suppliers_zero_treated_as_one():
    """Defensive — a zero-supplier batch isn't a valid input but the
    formula shouldn't return 0 (would mis-signal 'instant'). Treat
    zero / negative as a single-supplier estimate."""
    coefs = _coefs()
    assert compute_estimate_seconds(90, 5, coefs, n_suppliers=0) == \
        compute_estimate_seconds(90, 5, coefs, n_suppliers=1)


# ---------------------------------------------------------------------------
# Format helper
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seconds,expected", [
    (10,   "~10 seconds"),
    (42,   "~42 seconds"),
    (95,   "~95 seconds"),
    (119,  "~119 seconds"),
    (120,  "~2.0 minutes"),
    (240,  "~4.0 minutes"),
    (1800, "~30.0 minutes"),
])
def test_format_estimate_threshold_at_120s(seconds, expected):
    assert format_estimate(seconds) == expected


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@pytest.fixture
def profile():
    return load_profile("screening")


@pytest.fixture
def today():
    return date(2026, 5, 27)


@pytest.fixture
def earliest():
    return date.fromisoformat(EARLIEST_SCREENING_DATE)


def test_validation_passes_for_default_window(profile, today, earliest):
    start = today - timedelta(days=90)
    assert validate_window(start, today, profile, earliest, today) == []


def test_validation_rejects_end_in_future(profile, today, earliest):
    end = today + timedelta(days=1)
    start = end - timedelta(days=90)
    errors = validate_window(start, end, profile, earliest, today)
    assert any("future" in e.lower() for e in errors)


def test_validation_rejects_below_minimum(profile, today, earliest):
    start = today - timedelta(days=10)
    errors = validate_window(start, today, profile, earliest, today)
    assert any("at least 30 days" in e for e in errors)


def test_validation_rejects_above_maximum(profile, today, earliest):
    start = today - timedelta(days=400)
    errors = validate_window(start, today, profile, earliest, today)
    assert any("Trend page" in e for e in errors)


def test_validation_rejects_start_before_earliest(profile, today, earliest):
    start = earliest - timedelta(days=1)
    end = start + timedelta(days=90)
    errors = validate_window(start, end, profile, earliest, today)
    assert any("Data not available" in e for e in errors)
    # The formatted message should embed the earliest-date string
    assert any(EARLIEST_SCREENING_DATE in e for e in errors)


def test_validation_rejects_start_after_end(profile, today, earliest):
    start = today
    end = today - timedelta(days=30)
    errors = validate_window(start, end, profile, earliest, today)
    assert any("before end date" in e for e in errors)


# ---------------------------------------------------------------------------
# WindowSelection — engine plumbing format
# ---------------------------------------------------------------------------

def test_window_selection_as_iso_tuple_matches_engine_format():
    """Engine ScreeningRun.time_range is tuple[str, str] of ISO dates."""
    sel = WindowSelection(
        start_date=date(2026, 2, 26),
        end_date=date(2026, 5, 27),
        days=90,
        estimated_seconds=60.0,
    )
    assert sel.as_iso_tuple() == ("2026-02-26", "2026-05-27")


# ---------------------------------------------------------------------------
# Profile reusability (WP14)
# ---------------------------------------------------------------------------

def test_synthetic_profile_proves_component_is_profile_driven(tmp_path, monkeypatch):
    """Build a synthetic profile in memory and verify the picker's
    pure-helper layer (validate_window + compute_estimate) accepts it
    without code changes. Proves WP14: item 1.4 can add a 'trend'
    profile by editing the fixture only."""
    coefs = ComputeEstimateCoefficients(
        base_overhead_s=60,
        per_day_coef_s=1.0,
        complexity_small_max_km=10,
        complexity_medium_max_km=25,
        complexity_factor_small=1.0,
        complexity_factor_medium=2.0,
        complexity_factor_large=3.0,
        long_window_threshold_days=730,
        long_window_penalty_s=120,
        soft_warning_threshold_s=600,
        long_window_warning="Long trend windows take a while.",
    )
    synthetic = WindowProfile(
        name="trend_synthetic",
        label="Trend window",
        default_preset="24mo",
        presets=(
            Preset(key="12mo", label="12 mo", days=365),
            Preset(key="24mo", label="24 mo", days=730),
        ),
        min_days=365,
        max_days=1825,
        validation_messages={
            "below_min":       "Trend windows must be at least 12 months.",
            "above_max":       "Maximum 5 years.",
            "end_in_future":   "End date cannot be in the future.",
            "start_after_end": "Start must be before end.",
            "start_too_early": "Data not available before {earliest_date}.",
        },
        coefficients=coefs,
    )
    today = date(2026, 5, 27)
    earliest = date(2019, 1, 1)
    # A 24-month window should validate cleanly under the synthetic bounds.
    start = today - timedelta(days=730)
    assert validate_window(start, today, synthetic, earliest, today) == []
    # And the estimate uses the synthetic coefficients.
    est = compute_estimate_seconds(730, 5, coefs)
    # base 60 + 730*1.0*1.0 + 120 (long-window penalty since 730 > 730 is False
    # actually 730 is the threshold; only > triggers — so no penalty)
    assert est == pytest.approx(60 + 730 * 1.0 * 1.0)


# ---------------------------------------------------------------------------
# p10_list caption helper
# ---------------------------------------------------------------------------

def test_format_window_segment_renders_days_and_range():
    assert _format_window_segment(["2026-02-26", "2026-05-27"]) == \
        "Window: 90 d (2026-02-26 → 2026-05-27)"


def test_format_window_segment_handles_tuple():
    assert _format_window_segment(("2026-02-26", "2026-05-27")) == \
        "Window: 90 d (2026-02-26 → 2026-05-27)"


def test_format_window_segment_handles_missing():
    """Older saves predating the window picker may lack time_range."""
    assert _format_window_segment(None) == "Window: —"
    assert _format_window_segment([]) == "Window: —"


def test_format_window_segment_handles_malformed():
    """Defensive against corrupted saves — never raise."""
    assert _format_window_segment(["not-a-date", "also-not"]) == "Window: —"
    assert _format_window_segment(["2026-02-26"]) == "Window: —"  # wrong arity
