"""Tests for ui.components.p08_ranked_table (M-P08.2).

Pure-Python — no Streamlit runtime. Targets the dataframe-building
helpers and the column_config builder. Streamlit's column_config
classes are imported by the module, which works without a running
Streamlit server (they're plain dataclass-style descriptors).
"""

# M-P08.2
from __future__ import annotations

import math

import pandas as pd
import pytest

from ui.components.p08_ranked_table import (
    _build_column_config,
    _build_ranked_dataframe,
    _extract_score,
    _rank_by_to_payload_key,
    render_rank_by_selector,
    render_ranked_table,
)
from ui.prioritisation_state import SupplierResult


_ALL_PILLARS = {"air", "ghg", "nature"}


def _supplier(
    name: str,
    status: str = "success",
    air: float | None = None,
    ghg: float | None = None,
    nature: float | None = None,
    composite: float | None = None,
    error: str | None = None,
) -> SupplierResult:
    """Build a SupplierResult with a synthetic engine payload."""
    if status in ("failed", "cancelled"):
        result = None
    else:
        result = {
            "air.audit_followup_priority": air,
            "ghg.audit_followup_priority": ghg,
            "nature.followup_priority":    nature,
            "composite.overall_screening": composite,
        }
    return SupplierResult(
        supplier_id=name.lower().replace(" ", "_"),
        name=name,
        lat=0.0, lon=0.0, source="ad_hoc",
        status=status,
        result=result,
        error=error,
    )


# ---------------------------------------------------------------------------
# _rank_by_to_payload_key
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("label, expected", [
    ("Composite", "composite.overall_screening"),
    ("Air",       "air.audit_followup_priority"),
    ("GHG",       "ghg.audit_followup_priority"),
    ("Nature",    "nature.followup_priority"),
])
def test_rank_by_to_payload_key_known_labels(label, expected):
    assert _rank_by_to_payload_key(label) == expected


def test_rank_by_to_payload_key_unknown_label_falls_back_to_composite():
    """Defensive — an unrecognised label routes to the composite key
    rather than raising. Worst case the table sorts by a column the user
    didn't ask for, not a stack trace."""
    assert _rank_by_to_payload_key("Mystery") == "composite.overall_screening"


# ---------------------------------------------------------------------------
# _extract_score
# ---------------------------------------------------------------------------

def test_extract_score_happy_path():
    assert _extract_score(
        {"air.audit_followup_priority": 0.42}, "air.audit_followup_priority",
    ) == pytest.approx(0.42)


def test_extract_score_none_result_is_none():
    assert _extract_score(None, "air.audit_followup_priority") is None


def test_extract_score_missing_key_is_none():
    assert _extract_score({}, "air.audit_followup_priority") is None


def test_extract_score_non_numeric_value_is_none():
    """Defensive — a string value shouldn't crash the table."""
    assert _extract_score(
        {"air.audit_followup_priority": "not a number"},
        "air.audit_followup_priority",
    ) is None


# ---------------------------------------------------------------------------
# _build_ranked_dataframe
# ---------------------------------------------------------------------------

def test_build_dataframe_happy_path_three_suppliers_rank_by_composite():
    suppliers = [
        _supplier("A", air=0.2, ghg=0.2, nature=0.2, composite=0.20),
        _supplier("B", air=0.5, ghg=0.5, nature=0.5, composite=0.50),
        _supplier("C", air=0.8, ghg=0.8, nature=0.8, composite=0.80),
    ]
    df = _build_ranked_dataframe(
        suppliers, _ALL_PILLARS, show_composite=True, rank_by="Composite",
    )
    # Descending composite → C, B, A.
    assert list(df["Supplier"]) == ["C", "B", "A"]
    assert list(df["Rank"])     == [1, 2, 3]


def test_build_dataframe_failed_sorts_to_end_with_no_rank():
    suppliers = [
        _supplier("A", air=0.5, ghg=0.5, nature=0.5, composite=0.5),
        _supplier("B", status="failed", error="EE timeout"),
        _supplier("C", air=0.8, ghg=0.8, nature=0.8, composite=0.8),
    ]
    df = _build_ranked_dataframe(
        suppliers, _ALL_PILLARS, show_composite=True, rank_by="Composite",
    )
    # C (0.8) first, A (0.5) second, B (failed) at the bottom.
    assert list(df["Supplier"]) == ["C", "A", "B"]
    # Ranks: 1, 2, then None for failed.
    ranks = list(df["Rank"])
    assert ranks[0] == 1
    assert ranks[1] == 2
    assert ranks[2] is None or (
        isinstance(ranks[2], float) and math.isnan(ranks[2])
    )


def test_build_dataframe_rank_by_air_not_composite():
    """Rank-by drives the order — picking Air sorts by Air, not Composite."""
    suppliers = [
        _supplier("A", air=0.9, ghg=0.1, nature=0.1, composite=0.37),
        _supplier("B", air=0.1, ghg=0.9, nature=0.9, composite=0.63),
        _supplier("C", air=0.5, ghg=0.5, nature=0.5, composite=0.50),
    ]
    df = _build_ranked_dataframe(
        suppliers, _ALL_PILLARS, show_composite=True, rank_by="Air",
    )
    # Descending Air → A (0.9), C (0.5), B (0.1).
    assert list(df["Supplier"]) == ["A", "C", "B"]
    assert list(df["Rank"])     == [1, 2, 3]


def test_build_dataframe_partial_suppliers_ranked_with_successes():
    """A partial supplier with a real rank-by score is ranked alongside
    successes — only failed/cancelled fall to the bottom."""
    suppliers = [
        _supplier("A", status="success", air=0.5, ghg=0.5, nature=0.5,
                  composite=0.5),
        _supplier("B", status="partial", air=0.9, ghg=0.9, nature=0.9,
                  composite=0.9),
        _supplier("C", status="failed", error="boom"),
    ]
    df = _build_ranked_dataframe(
        suppliers, _ALL_PILLARS, show_composite=True, rank_by="Composite",
    )
    assert list(df["Supplier"]) == ["B", "A", "C"]
    assert list(df["Rank"])[:2] == [1, 2]


def test_build_dataframe_air_only_batch_hides_other_pillars():
    """Pillar hiding from M-P08.1 carries into the ranked dataframe."""
    suppliers = [
        _supplier("A", air=0.5),
        _supplier("B", air=0.8),
    ]
    df = _build_ranked_dataframe(
        suppliers, {"air"}, show_composite=False, rank_by="Air",
    )
    assert "Air"       in df.columns
    assert "GHG"       not in df.columns
    assert "Nature"    not in df.columns
    assert "Composite" not in df.columns


def test_build_dataframe_composite_hidden_when_not_all_pillars():
    """Air + GHG batch — Composite column absent even if a payload key
    happens to be present."""
    suppliers = [
        _supplier("A", air=0.5, ghg=0.5, composite=0.5),
    ]
    df = _build_ranked_dataframe(
        suppliers, {"air", "ghg"}, show_composite=False, rank_by="Air",
    )
    assert "Air"       in df.columns
    assert "GHG"       in df.columns
    assert "Composite" not in df.columns


def test_build_dataframe_error_column_only_when_some_failed():
    """Error column appears only when at least one supplier failed with
    an error string. Pure-success batches don't get the column at all."""
    success_only = [_supplier("A", air=0.5, ghg=0.5, nature=0.5,
                              composite=0.5)]
    df_clean = _build_ranked_dataframe(
        success_only, _ALL_PILLARS, show_composite=True, rank_by="Composite",
    )
    assert "Error" not in df_clean.columns

    with_failure = [
        _supplier("A", air=0.5, ghg=0.5, nature=0.5, composite=0.5),
        _supplier("B", status="failed", error="EE timeout"),
    ]
    df_dirty = _build_ranked_dataframe(
        with_failure, _ALL_PILLARS, show_composite=True, rank_by="Composite",
    )
    assert "Error" in df_dirty.columns


# ---------------------------------------------------------------------------
# _build_column_config
# ---------------------------------------------------------------------------

def test_column_config_all_three_pillars():
    config = _build_column_config(_ALL_PILLARS, show_composite=True)
    assert set(config.keys()) == {
        "Rank", "Supplier", "Status", "Air", "GHG", "Nature", "Composite",
    }


def test_column_config_air_only():
    config = _build_column_config({"air"}, show_composite=False)
    assert set(config.keys()) == {"Rank", "Supplier", "Status", "Air"}
    assert "GHG"       not in config
    assert "Nature"    not in config
    assert "Composite" not in config


def test_column_config_score_columns_use_two_decimal_format():
    """The Air/GHG/Nature/Composite columns format scores to %.2f."""
    config = _build_column_config(_ALL_PILLARS, show_composite=True)
    for label in ("Air", "GHG", "Nature", "Composite"):
        # Streamlit's NumberColumn exposes the format via a private-ish
        # attribute; both 'format' and the kwarg name vary across
        # versions, so introspect via the column's repr to keep the
        # test robust.
        assert "%.2f" in repr(config[label])


# ---------------------------------------------------------------------------
# M-P08.2-FIX: two-function shape (selector / table split)
# ---------------------------------------------------------------------------

def test_render_functions_split_into_selector_and_table():
    """The selector and table renderers are separately importable. The
    S2_Running progress callback re-renders the table without re-rendering
    the radio — same-key crash regression guard.
    """
    import inspect

    # Selector takes only `state`.
    sig_sel = inspect.signature(render_rank_by_selector)
    assert list(sig_sel.parameters) == ["state"]

    # Table takes `state` + `rank_by` (in that order).
    sig_tbl = inspect.signature(render_ranked_table)
    assert list(sig_tbl.parameters) == ["state", "rank_by"]
