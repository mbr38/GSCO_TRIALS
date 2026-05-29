"""Tests for ui.components.p11_templates (M-P11.1).

Pure-Python — no Streamlit. Pins the registry shape, the user-type
hard branch (Policy Maker → 1 template; MNC → 1 template), and
defensive lookup behaviour.
"""

# M-P11.1
from __future__ import annotations

from ui.components.p11_templates import (
    _TEMPLATES,
    ReportTemplate,
    get_template,
    templates_for,
)


# ---------------------------------------------------------------------------
# templates_for — user-type filter
# ---------------------------------------------------------------------------

def test_templates_for_policy_maker_returns_one_template():
    out = templates_for("policy_maker")
    assert len(out) == 1
    assert out[0].template_id  == "policy_audit"
    assert out[0].display_name == "Policy audit report"


def test_templates_for_mnc_returns_one_template():
    out = templates_for("mnc")
    assert len(out) == 1
    assert out[0].template_id  == "supplier_audit"
    assert out[0].display_name == "Supplier audit report"


def test_templates_for_unknown_user_type_returns_empty():
    """Defensive — an unrecognised user_type should not crash."""
    assert templates_for("future_role") == []
    assert templates_for("") == []


# ---------------------------------------------------------------------------
# get_template — direct lookup
# ---------------------------------------------------------------------------

def test_get_template_known_id_returns_template():
    t = get_template("policy_audit")
    assert isinstance(t, ReportTemplate)
    assert t.template_id == "policy_audit"


def test_get_template_unknown_id_returns_none():
    assert get_template("nonexistent") is None


# ---------------------------------------------------------------------------
# Registry-wide invariants
# ---------------------------------------------------------------------------

def test_every_template_has_non_empty_sections():
    """Each template needs at least one section — the preview / PDF
    rendering iterates the tuple, so an empty list would produce an
    empty report."""
    for t in _TEMPLATES:
        assert len(t.sections) > 0


def test_every_template_accepts_only_known_source_types():
    """Source types are filtered against saved_analyses ``type`` field.
    The store writes ``"screening"``, ``"prioritisation"``, and — since
    M-TREND-A2 (UT10) — ``"trend"``. Accepting other values would silently
    exclude no real sources, but the intent should stay explicit."""
    allowed = {"screening", "prioritisation", "trend"}
    for t in _TEMPLATES:
        assert t.accepted_source_types.issubset(allowed), (
            f"{t.template_id} accepts unknown source types: "
            f"{t.accepted_source_types - allowed}"
        )


def test_no_duplicate_template_ids():
    ids = [t.template_id for t in _TEMPLATES]
    assert len(ids) == len(set(ids))
