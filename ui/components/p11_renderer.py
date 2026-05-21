"""P-11 renderer (M-P11.1).

Dispatches to state-specific renderers. M-P11.1 implements
S1_TemplateAndSource fully; later states render placeholder
messages until their milestones land (M-P11.2 / .3 / .4).
"""

# M-P11.1
from __future__ import annotations

import streamlit as st

from ui.components.p11_templates import get_template, templates_for
from ui.p11_state import ReportState, ReportStateKind


def render_p11() -> None:
    state = _get_or_init_state()
    if state.kind == ReportStateKind.S1_TEMPLATE_AND_SOURCE:
        _render_s1(state)
    elif state.kind == ReportStateKind.S2_PREVIEW:
        _render_s2_placeholder(state)
    elif state.kind == ReportStateKind.S3_EXPORT:
        _render_s3_placeholder(state)
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
    templates = templates_for(user_type)

    if not templates:
        st.warning(
            "No report templates available for your user type. "
            "Templates: Policy Maker → Policy audit report; "
            "MNC → Supplier audit report.",
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
    selected_labels = st.multiselect(
        "Pick one or more saved analyses to include",
        options=list(source_options.keys()),
        key="p11_source_select",
    )
    state.source_ids = [source_options[label] for label in selected_labels]

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

def _render_s2_placeholder(state: ReportState) -> None:
    st.info(
        "**Preview lands in M-P11.2.** Template + source(s) selected. "
        "Once the preview milestone ships, this view will render the "
        "full report in HTML with section toggles.",
        icon="📄",
    )
    _render_back_button(state)


def _render_s3_placeholder(state: ReportState) -> None:
    st.info(
        "**Export lands in M-P11.3 (PDF) and M-P11.4 (CSV/JSON).**",
        icon="📥",
    )
    _render_back_button(state)


def _render_back_button(state: ReportState) -> None:
    if st.button(
        "← Back to template selection", key="p11_back_s1",
    ):
        state.kind = ReportStateKind.S1_TEMPLATE_AND_SOURCE
        st.rerun()
