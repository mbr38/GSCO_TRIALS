"""Tests for ui.p11_state (M-P11.1).

Pure-Python. Pins the ReportState defaults so M-P11.2 / .3 / .4 can
rely on them when implementing later states.
"""

# M-P11.1
from __future__ import annotations

from ui.p11_state import ReportState, ReportStateKind


def test_report_state_defaults_are_sensible():
    state = ReportState()
    assert state.kind        == ReportStateKind.S1_TEMPLATE_AND_SOURCE
    assert state.template_id is None
    assert state.source_ids  == []
    assert state.title       == ""
    assert state.notes       == ""
    assert state.error       is None


def test_report_state_kinds_have_canonical_string_values():
    """The Enum's string values are what's stored when serialised —
    pin them so a save/load roundtrip stays stable."""
    assert ReportStateKind.S1_TEMPLATE_AND_SOURCE.value == "S1_TemplateAndSource"
    assert ReportStateKind.S2_PREVIEW.value             == "S2_Preview"
    assert ReportStateKind.S3_EXPORT.value              == "S3_Export"
    assert ReportStateKind.E1_FAILED.value              == "E1_Failed"
