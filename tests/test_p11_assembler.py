"""Tests for ui.components.p11_assembler (M-P11.2).

The assembler walks a template's section tuple, calls each function,
and stitches the output into the Jinja shell. Tests pin the call
order, exception-resilience, unknown-section handling, and shell
title rendering.
"""

# M-P11.2
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from ui.components import p11_assembler
from ui.components.p11_assembler import build_report_html
from ui.components.p11_templates import ReportTemplate


def _fake_state(title="Demo title"):
    return SimpleNamespace(title=title, notes="")


def _template(sections):
    return ReportTemplate(
        template_id="test_tpl",
        display_name="Test template",
        description="—",
        user_type="policy_maker",
        accepted_source_types=frozenset({"screening"}),
        sections=tuple(sections),
    )


# ---------------------------------------------------------------------------
# 5n. order of sections preserved
# ---------------------------------------------------------------------------

def test_build_report_html_calls_sections_in_template_order():
    call_log = []

    def make_fn(tag):
        def _fn(state, sources):
            call_log.append(tag)
            return f"<section data-tag='{tag}'>{tag}</section>"
        return _fn

    registry = {
        "alpha": make_fn("alpha"),
        "beta":  make_fn("beta"),
        "gamma": make_fn("gamma"),
    }
    with patch.object(
        p11_assembler, "get_section", side_effect=lambda k: registry.get(k),
    ):
        out = build_report_html(
            _fake_state(),
            sources=[],
            template=_template(["alpha", "beta", "gamma"]),
        )

    assert call_log == ["alpha", "beta", "gamma"]
    # Fragments appear in order in the output.
    assert out.index("alpha") < out.index("beta") < out.index("gamma")


# ---------------------------------------------------------------------------
# 5o. exception-resilience
# ---------------------------------------------------------------------------

def test_build_report_html_section_exception_renders_inline_placeholder():
    def good(state, sources): return "<section>good-section</section>"
    def boom(state, sources): raise RuntimeError("intentional explosion")

    registry = {"good": good, "boom": boom}
    with patch.object(
        p11_assembler, "get_section", side_effect=lambda k: registry.get(k),
    ):
        out = build_report_html(
            _fake_state(),
            sources=[],
            template=_template(["good", "boom"]),
        )

    assert "good-section" in out
    assert "failed to render" in out
    assert "intentional explosion" in out


# ---------------------------------------------------------------------------
# 5p. unknown section key
# ---------------------------------------------------------------------------

def test_build_report_html_unknown_section_produces_placeholder():
    with patch.object(
        p11_assembler, "get_section", return_value=None,
    ):
        out = build_report_html(
            _fake_state(),
            sources=[],
            template=_template(["ghost_section"]),
        )
    assert "not implemented" in out
    assert "ghost_section" in out


# ---------------------------------------------------------------------------
# 5q. shell title threading
# ---------------------------------------------------------------------------

def test_build_report_html_title_appears_in_title_tag():
    # Use the real section registry — empty section tuple is fine for
    # exercising the shell renderer.
    out = build_report_html(
        _fake_state(title="Quarterly Audit Q2"),
        sources=[],
        template=_template([]),
    )
    assert "<title>Quarterly Audit Q2</title>" in out


def test_build_report_html_empty_title_uses_untitled_report():
    out = build_report_html(
        _fake_state(title=""),
        sources=[],
        template=_template([]),
    )
    assert "<title>Untitled report</title>" in out


def test_build_report_html_emits_full_html_document():
    out = build_report_html(
        _fake_state(),
        sources=[],
        template=_template([]),
    )
    assert "<!DOCTYPE html>" in out
    assert "<html" in out
    assert "</html>" in out
    assert "<body>" in out
