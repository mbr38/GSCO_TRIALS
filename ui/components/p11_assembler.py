"""P-11 report assembler (M-P11.2).

Single public function: ``build_report_html(state, sources, template)``.
Returns a complete HTML document — used by the preview renderer
(M-P11.2) and the PDF export pipeline (M-P11.3).
"""

# M-P11.2
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ui.components.p11_glossary  import render_glossary
from ui.components.p11_sections  import RenderContext, get_section
from ui.components.p11_templates import ReportTemplate
from ui.p11_state                import ReportState


_SHELL_DIR = Path(__file__).resolve().parent.parent.parent / "templates" / "p11"

# M-REPORT-A1: the content-aware glossary (RT13) is not an ordinary section —
# it scans the rest of the rendered report, so the assembler builds it last and
# slots it back into its declared position rather than calling get_section.
_GLOSSARY_KEY = "glossary"

_env = Environment(
    loader=FileSystemLoader(_SHELL_DIR),
    autoescape=select_autoescape(["html", "j2"]),
)


def build_report_html(
    state: ReportState,
    sources: list[dict],
    template: ReportTemplate,
) -> str:
    """Compose the report's full HTML document.

    M-REPORT-A1: a ``RenderContext`` (built from the template + the active
    ``user_type`` on ``state``) is threaded into every section so the General
    report's dual framing (RT8) and the ESRS layer (RT4) resolve at render time.
    The glossary section is deferred and rendered from the joined body of the
    other sections (content-aware, RT13).
    """
    ctx = RenderContext.from_template(template, getattr(state, "user_type", ""))

    # Render each section to a slot, deferring the glossary.
    fragments: list[str] = [""] * len(template.sections)
    glossary_index: int | None = None
    for i, section_key in enumerate(template.sections):
        if section_key == _GLOSSARY_KEY:
            glossary_index = i
            continue
        fragments[i] = _render_one_section(section_key, state, sources, ctx)

    if glossary_index is not None:
        # Scan everything else for known terms (RT13). Order doesn't affect the
        # scan, so building from the other slots is safe.
        body_so_far = "\n".join(f for f in fragments if f)
        fragments[glossary_index] = render_glossary(body_so_far)

    shell = _env.get_template("shell.html.j2")
    title_text = (state.title or "").strip() or "Untitled report"
    return shell.render(
        title=title_text,
        sections_html="\n".join(fragments),
    )


def _render_one_section(section_key, state, sources, ctx) -> str:
    """Render a single section, isolating per-section failures (one broken
    section never blanks the whole report)."""
    section_fn = get_section(section_key)
    if section_fn is None:
        return (
            f"<section><p><em>Section '{section_key}' "
            f"not implemented.</em></p></section>"
        )
    try:
        return section_fn(state, sources, ctx)
    except Exception as exc:  # noqa: BLE001
        return (
            f"<section><p><em>Section '{section_key}' "
            f"failed to render: {exc}</em></p></section>"
        )
