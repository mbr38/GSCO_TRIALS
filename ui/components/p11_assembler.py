"""P-11 report assembler (M-P11.2).

Single public function: ``build_report_html(state, sources, template)``.
Returns a complete HTML document — used by the preview renderer
(M-P11.2) and the PDF export pipeline (M-P11.3).
"""

# M-P11.2
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ui.components.p11_sections  import get_section
from ui.components.p11_templates import ReportTemplate
from ui.p11_state                import ReportState


_SHELL_DIR = Path(__file__).resolve().parent.parent.parent / "templates" / "p11"

_env = Environment(
    loader=FileSystemLoader(_SHELL_DIR),
    autoescape=select_autoescape(["html", "j2"]),
)


def build_report_html(
    state: ReportState,
    sources: list[dict],
    template: ReportTemplate,
) -> str:
    """Compose the report's full HTML document."""
    section_fragments: list[str] = []
    for section_key in template.sections:
        section_fn = get_section(section_key)
        if section_fn is None:
            section_fragments.append(
                f"<section><p><em>Section '{section_key}' "
                f"not implemented.</em></p></section>"
            )
            continue
        try:
            fragment = section_fn(state, sources)
            section_fragments.append(fragment)
        except Exception as exc:  # noqa: BLE001
            section_fragments.append(
                f"<section><p><em>Section '{section_key}' "
                f"failed to render: {exc}</em></p></section>"
            )

    shell = _env.get_template("shell.html.j2")
    title_text = (state.title or "").strip() or "Untitled report"
    return shell.render(
        title=title_text,
        sections_html="\n".join(section_fragments),
    )
