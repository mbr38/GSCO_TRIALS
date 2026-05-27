"""Tests for ui.components.severity (M-UI-A4).

Pure-Python. Covers all four severity grammars, the Sparse override, the
sign-convention direction helper, None-input handling, and the canonical
``SEVERITY_BANDS`` threshold table (spec §7.1, §7.5).
"""

# M-UI-A4
from __future__ import annotations

import pytest

from ui.components.severity import (
    SEVERITY_BANDS,
    is_critical,
    severity_categorical,
    severity_distance,
    severity_rank,
    severity_zscore,
    zscore_direction,
)


# A confidence that never trips the Sparse override (≥ 0.40).
_OK = 0.90
# Provenance with nothing that would trip Sparse.
_CLEAN_PROV: dict = {}


# ---------------------------------------------------------------------------
# §4.1 Z-score grammar — boundaries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("z,expected", [
    (2.0, "High"),       # exactly at High threshold
    (2.0001, "High"),
    (1.9999, "Concern"), # just below High
    (1.0, "Concern"),    # exactly at Concern threshold
    (0.9999, "Normal"),  # just below Concern
    (0.0, "Normal"),
])
def test_zscore_bands_positive(z, expected):
    assert severity_zscore(z, _OK, _CLEAN_PROV) == expected


@pytest.mark.parametrize("z,expected", [
    (-2.0, "High"),
    (-1.5, "Concern"),
    (-0.5, "Normal"),
])
def test_zscore_bands_use_magnitude_not_sign(z, expected):
    """SR1/§4.1: severity is on |z|; direction never changes the word."""
    assert severity_zscore(z, _OK, _CLEAN_PROV) == expected


def test_zscore_none_is_sparse_not_crash():
    assert severity_zscore(None, _OK, _CLEAN_PROV) == "Sparse"


# ---------------------------------------------------------------------------
# Sparse override (§4.1 SR8) — applies across grammars
# ---------------------------------------------------------------------------

def test_sparse_fires_on_low_confidence_even_with_high_z():
    """SR14: a high z at low confidence is still classified Sparse here
    (the orthogonal confidence dot carries the confidence signal)."""
    assert severity_zscore(5.0, 0.39, _CLEAN_PROV) == "Sparse"


def test_sparse_boundary_at_confidence_threshold():
    # 0.40 is NOT sparse (>= threshold passes); just below is.
    assert severity_zscore(1.5, 0.40, _CLEAN_PROV) == "Concern"
    assert severity_zscore(1.5, 0.3999, _CLEAN_PROV) == "Sparse"


def test_sparse_fires_on_none_confidence():
    assert severity_zscore(1.5, None, _CLEAN_PROV) == "Sparse"


def test_sparse_fires_on_skipped_reason():
    prov = {"skipped_reason": "no_hansen_pixels"}
    assert severity_zscore(5.0, _OK, prov) == "Sparse"


def test_sparse_fires_on_explicit_fallback_flag():
    prov = {"extra": {"fallback_used": True}}
    assert severity_zscore(5.0, _OK, prov) == "Sparse"


def test_sparse_fires_on_low_valid_pixel_pct():
    prov = {"extra": {"valid_pixel_pct": 0.29}}
    assert severity_zscore(5.0, _OK, prov) == "Sparse"
    prov_ok = {"extra": {"valid_pixel_pct": 0.30}}
    assert severity_zscore(1.5, _OK, prov_ok) == "Concern"


def test_sparse_none_provenance_is_handled():
    assert severity_zscore(1.5, _OK, None) == "Concern"


# ---------------------------------------------------------------------------
# zscore_direction (sign convention)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("z,expected", [
    (2.3, "above"),
    (-2.3, "below"),
    (0.05, "near"),
    (-0.05, "near"),
    (0.0, "near"),
    (None, "near"),
])
def test_zscore_direction(z, expected):
    assert zscore_direction(z) == expected


# ---------------------------------------------------------------------------
# §4.2 Categorical — DW dominant class (ODIAC scheme removed in spec v1.1)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("klass,expected", [
    ("built", "Concern"),
    ("bare", "Concern"),
    ("crops", "Normal"),       # never fires High alone (conservative)
    ("trees", "Normal"),
    ("water", "Normal"),
    ("grass", "Normal"),
])
def test_dw_dominant_class_bands(klass, expected):
    assert severity_categorical(klass, _OK, _CLEAN_PROV, scheme="dw") == expected


def test_dw_never_fires_high():
    """SR/§4.2: DW alone is capped at Concern."""
    for klass in ("built", "bare", "crops", "trees"):
        assert severity_categorical(klass, _OK, _CLEAN_PROV, scheme="dw") != "High"


def test_dw_none_is_sparse():
    assert severity_categorical(None, _OK, _CLEAN_PROV, scheme="dw") == "Sparse"


def test_categorical_unknown_scheme_raises():
    with pytest.raises(ValueError):
        severity_categorical("built", _OK, _CLEAN_PROV, scheme="nope")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# §4.3 Distance/overlap — KBA
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dist,overlap,expected", [
    (5.0, 0.5, "High"),     # overlap > 0 dominates
    (0.0, 0.0, "High"),     # dist < 1.0
    (0.99, 0.0, "High"),
    (1.0, 0.0, "Concern"),  # exactly at Concern lower bound
    (4.2, 0.0, "Concern"),
    (9.99, 0.0, "Concern"),
    (10.0, 0.0, "Normal"),  # exactly at Normal threshold
    (50.0, 0.0, "Normal"),
])
def test_kba_distance_overlap_bands(dist, overlap, expected):
    assert severity_distance(dist, overlap, _OK, _CLEAN_PROV) == expected


def test_kba_overlap_beats_far_distance():
    """A far site that still overlaps a KBA (multi-polygon AOI) fires High."""
    assert severity_distance(40.0, 2.0, _OK, _CLEAN_PROV) == "High"


def test_kba_both_none_is_sparse():
    assert severity_distance(None, None, _OK, _CLEAN_PROV) == "Sparse"


def test_kba_distance_none_but_overlap_present():
    assert severity_distance(None, 1.0, _OK, _CLEAN_PROV) == "High"


# Note (spec v1.1): the Hansen loss-fraction grammar was removed — no
# severity_loss_fraction function and no tests for it.


# ---------------------------------------------------------------------------
# Helpers: rank + is_critical
# ---------------------------------------------------------------------------

def test_severity_rank_order():
    assert severity_rank("High") > severity_rank("Concern")
    assert severity_rank("Concern") > severity_rank("Normal")
    assert severity_rank("Normal") > severity_rank("Sparse")


def test_is_critical():
    assert is_critical("High") is True
    assert is_critical("Concern") is True
    assert is_critical("Normal") is False
    assert is_critical("Sparse") is False


# ---------------------------------------------------------------------------
# §7.5 — canonical SEVERITY_BANDS fixture matches documented thresholds
# ---------------------------------------------------------------------------

def test_severity_bands_match_spec():
    assert SEVERITY_BANDS["zscore"] == {"High": 2.0, "Concern": 1.0}
    assert SEVERITY_BANDS["distance"] == {
        "High_km": 1.0, "Concern_km": 10.0, "High_overlap_pct": 0.0,
    }
    assert SEVERITY_BANDS["sparse_confidence"] == 0.40
    assert SEVERITY_BANDS["sparse_valid_pixel"] == 0.30


def test_severity_bands_drops_removed_grammars():
    """Spec v1.1: loss_fraction + odiac percentile bands removed."""
    assert "loss_fraction" not in SEVERITY_BANDS
    assert "odiac_percentile" not in SEVERITY_BANDS
    assert "odiac_mean" not in SEVERITY_BANDS
