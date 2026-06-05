"""Tests for ui.components.p07_form (M-P07).

Pure-Python — no Streamlit runtime. Covers the ad hoc textarea parser
(every error path + a happy mix) and pins the cap constant + the
Supplier dataclass shape so future drift surfaces here, not in the UI.
"""

# M-P07
from __future__ import annotations

import dataclasses

import pytest

from ui.components.p07_form import (
    _MAX_SUPPLIERS,
    Supplier,
    _parse_ad_hoc,
)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_single_valid_line_parses():
    suppliers, errors = _parse_ad_hoc("São Paulo HQ, -23.55, -46.63\n")
    assert len(suppliers) == 1
    assert errors == []
    s = suppliers[0]
    assert s.name   == "São Paulo HQ"
    assert s.lat    == pytest.approx(-23.55)
    assert s.lon    == pytest.approx(-46.63)
    assert s.source == "ad_hoc"
    assert s.id     == "adhoc_1"


def test_empty_and_comment_lines_are_ignored():
    text = (
        "\n"
        "# this is a comment\n"
        "   \n"
        "# São Paulo HQ, -23.55, -46.63\n"
        "Rio Distribution, -22.9, -43.17\n"
    )
    suppliers, errors = _parse_ad_hoc(text)
    assert len(suppliers) == 1
    assert errors == []
    assert suppliers[0].name == "Rio Distribution"


# ---------------------------------------------------------------------------
# Each error path
# ---------------------------------------------------------------------------

def test_lat_out_of_range_errors():
    suppliers, errors = _parse_ad_hoc("North Pole+, 91.0, 0.0\n")
    assert suppliers == []
    assert len(errors) == 1
    line_no, _, reason = errors[0]
    assert line_no == 1
    assert "out of range" in reason


def test_lon_out_of_range_errors():
    suppliers, errors = _parse_ad_hoc("Anywhere, 0.0, -181.0\n")
    assert suppliers == []
    assert len(errors) == 1
    _, _, reason = errors[0]
    assert "out of range" in reason


def test_non_numeric_lat_errors():
    suppliers, errors = _parse_ad_hoc("Foo, abc, 0.0\n")
    assert suppliers == []
    assert len(errors) == 1
    _, _, reason = errors[0]
    assert "must be numbers" in reason


def test_wrong_field_count_errors():
    suppliers, errors = _parse_ad_hoc(
        "Only Two, 0.0\n"
        "Way, Too, Many, 0.0\n"
    )
    assert suppliers == []
    assert len(errors) == 2
    for _, _, reason in errors:
        assert "3 comma-separated" in reason


def test_empty_name_errors():
    suppliers, errors = _parse_ad_hoc(", 0.0, 0.0\n")
    assert suppliers == []
    assert len(errors) == 1
    _, _, reason = errors[0]
    assert "name is empty" in reason


# ---------------------------------------------------------------------------
# Mixed input
# ---------------------------------------------------------------------------

def test_mixed_valid_and_invalid_returns_both():
    text = (
        "São Paulo HQ, -23.5505, -46.6333\n"
        "garbage line with no commas\n"
        "Rio Distribution, -22.9068, -43.1729\n"
        "Bad Lat, 999, 0\n"
    )
    suppliers, errors = _parse_ad_hoc(text)
    assert [s.name for s in suppliers] == ["São Paulo HQ", "Rio Distribution"]
    # Two error lines: the garbage line (no commas) and the bad-lat line.
    assert len(errors) == 2
    error_line_nos = {line_no for line_no, _, _ in errors}
    assert error_line_nos == {2, 4}


# ---------------------------------------------------------------------------
# Cap enforcement — parse-time vs run-time
# ---------------------------------------------------------------------------

def test_parser_does_not_enforce_cap():
    """Cap is enforced in the run section, not the parser. A 21-line
    list should parse to 21 entries — the warning fires later."""
    lines = "\n".join(
        f"Site {i}, 0.0, {i / 10:.1f}" for i in range(21)
    )
    suppliers, errors = _parse_ad_hoc(lines)
    assert len(suppliers) == 21
    assert errors == []


def test_max_suppliers_constant_pinned_at_20():
    """Locked design: 20-supplier batch cap."""
    assert _MAX_SUPPLIERS == 20


# ---------------------------------------------------------------------------
# Supplier dataclass shape
# ---------------------------------------------------------------------------

def test_supplier_is_frozen_with_expected_fields():
    fields = dataclasses.fields(Supplier)
    assert [f.name for f in fields] == [
        "id", "name", "lat", "lon", "source", "radius_km",
    ]
    # radius_km is an optional per-supplier override (region buffers);
    # defaults to None for node / ad-hoc suppliers.
    s = Supplier(id="x", name="X", lat=0.0, lon=0.0, source="ad_hoc")
    assert s.radius_km is None
    # Frozen — mutation raises FrozenInstanceError.
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.lat = 1.0  # type: ignore[misc]


def test_supplier_lat_lon_are_floats_after_parse():
    """The parser coerces lat/lon to float so downstream code can rely
    on the numeric type without re-checking."""
    suppliers, _ = _parse_ad_hoc("Foo, -1, 2\n")
    assert isinstance(suppliers[0].lat, float)
    assert isinstance(suppliers[0].lon, float)


# ---------------------------------------------------------------------------
# Whitespace handling
# ---------------------------------------------------------------------------

def test_whitespace_around_fields_is_stripped():
    suppliers, errors = _parse_ad_hoc(
        "  São Paulo  ,  -23.5505  ,  -46.6333  \n"
    )
    assert errors == []
    assert len(suppliers) == 1
    s = suppliers[0]
    assert s.name == "São Paulo"
    assert s.lat  == pytest.approx(-23.5505)
    assert s.lon  == pytest.approx(-46.6333)
