"""Tests for ui.components.p11_templates (M-P11.1 / M-REPORT-A1).

Pure-Python — no Streamlit. Pins the M-REPORT-A1 five-registration inventory
(spec §3), the dual-membership of the General + Trend reports, per-template
pillar/ESRS metadata, and defensive lookup behaviour.
"""

# M-P11.1 / M-REPORT-A1
from __future__ import annotations

from ui.components.p11_templates import (
    ALL_PILLARS,
    _TEMPLATES,
    ReportTemplate,
    get_template,
    templates_for,
)


# ---------------------------------------------------------------------------
# templates_for — user-type membership (RT7/RT8/RT11)
# ---------------------------------------------------------------------------

def test_templates_for_policy_maker_sees_general_and_trend():
    ids = [t.template_id for t in templates_for("policy_maker")]
    assert ids == ["general", "trend"]


def test_templates_for_mnc_sees_four_plus_trend():
    ids = [t.template_id for t in templates_for("mnc")]
    assert ids == ["general", "mnc_ghg", "mnc_air", "mnc_nature", "trend"]


def test_general_and_trend_belong_to_both_user_types():
    for tid in ("general", "trend"):
        t = get_template(tid)
        assert t.user_types == frozenset({"policy_maker", "mnc"})


def test_pillar_reports_are_mnc_only():
    for tid in ("mnc_ghg", "mnc_air", "mnc_nature"):
        assert get_template(tid).user_types == frozenset({"mnc"})


def test_templates_for_unknown_user_type_returns_empty():
    """Defensive — an unrecognised user_type should not crash."""
    assert templates_for("future_role") == []
    assert templates_for("") == []


# ---------------------------------------------------------------------------
# get_template — direct lookup
# ---------------------------------------------------------------------------

def test_get_template_known_id_returns_template():
    t = get_template("general")
    assert isinstance(t, ReportTemplate)
    assert t.template_id == "general"


def test_get_template_unknown_id_returns_none():
    assert get_template("nonexistent") is None


# ---------------------------------------------------------------------------
# Pillar + ESRS metadata (RT5/RT6/RT9)
# ---------------------------------------------------------------------------

def test_general_covers_all_pillars_and_is_esrs_capable():
    t = get_template("general")
    assert t.pillars == ALL_PILLARS
    assert t.esrs is True


def test_pillar_reports_each_cover_one_pillar_and_are_esrs():
    expected = {"mnc_ghg": "ghg", "mnc_air": "air", "mnc_nature": "nature"}
    for tid, pillar in expected.items():
        t = get_template(tid)
        assert t.pillars == frozenset({pillar})
        assert t.esrs is True


def test_trend_report_is_not_esrs_and_accepts_only_trend():
    t = get_template("trend")
    assert t.esrs is False
    assert t.accepted_source_types == frozenset({"trend"})


def test_trend_template_uses_per_indicator_structure_not_composite():
    t = get_template("trend")
    # Option A (RT9): own per-indicator structure, no composite-bearing sections.
    assert "trend_indicator_sections" in t.sections
    assert "executive_summary" not in t.sections   # carries composite table
    assert "pillar_findings" not in t.sections


def test_every_report_carries_a_glossary_appendix():
    """RT12 — all reports carry the content-aware glossary."""
    for t in _TEMPLATES:
        assert "glossary" in t.sections


# ---------------------------------------------------------------------------
# Registry-wide invariants
# ---------------------------------------------------------------------------

def test_registry_has_five_templates():
    assert len(_TEMPLATES) == 5


def test_every_template_has_non_empty_sections():
    for t in _TEMPLATES:
        assert len(t.sections) > 0


def test_every_template_accepts_only_known_source_types():
    allowed = {"screening", "prioritisation", "trend"}
    for t in _TEMPLATES:
        assert t.accepted_source_types.issubset(allowed), (
            f"{t.template_id} accepts unknown source types: "
            f"{t.accepted_source_types - allowed}"
        )


def test_every_template_has_known_user_types():
    allowed = {"policy_maker", "mnc"}
    for t in _TEMPLATES:
        assert t.user_types.issubset(allowed)
        assert t.user_types  # non-empty


def test_no_duplicate_template_ids():
    ids = [t.template_id for t in _TEMPLATES]
    assert len(ids) == len(set(ids))
