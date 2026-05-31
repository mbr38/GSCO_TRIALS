"""Per-setup-page guided tutorial (M-TUTORIAL-A1).

A themed, dismissible, step-by-step "Quick tour" rendered with native
Streamlit widgets inside an ``st.dialog`` modal. One tutorial per setup
page (P-02 / P-04 / P-07), each scoped to that page's own flow. The
panel steps through the page's flow one card at a time with
Back / Next / Done / Skip controls — the sequential, guided feel of a
coachmark overlay, but built entirely from native widgets styled with
the existing ``ui.theme`` tokens (no JS spotlight, no widget-anchored
DOM highlight — see the spec's §2 rationale and
``UI_Theming_Session_Handoff.md``).

Public API (call once per setup page, just below the persistent nav):

    render_tutorial_trigger(tutorial_id)   # tutorial_id ∈ {"P-02","P-04","P-07"}

Manual-only for the demo: the tour opens solely on the "Show me around"
button click. There is no first-visit auto-open and no seen-tracking
(spec §6). The only session state is the current step index while a
dialog is open, namespaced under ``_tutorial_step``.

Authority: M-TUTORIAL-A1 spec. Copy in ``TUTORIALS`` is owner-reviewable
in one place. The draft copy was reconciled against the *implemented*
pages (not the spec's draft wording) where they diverged — see the PR
discovery note (e.g. P-07 caps at 20 suppliers, not 30; P-02 has no
upload path).
"""

# M-TUTORIAL-A1
from __future__ import annotations

import html

import streamlit as st

from ui.theme.tokens import CARD, COLORS, FONTS, RADIUS, TYPE_SCALE

# ---------------------------------------------------------------------------
# Copy registry — single source of truth for all tutorial text (spec §7).
# Owner-editable. Each step: {title, body, optional control_hint}.
# ---------------------------------------------------------------------------

TRIGGER_LABEL: str = "👋 Show me around"
DIALOG_TITLE: str = "Quick tour"

TUTORIALS: dict[str, dict] = {
    "P-02": {
        "title": "Scope Setup",
        "steps": [
            {
                "title": "What this page is for",
                "body": (
                    "Set the supply-chain context for everything you'll do "
                    "this session. Nothing is computed yet."
                ),
            },
            {
                "title": "Pick your path",
                "body": (
                    "MNC users pick a demo supply chain from the GSCO "
                    "catalogue. Policy Maker users pick a country and then a "
                    "region. Either user can choose **No scope** to screen "
                    "ad-hoc locations later."
                ),
                "control_hint": "Mode: Supply chain · Region · No scope",
            },
            {
                "title": "Preview on the map",
                "body": (
                    "Once you pick a supply chain or region, a map preview "
                    "shows the nodes (or the region outline) so you can "
                    "sanity-check the scope before committing to it."
                ),
            },
            {
                "title": "Confirm and continue",
                "body": (
                    "Review the preview, then **Confirm** to lock the scope "
                    "and move on to the Workflow Hub. You can change the "
                    "scope any time from the top nav."
                ),
            },
        ],
    },
    "P-04": {
        "title": "Inspect Setup",
        "steps": [
            {
                "title": "What this page is for",
                "body": (
                    "Configure a single-location analysis: one centre point, "
                    "a radius, the indicators to run, and (for trends) a time "
                    "range."
                ),
            },
            {
                "title": "Choose a centre",
                "body": (
                    "In v1 you set the centre with **Free Coordinates** — "
                    "search a place name or type a latitude/longitude. The "
                    "Region and Supplier modes arrive once scope setup lands."
                ),
                "control_hint": "Selection mode: Region · Supplier · Free coordinates",
            },
            {
                "title": "Set the radius",
                "body": (
                    "Pick a buffer radius — fixed stops of 1 / 5 / 10 / 25 / "
                    "50 / 100 km, default 5 km. Some indicators (notably the "
                    "coarse CAMS PM grids) need at least 25 km to return a "
                    "value."
                ),
                "control_hint": "Radius (km): 1 · 5 · 10 · 25 · 50 · 100",
            },
            {
                "title": "Pick indicators",
                "body": (
                    "All indicators are pre-selected by default; deselect any "
                    "you don't need, grouped per pillar. Screening uses the "
                    "latest valid window automatically; the time range applies "
                    "to Trend (arriving with P-06)."
                ),
            },
            {
                "title": "Run",
                "body": (
                    "Hit **Run Screening** to compute and move to the results "
                    "view. Run Trend is disabled until the Trend page lands."
                ),
            },
        ],
    },
    "P-07": {
        "title": "Prioritisation Setup",
        "steps": [
            {
                "title": "What this page is for",
                "body": (
                    "Rank many or all of your nodes against each other on the "
                    "same basis, so you can decide where to look first."
                ),
            },
            {
                "title": "Choose mode",
                "body": (
                    "Pick nodes from your loaded **supply chain**, or paste an "
                    "**ad-hoc list** of `name, lat, lon` — one location per "
                    "line. The country supplier database is a v1.x mode."
                ),
                "control_hint": "Mode: Supply chain · Ad hoc list",
            },
            {
                "title": "Select locations (cap 20)",
                "body": (
                    "Choose the locations to compare. The demo caps a batch "
                    "at 20 locations to keep compute manageable; extras are "
                    "flagged before you run."
                ),
            },
            {
                "title": "Fixed radius — and why",
                "body": (
                    "Every location is screened with the same radius so the "
                    "scores are directly comparable — that comparability is "
                    "the whole point of prioritisation."
                ),
            },
            {
                "title": "Indicators & run",
                "body": (
                    "The same indicator set is applied to every location. "
                    "Adjust it if needed, then **Run Prioritisation** to land "
                    "on the ranked results."
                ),
            },
        ],
    },
}

_STEP_STATE_KEY: str = "_tutorial_step"


# ---------------------------------------------------------------------------
# Pure helpers (unit-testable without Streamlit)
# ---------------------------------------------------------------------------

def _next_index(current: int, delta: int, n_steps: int) -> int:
    """Clamp ``current + delta`` to the valid ``[0, n_steps - 1]`` range."""
    return max(0, min(current + delta, n_steps - 1))


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def _ensure_state() -> None:
    """Initialise the namespaced step-index map defensively."""
    if _STEP_STATE_KEY not in st.session_state:
        st.session_state[_STEP_STATE_KEY] = {}


def _step_for(tutorial_id: str, n_steps: int) -> int:
    """Read and clamp the stored step index for ``tutorial_id``."""
    idx = st.session_state[_STEP_STATE_KEY].get(tutorial_id, 0)
    return _next_index(idx, 0, n_steps)


def _advance(tutorial_id: str, delta: int) -> None:
    """on_click callback: move the stored step index by ``delta``.

    Mutating session state in a callback (rather than calling
    ``st.rerun``) keeps the dialog open: the rerun is triggered by a
    widget *inside* the dialog, so Streamlit re-executes the dialog body
    with the updated index instead of closing it.
    """
    steps = TUTORIALS[tutorial_id]["steps"]
    current = st.session_state[_STEP_STATE_KEY].get(tutorial_id, 0)
    st.session_state[_STEP_STATE_KEY][tutorial_id] = _next_index(
        current, delta, len(steps)
    )


# ---------------------------------------------------------------------------
# Step card rendering (themed, token-only — no hardcoded hex)
# ---------------------------------------------------------------------------

def _step_card_html(step: dict) -> str:
    """Build the themed step container (title + body + optional hint).

    Mirrors ``ui.theme.card._card_html`` chrome so the tour matches the
    GSCO card style. Interactive controls are rendered as native widgets
    *below* this block (HTML can't host Streamlit buttons).
    """
    body_font = TYPE_SCALE["body"]
    hint = step.get("control_hint")
    hint_html = ""
    if hint:
        hint_html = f"""
    <div style="
        margin-top: 1rem;
        padding: 0.55rem 0.85rem;
        background: {COLORS['surface_elevated']};
        border: 1px solid {COLORS['card_border']};
        border-radius: {RADIUS['button']}px;
        font-family: {FONTS['sans_body']};
        font-size: {TYPE_SCALE['caption']['size']};
        color: {COLORS['text_secondary']};
    ">🎯&nbsp;&nbsp;{html.escape(hint)}</div>"""

    return f"""
<div style="
    background: {CARD['bg']};
    border: {CARD['border']};
    border-radius: {CARD['radius']};
    padding: {CARD['padding']};
">
    <h3 style="
        font-family: {FONTS['serif_display']};
        font-weight: 400;
        color: {COLORS['text_primary']};
        margin: 0 0 0.5rem 0;
        font-size: 1.4rem;
    ">{html.escape(step['title'])}</h3>
    <p style="
        font-family: {body_font['family']};
        font-size: {body_font['size']};
        font-weight: {body_font['weight']};
        color: {COLORS['text_secondary']};
        margin: 0;
        line-height: 1.5;
    ">{html.escape(step['body'])}</p>{hint_html}
</div>
"""


# ---------------------------------------------------------------------------
# Dialog (the stepper)
# ---------------------------------------------------------------------------

@st.dialog(DIALOG_TITLE)
def _render_tour(tutorial_id: str) -> None:
    """Render the one-step-at-a-time stepper inside an st.dialog modal.

    Back / Next use ``on_click`` callbacks (which keep the dialog open).
    Done and Skip call ``st.rerun()`` — the repo's idiom for closing an
    open dialog (see ``p10_list._delete_dialog``).
    """
    spec = TUTORIALS[tutorial_id]
    steps = spec["steps"]
    n = len(steps)
    idx = _step_for(tutorial_id, n)
    step = steps[idx]

    st.markdown(_step_card_html(step), unsafe_allow_html=True)
    st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)

    st.caption(f"Step {idx + 1} of {n}")
    st.progress((idx + 1) / n)

    is_last = idx == n - 1
    col_back, col_next = st.columns(2)
    with col_back:
        st.button(
            "Back",
            key=f"_tutorial_back_{tutorial_id}",
            disabled=idx == 0,
            use_container_width=True,
            on_click=_advance,
            args=(tutorial_id, -1),
        )
    with col_next:
        if is_last:
            if st.button(
                "Done",
                key=f"_tutorial_done_{tutorial_id}",
                type="primary",
                use_container_width=True,
            ):
                st.rerun()  # closes the dialog
        else:
            st.button(
                "Next",
                key=f"_tutorial_next_{tutorial_id}",
                type="primary",
                use_container_width=True,
                on_click=_advance,
                args=(tutorial_id, 1),
            )

    if st.button(
        "Skip tour",
        key=f"_tutorial_skip_{tutorial_id}",
        type="secondary",
        use_container_width=True,
    ):
        st.rerun()  # closes the dialog


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_tutorial_trigger(tutorial_id: str) -> None:
    """Render the "Show me around" button and open the tour on click.

    Call once per setup page, just below the persistent nav and before
    the page's first form control. ``tutorial_id`` must be one of the
    keys in ``TUTORIALS`` ({"P-02", "P-04", "P-07"}).

    The button is a right-aligned secondary action so it doesn't compete
    with the page's primary CTA. Clicking it resets the step index to 0
    (each open starts the tour from the beginning) and opens the dialog.
    """
    if tutorial_id not in TUTORIALS:
        raise ValueError(
            f"tutorial_id must be one of {sorted(TUTORIALS)}; got {tutorial_id!r}"
        )

    _ensure_state()

    # Right-align the trigger so it reads as a secondary affordance.
    _, col = st.columns([5, 2])
    with col:
        clicked = st.button(
            TRIGGER_LABEL,
            key=f"_tutorial_trigger_{tutorial_id}",
            type="secondary",
            use_container_width=True,
        )

    # Open outside the column context so the modal renders at page top level.
    if clicked:
        st.session_state[_STEP_STATE_KEY][tutorial_id] = 0
        _render_tour(tutorial_id)
