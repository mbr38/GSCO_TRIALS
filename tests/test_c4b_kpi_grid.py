"""Tests for ui.components.c4b_kpi_grid — the M-UI-A4 indicator snapshot.

Pure-Python — no Streamlit. The ``render_*`` functions write to Streamlit
and can't be asserted on directly, so we test the pure helpers (tile
registry, severity dispatch, failure detection, snapshot partition, HTML
builders) plus end-to-end passes over the seeded demo screening payloads
(Sapezal + Brasília golden fixtures, spec §7.4).
"""

# M-UI-A4
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ui.components.c4a_indicator_map import _RENDERERS
from ui.components.c4b_kpi_grid import (
    MAP_ANCHOR_ID,
    _MIN_SNAPSHOT_TILES,
    _TILES,
    _headline_value,
    _is_failed,
    _resolve_failure_reason,
    _severity_badge_html,
    _snapshot_partition,
    _tile_severity,
    _visible_tiles,
)
from ui.components.severity import is_critical


def _tile(indicator: str):
    return next(t for t in _TILES if t.indicator == indicator)


# ---------------------------------------------------------------------------
# Tile registry integrity (SR4, SR6, SR7)
# ---------------------------------------------------------------------------

def test_tile_count_is_thirteen():
    # Spec v1.1: 9 air + 2 ghg + 3 nature (Hansen + ODIAC removed).
    # M-CH4-A1: CH₄ removed from the headline grid (reference data) → 9+1+3=13.
    assert len(_TILES) == 13


def test_pillar_split():
    counts = {p: sum(1 for t in _TILES if t.pillar == p) for p in ("air", "ghg", "nature")}
    # M-CH4-A1: ghg drops from 2 to 1 (only VIIRS remains scored; CH₄ + ODIAC
    # are reference data).
    assert counts == {"air": 9, "ghg": 1, "nature": 3}


def test_nature_tiles_present_in_headline_registry():
    """SR4 (v1.1) — KBA, DW, NDVI get headline tiles; Hansen is excluded."""
    nature = {t.indicator for t in _TILES if t.pillar == "nature"}
    assert nature == {"kba", "dw", "ndvi"}


def test_grammars_used():
    """SR7 (v1.1) — z-score / categorical / distance, plus the M-GHG-REDESIGN-A1
    score-band grammar for the re-grammared VIIRS tile (loss_fraction removed)."""
    grammars = {t.grammar for t in _TILES}
    assert grammars == {"zscore", "score_band", "categorical", "distance"}


def test_viirs_tile_uses_score_band_grammar():
    """M-GHG-REDESIGN-A1 — VIIRS bands its [0,1] sustained-contrast score, not a
    z-score; the tile carries no z_key."""
    viirs = next(t for t in _TILES if t.select_key == "ghg.viirs.score")
    assert viirs.grammar == "score_band"
    assert viirs.score_key == "ghg.viirs.score"
    assert viirs.z_key is None


def test_hansen_and_odiac_not_in_headline_grid():
    """SR4 (v1.1) / §8.6 regression — reference datasets must not re-appear as
    tiles. Hansen (nature.forest_loss) and ODIAC (ghg.co2) live in C5."""
    indicators = {(t.pillar, t.indicator) for t in _TILES}
    assert ("nature", "forest_loss") not in indicators
    assert ("ghg", "co2") not in indicators
    # M-CH4-A1: CH₄ is reference data too — must not appear as a headline tile.
    assert ("ghg", "ch4") not in indicators
    # Also by select-key, since that's what selection/rendering keys on.
    select_keys = {t.select_key for t in _TILES}
    assert "nature.forest_loss.ha" not in select_keys
    assert "ghg.co2.score" not in select_keys
    assert "ghg.ch4.score" not in select_keys


def test_every_tile_has_select_key_and_confidence_key():
    for t in _TILES:
        assert t.select_key, t.indicator
        # All current tiles carry a confidence key; the field is optional
        # for forward-compat but should be populated today.
        assert t.confidence_key, t.indicator


def test_zscore_tiles_have_z_key():
    for t in _TILES:
        if t.grammar == "zscore":
            assert t.z_key is not None, t.indicator


def test_provenance_key_shape():
    assert _tile("no2").provenance_key == "_provenance.air.no2"
    assert _tile("kba").provenance_key == "_provenance.nature.kba"


def test_no_engine_critical_field_dependency():
    """SR3 — severity is local; no tile reads an engine 'critical' flag."""
    for t in _TILES:
        for field in (t.select_key, t.z_key, t.category_key, t.dist_km_key,
                      t.confidence_key):
            if field:
                assert "critical" not in field


# ---------------------------------------------------------------------------
# _is_failed / _headline_value (grammar-value-based)
# ---------------------------------------------------------------------------

def test_is_failed_when_zscore_headline_none():
    assert _is_failed(_tile("no2"), {"air.no2.z": None}) is True


def test_is_failed_false_when_zscore_present():
    assert _is_failed(_tile("no2"), {"air.no2.z": 1.2}) is False


def test_ndvi_not_failed_when_score_none_but_z_present():
    """Regression: nature.ndvi.score is routinely None in v1; the NDVI tile
    keys failure on its z, not its score, so it doesn't read as failed."""
    payload = {"nature.ndvi.score": None, "nature.ndvi.z": -1.4}
    assert _is_failed(_tile("ndvi"), payload) is False


def test_is_failed_distance_needs_both_none():
    assert _is_failed(_tile("kba"), {"nature.kba.dist_km": None,
                                     "nature.kba.overlap_pct": None}) is True
    assert _is_failed(_tile("kba"), {"nature.kba.dist_km": 5.0,
                                     "nature.kba.overlap_pct": None}) is False


def test_is_failed_on_empty_payload():
    assert _is_failed(_tile("co"), {}) is True


def test_headline_value_distance_prefers_distance():
    assert _headline_value(_tile("kba"),
                           {"nature.kba.dist_km": 3.0, "nature.kba.overlap_pct": 1.0}) == 3.0


# ---------------------------------------------------------------------------
# _resolve_failure_reason (SR12)
# ---------------------------------------------------------------------------

def test_resolve_reason_from_failures_list():
    payload = {
        "air.pm10.z": None,
        "_failures": {"air": [
            {"indicator_id": "air.pm10", "reason": "buffer smaller than native pixel"},
        ]},
    }
    assert "buffer" in _resolve_failure_reason(_tile("pm10"), payload)


def test_resolve_reason_from_provenance_skipped_translates():
    # DW skip translates via _SKIPPED_REASON_TRANSLATIONS (forest_loss tile
    # was removed in v1.1, so exercise the path on a still-present tile).
    payload = {"nature.dw.dominant_class": None,
               "_provenance.nature.dw": {"skipped_reason": "no_dw_pixels"}}
    assert "Dynamic World" in _resolve_failure_reason(_tile("dw"), payload)


def test_resolve_reason_generic_fallback():
    assert _resolve_failure_reason(_tile("aod"), {"air.aod.z": None}) == (
        "Indicator did not return a value."
    )


# ---------------------------------------------------------------------------
# _tile_severity dispatch (one per grammar)
# ---------------------------------------------------------------------------

def test_severity_zscore_dispatch():
    payload = {"air.no2.z": 2.4, "air.no2.confidence": 0.9}
    assert _tile_severity(_tile("no2"), payload) == "High"


def test_severity_distance_dispatch():
    payload = {"nature.kba.dist_km": 0.5, "nature.kba.overlap_pct": 0.0,
               "nature.kba.confidence": 0.9}
    assert _tile_severity(_tile("kba"), payload) == "High"


def test_severity_categorical_dw_dispatch():
    payload = {"nature.dw.dominant_class": "built", "nature.dw.confidence": 0.9}
    assert _tile_severity(_tile("dw"), payload) == "Concern"


def test_failed_tile_reports_sparse_for_filter():
    """SR12 — a failed tile is non-critical (Sparse) for the snapshot."""
    assert _tile_severity(_tile("pm10"), {"air.pm10.z": None}) == "Sparse"


# ---------------------------------------------------------------------------
# _visible_tiles — selection-aware (M-P04)
# ---------------------------------------------------------------------------

def test_visible_tiles_keeps_only_selected():
    selected = {"air.no2.score", "ghg.viirs.score", "nature.kba.proximity_score"}
    visible = {t.indicator for t in _visible_tiles(selected)}
    assert visible == {"no2", "viirs", "kba"}


def test_visible_tiles_ch4_yields_no_tile():
    """M-CH4-A1 — selecting CH₄ yields no headline tile (reference data in C5),
    mirroring Hansen/ODIAC."""
    selected = {"air.no2.score", "ghg.ch4.score"}
    visible = {t.indicator for t in _visible_tiles(selected)}
    assert visible == {"no2"}


def test_visible_tiles_nature_select_keys_resolve():
    """The Nature tiles use the registry's selectable IDs, not '.score'.

    Selecting nature.forest_loss.ha yields no tile (Hansen is a reference
    dataset in C5, not a headline tile, per spec v1.1)."""
    selected = {"nature.dw.trees_pct", "nature.forest_loss.ha", "nature.ndvi.score"}
    visible = {t.indicator for t in _visible_tiles(selected)}
    assert visible == {"dw", "ndvi"}


def test_visible_tiles_empty_selection():
    assert _visible_tiles(set()) == []


# ---------------------------------------------------------------------------
# _snapshot_partition — SR2, SR9, SR5.4
# ---------------------------------------------------------------------------

def test_snapshot_shows_only_critical_when_many_fire():
    payload = {
        "air.no2.z": 3.0, "air.no2.confidence": 0.9,   # High
        "air.so2.z": 1.5, "air.so2.confidence": 0.9,   # Concern
        "air.co.z": 2.2, "air.co.confidence": 0.9,     # High
        "air.hcho.z": 0.1, "air.hcho.confidence": 0.9, # Normal
    }
    selected = {"air.no2.score", "air.so2.score", "air.co.score", "air.hcho.score"}
    snapshot, rest, sev = _snapshot_partition(_visible_tiles(selected), payload)
    snap_inds = {t.indicator for t in snapshot}
    assert snap_inds == {"no2", "so2", "co"}        # 3 critical
    assert {t.indicator for t in rest} == {"hcho"}  # the Normal one
    assert all(is_critical(sev[t.select_key]) for t in snapshot)


def test_snapshot_min_three_topup_when_few_critical():
    """SR9 — fewer than 3 critical → top up with highest-severity Normals."""
    payload = {
        "air.no2.z": 3.0, "air.no2.confidence": 0.9,   # High (1 critical)
        "air.so2.z": 0.2, "air.so2.confidence": 0.9,   # Normal
        "air.co.z": 0.8, "air.co.confidence": 0.9,     # Normal (higher |z|)
        "air.hcho.z": 0.1, "air.hcho.confidence": 0.9, # Normal
    }
    selected = {"air.no2.score", "air.so2.score", "air.co.score", "air.hcho.score"}
    snapshot, rest, _ = _snapshot_partition(_visible_tiles(selected), payload)
    assert len(snapshot) == _MIN_SNAPSHOT_TILES
    assert _tile("no2") in snapshot                 # the critical one is kept


def test_snapshot_topup_below_min_returns_all_when_too_few():
    payload = {"air.no2.z": 0.1, "air.no2.confidence": 0.9,
               "air.so2.z": 0.2, "air.so2.confidence": 0.9}
    selected = {"air.no2.score", "air.so2.score"}
    snapshot, rest, _ = _snapshot_partition(_visible_tiles(selected), payload)
    # Only 2 tiles exist; snapshot can't exceed what's available.
    assert len(snapshot) == 2
    assert rest == []


def test_snapshot_critical_sorted_high_before_concern():
    payload = {
        "air.no2.z": 1.2, "air.no2.confidence": 0.9,   # Concern
        "air.so2.z": 3.0, "air.so2.confidence": 0.9,   # High
    }
    selected = {"air.no2.score", "air.so2.score"}
    snapshot, _, _ = _snapshot_partition(_visible_tiles(selected), payload)
    assert [t.indicator for t in snapshot] == ["so2", "no2"]


# ---------------------------------------------------------------------------
# HTML builders (SR1, SR5)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("severity,word", [
    ("High", "High"), ("Concern", "Concern"),
    ("Normal", "Normal"), ("Sparse", "Sparse data"),
])
def test_severity_badge_contains_word(severity, word):
    assert word in _severity_badge_html(severity)


def test_map_anchor_id_is_shared():
    """SR5 — the anchor id is still importable from c4b (re-exported from
    multi_map_state after M-UI-A5) so the host and tiles share one id."""
    from ui.components.multi_map_state import MAP_ANCHOR_ID as canonical
    assert MAP_ANCHOR_ID == canonical


def test_every_tile_select_key_has_a_map_renderer():
    """MV8/MV16 — clicking any C4b tile's "View on map →" sets that tile's
    ``select_key`` as the active indicator, so every tile must dispatch to a
    registered renderer (otherwise the click would land on the
    not-implemented fallback)."""
    for tile in _TILES:
        assert tile.select_key in _RENDERERS, tile.select_key


# ---------------------------------------------------------------------------
# Integration — seeded demo golden payloads (spec §7.4)
# ---------------------------------------------------------------------------

_SAVES = Path(__file__).resolve().parent.parent / "demo" / "saved_analyses"


def _load_payload(name: str) -> dict:
    return json.loads((_SAVES / name).read_text())["payload"]


@pytest.fixture
def sapezal_payload() -> dict:
    return _load_payload("high_priority_amazon.json")


@pytest.fixture
def brasilia_payload() -> dict:
    return _load_payload("low_priority_brasilia.json")


_ALL_SELECTED = {t.select_key for t in _TILES}


def test_sapezal_all_tiles_classify_without_crash(sapezal_payload):
    for t in _TILES:
        sev = _tile_severity(t, sapezal_payload)
        assert sev in ("High", "Concern", "Normal", "Sparse")


def test_sapezal_kba_is_concern(sapezal_payload):
    # dist 7.33 km, no overlap → 1.0 ≤ d < 10.0 → Concern.
    assert _tile_severity(_tile("kba"), sapezal_payload) == "Concern"


def test_sapezal_snapshot_respects_min_three(sapezal_payload):
    """R1/SR9 — Sapezal is mostly Normal; the floor keeps the section full."""
    snapshot, _, _ = _snapshot_partition(_visible_tiles(_ALL_SELECTED), sapezal_payload)
    assert len(snapshot) >= _MIN_SNAPSHOT_TILES


def test_sapezal_viirs_classifies_normal(sapezal_payload):
    # M-VIIRS-REDESIGN-A1 — VIIRS score is now FLARING (absolute-anchored intense-
    # source), not the old saturating contrast·persistence. Sapezal is a soy
    # plantation frontier: locally lit, but with NO intense (>100 nW) source, so
    # flaring = 0.0 → Normal. The old test asserted "High" — that was precisely
    # the saturation bug the redesign fixes (a soy farm is not a GHG-intense source).
    # Its lit-presence is still captured as `attributability_state = high`, just not
    # as severity. Graceful-degradation-on-missing-score is covered by test_severity.py.
    assert _is_failed(_tile("viirs"), sapezal_payload) is False
    assert _tile_severity(_tile("viirs"), sapezal_payload) == "Normal"


def test_brasilia_kba_overlap_fires_high(brasilia_payload):
    # overlap 11.3% > 0 → High.
    assert _tile_severity(_tile("kba"), brasilia_payload) == "High"


def test_brasilia_has_critical_tiles(brasilia_payload):
    snapshot, _, sev = _snapshot_partition(_visible_tiles(_ALL_SELECTED), brasilia_payload)
    criticals = [k for k, s in sev.items() if is_critical(s)]
    assert criticals  # at least KBA fires


def test_selection_aware_air_only_hides_nature(sapezal_payload):
    """Only-Air selection → no Nature tiles render (SR/integration)."""
    air_only = {t.select_key for t in _TILES if t.pillar == "air"}
    visible = _visible_tiles(air_only)
    assert all(t.pillar == "air" for t in visible)
    assert not any(t.pillar == "nature" for t in visible)
