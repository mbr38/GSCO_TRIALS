"""P-11 renderer (M-P11.1 / M-P11.2 / M-P11.3).

Dispatches to state-specific renderers. M-P11.1 wires
S1_TemplateAndSource; M-P11.2 wires S2_Preview to render the real
HTML report (assembled by ``p11_assembler.build_report_html``);
M-P11.3 wires S3_Export to generate + download a PDF via
weasyprint. CSV / JSON exports land in M-P11.4.
"""

# M-P11.1
from __future__ import annotations

import re
from datetime import datetime, timezone

import streamlit as st
import streamlit.components.v1 as st_components

from ui.components.p11_assembler import build_report_html
from ui.components.p11_csv       import render_csv
from ui.components.p11_json      import render_json
from ui.components.p11_pdf       import PdfDependencyError, render_pdf
from ui.components.p11_sections  import highest_priority_pillar
from ui.components.p11_templates import get_template, templates_for
from ui.p11_state import ReportState, ReportStateKind


def render_p11() -> None:
    state = _get_or_init_state()
    if state.kind == ReportStateKind.S1_TEMPLATE_AND_SOURCE:
        _render_s1(state)
    elif state.kind == ReportStateKind.S2_PREVIEW:
        _render_s2(state)
    elif state.kind == ReportStateKind.S3_EXPORT:
        _render_s3(state)
    else:
        st.error(f"Unknown report state: {state.kind}", icon="⚠️")


def _get_or_init_state() -> ReportState:
    state = st.session_state.get("report_state")
    if state is None:
        state = ReportState()
        st.session_state["report_state"] = state
    return state


# ──────────────────────────────────────────────────────────────────
# S1 — template + source picker
# ──────────────────────────────────────────────────────────────────

def _render_s1(state: ReportState) -> None:
    user_type = st.session_state.get("user_type", "")
    # M-REPORT-A1: capture the active user type onto the report state so the
    # assembler can resolve the General report's dual framing (RT8) and the
    # ESRS layer (RT4) at render time, rather than off two separate template IDs.
    state.user_type = user_type
    templates = templates_for(user_type)

    if not templates:
        st.warning(
            "No report templates available for your user type. "
            "Templates: Policy Maker → General report + Trend report; "
            "MNC → General, GHG (E1), Air (E2), Nature (E4) + Trend report.",
            icon="⚠️",
        )
        return

    # Template selector.
    st.markdown("### Template")
    template_options = {t.display_name: t.template_id for t in templates}
    selected_label = st.selectbox(
        "Choose a report template",
        options=list(template_options.keys()),
        index=0,
        key="p11_template_select",
    )
    state.template_id = template_options[selected_label]
    template = get_template(state.template_id)
    if template:
        st.caption(template.description)

    # Source picker, filtered to compatible saved-analysis types.
    st.markdown("### Sources")
    saved = st.session_state.get("saved_analyses", [])
    compatible = [
        s for s in saved
        if s.get("type") in template.accepted_source_types
    ]

    if not compatible:
        st.info(
            "No compatible saved analyses yet. Save a screening "
            "or prioritisation result first (P-05, P-08), then "
            "return here to build a report.",
            icon="📋",
        )
        _disabled_preview_button()
        return

    source_options = {
        f"{s.get('name', 'Unnamed')} ({s.get('type', '?')})": s["id"]
        for s in compatible
    }
    # M-REPORT-COOP: the supplier cooperation report is single-supplier by
    # design (no cross-supplier ranking), so it picks exactly one source via a
    # selectbox rather than the multi-select other templates use.
    if state.template_id == "supplier_cooperation":
        selected_label = st.selectbox(
            "Pick the saved analysis (one supplier)",
            options=list(source_options.keys()),
            index=None,
            placeholder="Choose a saved analysis",
            key="p11_source_select_single",
        )
        state.source_ids = (
            [source_options[selected_label]] if selected_label else []
        )
    else:
        selected_labels = st.multiselect(
            "Pick one or more saved analyses to include",
            options=list(source_options.keys()),
            key="p11_source_select",
        )
        state.source_ids = [source_options[label] for label in selected_labels]

    # M-REPORT-COOP: the supplier cooperation report renders one user-chosen
    # pillar. Surface a pillar picker only for that template; every other
    # template leaves ``state.pillar`` None so a stale value can't narrow a
    # fixed-pillar or all-pillar report.
    state.pillar = None
    if state.template_id == "supplier_cooperation":
        _render_coop_pillar_picker(state, compatible)

    # Title + notes. Widget keys manage persistence across reruns; the
    # state assignments capture the current value for validation.
    st.markdown("### Title and notes")
    state.title = st.text_input(
        "Report title (will appear on the title page)",
        placeholder="e.g. Q2 2026 audit — Brazilian Soy & Cattle suppliers",
        key="p11_title",
    )
    state.notes = st.text_area(
        "Additional notes (optional, included in the report's introduction)",
        height=100,
        key="p11_notes",
    )

    # Preview button.
    can_preview = bool(
        state.template_id and state.source_ids and state.title.strip()
    )
    if not can_preview:
        missing: list[str] = []
        if not state.template_id:
            missing.append("template")
        if not state.source_ids:
            missing.append("at least one source")
        if not state.title.strip():
            missing.append("title")
        st.caption(f"Missing: {', '.join(missing)}.")

    if st.button(
        "Next: Preview report",
        type="primary",
        disabled=not can_preview,
        use_container_width=True,
    ):
        state.kind = ReportStateKind.S2_PREVIEW
        st.rerun()


# M-REPORT-COOP
_COOP_PILLAR_ORDER = ("air", "ghg", "nature")
_COOP_PILLAR_LABELS = {
    "air": "Air pollution", "ghg": "GHG emissions", "nature": "Nature & land",
}


def _render_coop_pillar_picker(state: ReportState, compatible: list[dict]) -> None:
    """Pillar selector for the supplier cooperation report.

    Defaults to the (first) selected source's highest follow-up-priority pillar
    — the natural focus — but the choice is the user's. Writes the chosen pillar
    onto ``state.pillar``; the assembler threads it into the RenderContext.
    """
    st.markdown("### Pillar")
    default_pillar = "nature"
    selected = [s for s in compatible if s["id"] in state.source_ids]
    if selected:
        default_pillar = highest_priority_pillar(selected[0].get("payload") or {})
    default_idx = (
        _COOP_PILLAR_ORDER.index(default_pillar)
        if default_pillar in _COOP_PILLAR_ORDER else 0
    )
    choice = st.selectbox(
        "Which pillar should this cooperation report address?",
        options=[_COOP_PILLAR_LABELS[p] for p in _COOP_PILLAR_ORDER],
        index=default_idx,
        key="p11_coop_pillar",
        help=(
            "Defaults to the pillar with the highest follow-up priority for "
            "the selected supplier — you can change it."
        ),
    )
    inverse = {v: k for k, v in _COOP_PILLAR_LABELS.items()}
    state.pillar = inverse[choice]


def _disabled_preview_button() -> None:
    st.button(
        "Next: Preview report",
        type="primary",
        disabled=True,
        use_container_width=True,
        key="p11_preview_disabled",
    )


# ──────────────────────────────────────────────────────────────────
# S2 / S3 placeholders
# ──────────────────────────────────────────────────────────────────

# M-P11.2
def _render_s2(state: ReportState) -> None:
    template = get_template(state.template_id)
    if template is None:
        st.error("Template missing — return to selection.", icon="⚠️")
        _render_back_button(state)
        return

    saved = st.session_state.get("saved_analyses", [])
    sources = [s for s in saved if s["id"] in state.source_ids]

    if not sources:
        st.error(
            "Selected sources are no longer available. They may "
            "have been deleted. Return to selection.",
            icon="⚠️",
        )
        _render_back_button(state)
        return

    try:
        report_html = build_report_html(state, sources, template)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to render preview: {exc}", icon="⚠️")
        _render_back_button(state)
        return

    # Top bar: nav + route to S3_Export (M-P11.3).
    col_back, col_export = st.columns([1, 1])
    with col_back:
        _render_back_button(state)
    with col_export:
        # M-P11.3
        if st.button(
            "Continue to Export →",
            type="primary",
            use_container_width=True,
            key="p11_s2_to_export",
        ):
            state.kind = ReportStateKind.S3_EXPORT
            st.rerun()

    st.divider()

    # Render the HTML inside Streamlit using components.html.
    # Iframe-isolated; the report's CSS doesn't leak into the app.
    st_components.html(report_html, height=800, scrolling=True)


# ──────────────────────────────────────────────────────────────────
# S3 — Export (M-P11.3 wires PDF; CSV / JSON land in M-P11.4)
# ──────────────────────────────────────────────────────────────────

# M-P11.3
def _render_s3(state: ReportState) -> None:
    template = get_template(state.template_id)
    if template is None:
        st.error("Template missing — return to selection.", icon="⚠️")
        _render_back_button(state)
        return

    saved = st.session_state.get("saved_analyses", [])
    sources = [s for s in saved if s["id"] in state.source_ids]
    if not sources:
        st.error(
            "Selected sources are no longer available. Return to "
            "selection to pick again.",
            icon="⚠️",
        )
        _render_back_button(state)
        return

    st.markdown("### Export")
    st.caption(
        "Generate and download your report. PDF is the primary "
        "export format; CSV and JSON exports land in M-P11.4."
    )

    # Assemble HTML once — the export branches (PDF now, CSV/JSON
    # later) all share it.
    try:
        report_html = build_report_html(state, sources, template)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to assemble report HTML: {exc}", icon="⚠️")
        _render_back_button(state)
        return

    col_pdf, col_csv, col_json = st.columns(3)
    with col_pdf:
        _render_pdf_export(state, report_html)
    with col_csv:
        _render_csv_export(state, sources)  # M-P11.4
    with col_json:
        _render_json_export(state, sources, template)  # M-P11.4

    st.divider()
    _render_back_button(state)


# M-P11.3
def _render_pdf_export(state: ReportState, report_html: str) -> None:
    """Two-step PDF UX: Generate → Download.

    The render is ~3-5 sec on first call (Pango/Cairo cold-start +
    layout). Caching the bytes in session state means re-clicking on
    the same setup is instant; changing template / sources / title /
    notes invalidates the cache and re-prompts a fresh render.
    """
    cache_key = _pdf_cache_key(state)
    cached = st.session_state.get("p11_pdf_cache")

    if cached and cached.get("key") == cache_key:
        filename = _build_filename(state, "pdf")
        st.download_button(
            "📄 Download PDF",
            data=cached["bytes"],
            file_name=filename,
            mime="application/pdf",
            type="primary",
            use_container_width=True,
            key="p11_pdf_download",
        )
        st.caption(
            f"Generated {cached['size_kb']} KB · {cached['generated_at']}"
        )
        return

    if st.button(
        "Generate PDF",
        type="primary",
        use_container_width=True,
        key="p11_pdf_generate",
    ):
        with st.spinner("Rendering PDF…"):
            try:
                pdf_bytes = render_pdf(report_html)
            except PdfDependencyError as exc:  # M-P11-FIX
                _render_pdf_deps_error(exc)
                return
            except Exception as exc:  # noqa: BLE001
                st.error(f"PDF generation failed: {exc}", icon="⚠️")
                return
        st.session_state["p11_pdf_cache"] = {
            "key":          cache_key,
            "bytes":        pdf_bytes,
            "size_kb":      round(len(pdf_bytes) / 1024, 1),
            "generated_at": datetime.now(timezone.utc).strftime("%H:%M UTC"),
        }
        st.rerun()


# M-P11.4
def _render_csv_export(state: ReportState, sources: list[dict]) -> None:
    """CSV export — one-shot download (no two-step like PDF).

    CSV generation is fast (<100 ms even for multi-source reports),
    so the spinner / cache pattern isn't worth the UX cost. The
    button surfaces directly as ``st.download_button``.
    """
    try:
        csv_string = render_csv(state, sources)
    except Exception as exc:  # noqa: BLE001
        st.error(f"CSV generation failed: {exc}", icon="⚠️")
        return
    filename = _build_filename(state, "csv")
    st.download_button(
        "📊 Download CSV",
        data=csv_string.encode("utf-8"),
        file_name=filename,
        mime="text/csv",
        use_container_width=True,
        key="p11_csv_download",
    )
    # Header line + data lines; trailing newline doesn't count.
    n_rows = max(csv_string.count("\n") - 1, 0)
    st.caption(f"Flat per-indicator table · {n_rows} rows")


# M-P11.4
def _render_json_export(state: ReportState, sources: list[dict], template) -> None:
    """JSON export — one-shot download."""
    try:
        json_string = render_json(state, sources, template)
    except Exception as exc:  # noqa: BLE001
        st.error(f"JSON generation failed: {exc}", icon="⚠️")
        return
    filename = _build_filename(state, "json")
    data_bytes = json_string.encode("utf-8")
    st.download_button(
        "📦 Download JSON",
        data=data_bytes,
        file_name=filename,
        mime="application/json",
        use_container_width=True,
        key="p11_json_download",
    )
    st.caption(f"Report-wrapped JSON · {max(len(data_bytes) // 1024, 1)} KB")


# M-P11-FIX
def _render_pdf_deps_error(exc: PdfDependencyError) -> None:
    """Friendly missing-deps surface with platform-specific install
    commands, in place of the raw weasyprint dlopen traceback."""
    st.error(
        "**PDF generation isn't available** — the host machine is "
        "missing one of weasyprint's native dependencies (Pango, "
        "Cairo, or GLib).",
        icon="⚠️",
    )
    with st.expander("How to fix this"):
        st.markdown(
            "**macOS** (Homebrew):\n"
            "```bash\n"
            "brew install pango cairo glib\n"
            "```\n"
            "If the install completed but PDF still fails, the dyld "
            "search path may need updating. Add to `~/.zshrc`:\n"
            "```bash\n"
            "export DYLD_FALLBACK_LIBRARY_PATH="
            "$(brew --prefix)/lib:$DYLD_FALLBACK_LIBRARY_PATH\n"
            "```\n"
            "Then restart the terminal and Streamlit.\n\n"
            "**Linux** (Debian / Ubuntu):\n"
            "```bash\n"
            "apt-get install libpango-1.0-0 libpangoft2-1.0-0 "
            "libcairo2 libglib2.0-0\n"
            "```\n\n"
            "**Windows**: see [weasyprint's installation guide]"
            "(https://doc.courtbouillon.org/weasyprint/stable/"
            "first_steps.html#windows).\n\n"
            "Raw error for diagnosis:"
        )
        st.code(str(exc), language="text")


# M-P11.3
def _pdf_cache_key(state: ReportState) -> str:
    """Cache key — invalidates when template / sources / title / notes change.

    M-REPORT-A1: includes ``user_type`` because the General report is dual-framed
    by user type (RT8) — the same template_id renders ESRS-framed for an MNC and
    plain for a policy maker, so the two must not share a cached PDF.
    """
    return (
        f"{state.template_id}|"
        f"{getattr(state, 'user_type', '')}|"
        # M-REPORT-COOP: the cooperation report's pillar is user-chosen, so two
        # renders differing only by pillar must not share a cached PDF.
        f"{getattr(state, 'pillar', None)}|"
        f"{','.join(sorted(state.source_ids))}|"
        f"{state.title}|"
        f"{state.notes}"
    )


# M-P11.3 / M-P11.4
def _build_filename(state: ReportState, ext: str) -> str:
    """Build a safe download filename: ``<sanitised-title>_<date>.<ext>``.

    Strips path-unsafe characters, collapses whitespace to underscores,
    and truncates the title to 60 chars to keep filenames reasonable.
    Empty / whitespace-only titles default to ``"report"``. The
    ``ext`` argument lets all three exports (PDF / CSV / JSON) share
    the same naming convention.
    """
    raw_title = (state.title or "").strip() or "report"
    safe_title = re.sub(r"[^\w\s-]", "", raw_title).strip()
    safe_title = re.sub(r"\s+", "_", safe_title)[:60] or "report"
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{safe_title}_{date_str}.{ext}"


def _render_back_button(state: ReportState) -> None:
    if st.button(
        "← Back to template selection", key="p11_back_s1",
    ):
        state.kind = ReportStateKind.S1_TEMPLATE_AND_SOURCE
        st.rerun()
