"""Tests for ui.components.p11_csv (M-P11.4).

Pure-Python — no Streamlit. Pins the column contract (header order
+ exact column names), the row-shape contract (N × 19 expansion for
prioritisation sources, header-only when there's nothing to write),
and the value formatting rules (4-decimal scores, blank cells for
None / non-numeric, skipped_reason populated when set).
"""

# M-P11.4
from __future__ import annotations

import csv
from io import StringIO
from types import SimpleNamespace

from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS
from ui.components.p11_csv import _COLUMNS, render_csv


_TOTAL_INDICATORS = len(ALL_INDICATOR_IDS)


def _state():
    return SimpleNamespace(title="Demo", notes="")


def _screening_source(name="Screening A", payload=None):
    return {
        "id":              "src-1",
        "name":            name,
        "type":            "screening",
        "screening_setup": {
            "centre":     {"lat": 1.0, "lon": 2.0},
            "radius_km":  10,
            "time_range": ["2025-01-01", "2025-06-01"],
            "indicators": list(ALL_INDICATOR_IDS),
        },
        "payload":         payload or {},
    }


def _prioritisation_source(
    name="Prioritisation A",
    n_suppliers=2,
    include_empty_supplier=False,
):
    supplier_results = []
    for i in range(n_suppliers):
        supplier_results.append({
            "name":   f"Supplier {i}",
            "status": "success",
            "result": {
                "air.no2.score": 0.4 + 0.1 * i,
            },
        })
    if include_empty_supplier:
        supplier_results.append({
            "name":   "Failed Supplier",
            "status": "failed",
            "result": {},  # filtered out by the writer.
        })
    return {
        "id":                   "prio-1",
        "name":                 name,
        "type":                 "prioritisation",
        "supplier_results":     supplier_results,
    }


def _parse(csv_string: str) -> tuple[list[str], list[dict[str, str]]]:
    """Return (header, rows) from a CSV string.

    M-P11.4-FIX: ``render_csv`` prefixes the output with a UTF-8 BOM
    so Excel reads the file as UTF-8 — strip it here so DictReader
    sees the canonical header name (not ``\\ufeffsource_name``).
    """
    if csv_string.startswith("﻿"):
        csv_string = csv_string[1:]
    reader = csv.DictReader(StringIO(csv_string))
    return reader.fieldnames or [], list(reader)


# ---------------------------------------------------------------------------
# 5a. header row contains the expected columns in the expected order
# ---------------------------------------------------------------------------

def test_csv_header_matches_column_contract():
    out = render_csv(_state(), [_screening_source()])
    header, _ = _parse(out)
    assert header == list(_COLUMNS)


# ---------------------------------------------------------------------------
# 5b. screening source produces one row per indicator
# ---------------------------------------------------------------------------

def test_csv_screening_source_produces_one_row_per_indicator():
    out = render_csv(_state(), [_screening_source()])
    _, rows = _parse(out)
    assert len(rows) == _TOTAL_INDICATORS
    # Every row carries source_name + source_type for the source.
    assert {r["source_name"] for r in rows} == {"Screening A"}
    assert {r["source_type"] for r in rows} == {"screening"}


# ---------------------------------------------------------------------------
# 5c. prioritisation source expands to N × 19 rows
# ---------------------------------------------------------------------------

def test_csv_prioritisation_expands_per_supplier():
    src = _prioritisation_source(n_suppliers=3)
    out = render_csv(_state(), [src])
    _, rows = _parse(out)
    assert len(rows) == 3 * _TOTAL_INDICATORS
    supplier_names = {r["source_name"] for r in rows}
    # "Prioritisation A / Supplier 0", "/ Supplier 1", "/ Supplier 2"
    assert supplier_names == {
        f"Prioritisation A / Supplier {i}" for i in range(3)
    }


def test_csv_prioritisation_skips_empty_supplier_results():
    src = _prioritisation_source(n_suppliers=2, include_empty_supplier=True)
    out = render_csv(_state(), [src])
    _, rows = _parse(out)
    # Failed supplier (empty result) is filtered out.
    assert len(rows) == 2 * _TOTAL_INDICATORS
    assert "Failed Supplier" not in {r["source_name"] for r in rows}


# ---------------------------------------------------------------------------
# 5d. multi-source row count sums
# ---------------------------------------------------------------------------

def test_csv_multi_source_row_count_sums_correctly():
    sources = [
        _screening_source("Screen A"),
        _screening_source("Screen B"),
        _prioritisation_source("Prio C", n_suppliers=2),
    ]
    out = render_csv(_state(), sources)
    _, rows = _parse(out)
    # 19 (Screen A) + 19 (Screen B) + 2*19 (Prio C) = 76.
    assert len(rows) == _TOTAL_INDICATORS + _TOTAL_INDICATORS + 2 * _TOTAL_INDICATORS


# ---------------------------------------------------------------------------
# 5e. value formatting — 4-decimal scores, blank cells for None
# ---------------------------------------------------------------------------

def test_csv_score_values_formatted_to_four_decimals():
    payload = {
        "air.no2.score": 0.12345,
        "air.no2.confidence": 0.789,
    }
    out = render_csv(_state(), [_screening_source(payload=payload)])
    _, rows = _parse(out)
    no2_row = next(r for r in rows if r["indicator_id"] == "air.no2.score")
    assert no2_row["score"] == "0.1235"  # rounded to 4dp
    assert no2_row["confidence"] == "0.7890"


def test_csv_missing_score_renders_as_empty_cell():
    out = render_csv(_state(), [_screening_source(payload={})])
    _, rows = _parse(out)
    # Every cell is blank because nothing in payload.
    for r in rows:
        assert r["score"] == ""
        assert r["confidence"] == ""


# ---------------------------------------------------------------------------
# 5f. skipped_reason populated when set
# ---------------------------------------------------------------------------

def test_csv_skipped_reason_propagates_from_provenance():
    payload = {
        "air.no2.score": None,
        "_provenance.air.no2": {
            "asset_id":       "COPERNICUS/S5P/OFFL/L3_NO2",
            "native_scale_m": 1113.0,
            "time_range":     ("2025-01-01", "2025-06-01"),
            "skipped_reason": "Not enough valid grids",
        },
    }
    out = render_csv(_state(), [_screening_source(payload=payload)])
    _, rows = _parse(out)
    no2_row = next(r for r in rows if r["indicator_id"] == "air.no2.score")
    assert no2_row["skipped_reason"] == "Not enough valid grids"
    assert no2_row["asset_id"] == "COPERNICUS/S5P/OFFL/L3_NO2"
    assert no2_row["time_range_start"] == "2025-01-01"
    assert no2_row["time_range_end"] == "2025-06-01"


# ---------------------------------------------------------------------------
# M-UI-A1-SURFACE Sub-milestone 5 — A1 audit-transparency columns
# ---------------------------------------------------------------------------

def test_csv_row_includes_all_a1_extra_columns():
    """Spec — for an indicator with the full M-TIER-A1 + engine-gap
    extras dict, all 7 new columns appear in the header AND carry the
    expected values for a sample row.
    """
    payload = {
        "air.no2.score": 0.45,
        "air.no2.confidence": 0.684,
        "_provenance.air.no2": {
            "asset_id":       "COPERNICUS/S5P/OFFL/L3_NO2",
            "native_scale_m": 1113.0,
            "time_range":     ("2026-02-22", "2026-05-23"),
            "extra": {
                "confidence_terms": {
                    "qa":               0.90,
                    "n_valid":          1.00,
                    "anomaly_strength": 0.00,
                    "spatial_context":  1.00,
                    "column_to_surface_uncertainty": "moderate",
                },
                "n_valid_dates": 64,
                "granule_count": 64,
            },
        },
    }
    out = render_csv(_state(), [_screening_source(payload=payload)])
    header, rows = _parse(out)

    # Header carries every new column in the locked order.
    for col in (
        "confidence_term_qa",
        "confidence_term_n_valid",
        "confidence_term_anomaly_strength",
        "confidence_term_spatial_context",
        "column_to_surface_multiplier",
        "n_valid_dates",
        "granule_count",
    ):
        assert col in header

    no2_row = next(r for r in rows if r["indicator_id"] == "air.no2.score")
    assert no2_row["confidence_term_qa"]               == "0.9000"
    assert no2_row["confidence_term_n_valid"]          == "1.0000"
    assert no2_row["confidence_term_anomaly_strength"] == "0.0000"
    assert no2_row["confidence_term_spatial_context"]  == "1.0000"
    # multiplier derived from `moderate` → 0.95 via the engine constant.
    assert no2_row["column_to_surface_multiplier"]     == "0.9500"
    # Integer-typed fields render as bare ints, not 4-decimal floats.
    assert no2_row["n_valid_dates"] == "64"
    assert no2_row["granule_count"] == "64"


def test_csv_row_a1_columns_empty_for_indicator_without_extras():
    """An indicator with no provenance.extra (or empty extra) must
    leave the 7 new columns blank — never crash, never literal 'None'."""
    payload = {
        "air.no2.score":      0.45,
        "_provenance.air.no2": {
            "asset_id": "COPERNICUS/S5P/OFFL/L3_NO2",
            # No `extra` key at all.
        },
    }
    out = render_csv(_state(), [_screening_source(payload=payload)])
    _, rows = _parse(out)
    no2_row = next(r for r in rows if r["indicator_id"] == "air.no2.score")
    for col in (
        "confidence_term_qa",
        "confidence_term_n_valid",
        "confidence_term_anomaly_strength",
        "confidence_term_spatial_context",
        "column_to_surface_multiplier",
        "n_valid_dates",
        "granule_count",
    ):
        assert no2_row[col] == ""


# ---------------------------------------------------------------------------
# 5g. empty source list → header-only CSV (no crash)
# ---------------------------------------------------------------------------

def test_csv_empty_sources_returns_header_only():
    out = render_csv(_state(), [])
    header, rows = _parse(out)
    assert header == list(_COLUMNS)
    assert rows == []


# ---------------------------------------------------------------------------
# M-P11.4-FIX — UTF-8 BOM + QUOTE_ALL for Excel compatibility
# ---------------------------------------------------------------------------

def test_csv_output_starts_with_utf8_bom():
    """Excel on macOS / Windows needs the BOM to read the file as UTF-8."""
    out = render_csv(_state(), [_screening_source()])
    assert out.startswith("﻿")


def test_csv_source_name_with_comma_is_quoted():
    """Commas inside cells used to break Excel's column layout —
    QUOTE_ALL wraps every field, so the parsed cell stays intact."""
    src = _screening_source(name="Rio, Brazil — supplier A")
    out = render_csv(_state(), [src])
    # The raw output contains the quoted form.
    assert '"Rio, Brazil — supplier A"' in out
    # Round-tripping through csv.DictReader preserves the comma in one cell.
    _, rows = _parse(out)
    assert {r["source_name"] for r in rows} == {"Rio, Brazil — supplier A"}


def test_csv_every_field_is_quoted():
    """QUOTE_ALL quotes header and data cells uniformly. Spot-check
    a few representative values — every column header is quoted, and
    a known pillar/source_type value is too."""
    out = render_csv(_state(), [_screening_source()])
    for column in _COLUMNS:
        assert f'"{column}"' in out
    # Pillar / source_type cells are quoted even though they're
    # simple ASCII tokens.
    assert '"air"' in out
    assert '"screening"' in out


def test_csv_utf8_special_chars_round_trip():
    """Em-dashes / accented characters used to mangle when Excel
    on macOS auto-detected the encoding as the local 8-bit one. The
    BOM forces UTF-8; check that decoding the bytes preserves the
    character."""
    src = _screening_source(name="São Paulo — supplier")
    out = render_csv(_state(), [src])
    encoded = out.encode("utf-8")
    decoded = encoded.decode("utf-8-sig")  # strips BOM, decodes as UTF-8
    assert "São Paulo — supplier" in decoded
