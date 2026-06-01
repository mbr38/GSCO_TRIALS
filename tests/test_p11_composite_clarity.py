"""Tests for M-REPORT-A2 composite-row disambiguation (RA2/RA3).

The executive-summary composite column shows the whole-screening
``overall_screening`` (all three pillars). In a single-pillar ESRS report it is
relabelled + carries a scope-of-composite note; the General report (all pillars)
is unchanged. The trigger keys off pillar cardinality, not user_type/template_id.

Pure-Python: synthetic payload, direct section call + assembler end-to-end.
"""

# M-REPORT-A2
from __future__ import annotations

from types import SimpleNamespace

from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS
from ui.components.p11_assembler import build_report_html
from ui.components.p11_sections import RenderContext, _render_executive_summary
from ui.components.p11_templates import get_template

_LABEL = "Overall screening composite (all 3 pillars)"
_NOTE = "overall screening composite above reflects all three pillars"


def _source():
    return {
        "id": "s1", "name": "Acme Plant", "type": "screening",
        "screening_setup": {
            "indicators": list(ALL_INDICATOR_IDS),
            "centre": {"lat": 1.0, "lon": 2.0}, "radius_km": 5,
            "time_range": ["2026-01-01", "2026-03-01"],
        },
        "payload": {"composite.overall_screening": 0.5},
    }


def _state():
    return SimpleNamespace(title="Q2", notes="", user_type="mnc",
                           template_id="x")


# ---------------------------------------------------------------------------
# Section-level: predicate keys off pillar cardinality (RA3)
# ---------------------------------------------------------------------------

def test_single_pillar_relabels_and_adds_note():
    ctx = RenderContext(user_type="mnc", pillars=frozenset({"ghg"}),
                        apply_esrs=True, template_id="mnc_ghg")
    out = _render_executive_summary(_state(), [_source()], ctx)
    assert _LABEL in out
    assert _NOTE in out
    assert "Climate change pillar only" in out  # E1 topic resolved from RT6 map


def test_all_pillars_unchanged():
    ctx = RenderContext(user_type="mnc",
                        pillars=frozenset({"air", "ghg", "nature"}),
                        apply_esrs=True, template_id="general")
    out = _render_executive_summary(_state(), [_source()], ctx)
    assert _LABEL not in out
    assert _NOTE not in out
    assert "<th>Composite</th>" in out


def test_predicate_is_cardinality_not_user_type():
    # A single-pillar context fires the clarification regardless of user_type.
    for ut in ("mnc", "policy_maker", ""):
        ctx = RenderContext(user_type=ut, pillars=frozenset({"air"}),
                            apply_esrs=(ut == "mnc"), template_id="mnc_air")
        out = _render_executive_summary(_state(), [_source()], ctx)
        assert _LABEL in out
        assert "Pollution pillar only" in out  # E2 topic


def test_no_ctx_defaults_to_all_pillars_unchanged():
    # Direct 2-arg call (no ctx) → all-pillars default → original bare header.
    out = _render_executive_summary(_state(), [_source()])
    assert _LABEL not in out
    assert "<th>Composite</th>" in out


# ---------------------------------------------------------------------------
# End-to-end via the assembler
# ---------------------------------------------------------------------------

def _build(user_type, template_id):
    st = SimpleNamespace(title="Q2", notes="", user_type=user_type,
                         template_id=template_id)
    return build_report_html(st, [_source()], get_template(template_id))


def test_pillar_reports_carry_clarification():
    for tid in ("mnc_ghg", "mnc_air", "mnc_nature"):
        out = _build("mnc", tid)
        assert _LABEL in out
        assert _NOTE in out


def test_general_report_has_no_clarification_either_framing():
    for ut in ("mnc", "policy_maker"):
        out = _build(ut, "general")
        assert _LABEL not in out
        assert _NOTE not in out
