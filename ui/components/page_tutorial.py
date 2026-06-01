"""Guided in-page tutorials (M-TUTORIAL-A1 + M-TUTORIAL-RESULTS-A1).

A themed, dismissible, step-by-step tour rendered with native Streamlit
widgets inside an ``st.dialog`` modal. One tutorial per page — the three
setup pages (P-02 / P-04 / P-07) and the two result pages (P-05 / P-06) —
each scoped to that page's flow. The panel steps one card at a time with
Back / Next / Done / Skip controls — the sequential, guided feel of a
coachmark overlay, but built entirely from native widgets styled with the
existing ``ui.theme`` tokens (no JS spotlight, no widget-anchored DOM
highlight — see the spec's §2 rationale and ``UI_Theming_Session_Handoff.md``).

Public API (call once per page):

    render_tutorial_trigger(tutorial_id, start_step=0)

Step schema (scannable layout — M-TUTORIAL-IMPROVE): each step is
``{title, body, bullets?, legend?, schematic?, control_hint?}`` where

  - ``body``    — a short lead sentence (the takeaway), not a paragraph.
  - ``bullets`` — a list of short scannable points (rendered as a tight
                  accent-bulleted list).
  - ``legend``  — a list of ``(label, tone)`` pairs rendered as coloured
                  chips. ``tone`` reuses the project's canonical palette via
                  ``traffic_light.band_colour`` (so a "High" chip is the same
                  red the live tiles use — no new hex invented here).
  - ``schematic`` — optional token-built HTML mock (injected raw).
  - ``control_hint`` — optional single static chip (legacy; prefer bullets).

Manual-only for the demo: the tour opens solely on the trigger button
click. No first-visit auto-open and no seen-tracking. The only session
state is the current step index while a dialog is open, namespaced under
``_tutorial_step``.

Authority: M-TUTORIAL-A1 / M-TUTORIAL-RESULTS-A1 specs. Copy is reconciled
against the *implemented* surfaces (severity words High/Concern/Normal/
Sparse; the four tile grammars; the trend verdict/significance vocabulary).
"""

# M-TUTORIAL-A1
from __future__ import annotations

import html

import streamlit as st

from ui.components.traffic_light import band_colour
from ui.theme.tokens import CARD, COLORS, FONTS, RADIUS, TYPE_SCALE

TRIGGER_LABEL: str = "👋 Show me around"
DIALOG_TITLE: str = "Quick tour"


# ---------------------------------------------------------------------------
# Chip / bullet palette. Severity-coloured tones reuse the canonical
# traffic-light palette (band_colour) so tutorial chips match the live UI;
# accent/neutral tones come straight from the theme tokens.
# ---------------------------------------------------------------------------
def _tone_colour(tone: str) -> str:
    return {
        "red":     band_colour("high"),      # High
        "amber":   band_colour("moderate"),  # Concern / Moderate
        "green":   band_colour("low"),       # Normal / Low
        "grey":    band_colour(None),        # Sparse
        "accent":  COLORS["accent_green"],
        "neutral": COLORS["text_muted"],
    }.get(tone, COLORS["text_secondary"])


# A token-only mini-tile schematic (technique (a)) illustrating what a C4b
# indicator tile looks like — a quick visual anchor for the "what a tile
# shows" step.
_C4B_TILE_SCHEMATIC: str = f"""
<div style="margin-top:1rem;border:{CARD['border']};border-radius:{CARD['radius']};
    padding:0.75rem 1rem;background:{COLORS['surface_elevated']};max-width:240px;">
  <div style="display:flex;justify-content:space-between;align-items:center;
      font-family:{FONTS['sans_body']};font-size:{TYPE_SCALE['caption']['size']};">
    <span style="font-weight:600;color:{COLORS['text_primary']};">NO₂</span>
    <span style="font-weight:700;color:{_tone_colour('red')};">● High</span>
  </div>
  <div style="text-align:center;font-family:{FONTS['sans_body']};font-weight:700;
      font-size:2em;color:{COLORS['text_primary']};padding:4px 0 0 0;">+2.3σ</div>
  <div style="text-align:center;font-family:{FONTS['sans_body']};
      font-size:{TYPE_SCALE['caption']['size']};color:{COLORS['text_secondary']};">
      ▲ above regional baseline</div>
  <div style="text-align:center;font-family:{FONTS['sans_body']};
      font-size:{TYPE_SCALE['caption']['size']};color:{COLORS['accent_green']};
      margin-top:6px;">↑ the big number is the severity (here, a z-score)</div>
</div>"""


# ---------------------------------------------------------------------------
# Copy registry — single source of truth for all tutorial text.
# Owner-editable. Scannable shape: short lead `body` + `bullets` + `legend`.
# ---------------------------------------------------------------------------

TUTORIALS: dict[str, dict] = {
    "P-02": {
        "title": "Scope Setup",
        "steps": [
            {
                "title": "What this page is for",
                "body": "Set the supply-chain context for this session — nothing is computed yet.",
            },
            {
                "title": "Pick your path",
                "body": "How you load a scope depends on your user type.",
                "bullets": [
                    "MNC: pick a demo supply chain from the GSCO catalogue",
                    "Policy Maker: pick a country, then a region",
                    "Either: choose 'No scope' to screen ad-hoc locations later",
                ],
            },
            {
                "title": "Preview on the map",
                "body": "Pick a scope and a map preview appears.",
                "bullets": [
                    "Supply-chain nodes (or the region outline) render on the map",
                    "Use it to sanity-check the scope before committing",
                ],
            },
            {
                "title": "Confirm and continue",
                "body": "Lock it in to reach the Workflow Hub.",
                "bullets": [
                    "'Confirm' saves the scope",
                    "Change it any time from the top nav",
                ],
            },
        ],
    },
    "P-04": {
        "title": "Inspect Setup",
        "steps": [
            {
                "title": "What this page is for",
                "body": "Configure a single-location analysis.",
                "bullets": [
                    "One centre point and a radius",
                    "The indicators to run",
                    "A time range (used for trends)",
                ],
            },
            {
                "title": "Choose a centre",
                "body": "Set the point to screen around.",
                "bullets": [
                    "With 'No Scope': search a place name or type a latitude/longitude",
                    "Region and Supplier modes arrive with scope setup",
                ],
            },
            {
                "title": "Set the radius",
                "body": "Pick a buffer radius around the centre.",
                "bullets": [
                    "Fixed stops: 1 / 5 / 10 / 25 / 50 / 100 km (default 5)",
                    "Coarse CAMS PM grids need ≥ 25 km to return a value",
                ],
            },
            {
                "title": "Pick indicators",
                "body": "All indicators are pre-selected; deselect what you don't need.",
                "bullets": [
                    "Grouped per pillar",
                    "Screening uses the latest valid window; the time range can be changed",
                ],
            },
            {
                "title": "Run",
                "body": "Run Screening to compute and move to the results view.",
            },
        ],
    },
    "P-07": {
        "title": "Prioritisation Setup",
        "steps": [
            {
                "title": "What this page is for",
                "body": "Rank many or all of your nodes on the same basis, so you can decide where to look first.",
            },
            {
                "title": "Choose mode",
                "body": "Pick where the nodes come from.",
                "bullets": [
                    "Supply chain: nodes from your loaded scope",
                    "Ad-hoc list: paste 'name, lat, lon', one per line",
                ],
            },
            {
                "title": "Select locations (cap 20)",
                "body": "Choose the locations to compare.",
                "bullets": [
                    "The demo caps a batch at 20 locations",
                    "Extras are flagged before you run",
                ],
            },
            {
                "title": "Fixed radius — and why",
                "body": "Every location uses the same radius.",
                "bullets": [
                    "That comparability is the whole point of prioritisation",
                ],
            },
            {
                "title": "Indicators & run",
                "body": "The same indicator set applies to every location.",
                "bullets": [
                    "Adjust it if needed",
                    "'Run Prioritisation' lands on the ranked results",
                ],
            },
        ],
    },
    # ----------------------------------------------------------------------
    # M-TUTORIAL-RESULTS-A1 — interpretation tutorials for the result pages.
    # Severity words are High / Concern / Normal / Sparse; the four tile
    # grammars are z-score, sustained-contrast score, DW categorical, and
    # KBA distance/overlap. See severity.py, c4b_kpi_grid.py, trend_record.py.
    # ----------------------------------------------------------------------
    "P-05-RESULTS": {
        "title": "How to read your results",
        "trigger_label": "❓ How to read this",
        "steps": [
            {
                "title": "What this page tells you",
                "body": "A snapshot of conditions at your location, across three pillars.",
                "bullets": [
                    "Air · Greenhouse Gas · Nature",
                    "Each signal is compared against the surrounding area",
                    "A high number means 'unusual for this place', not just 'present'",
                ],
            },
            {
                "title": "The traffic-light summary",
                "body": "The top chips rank where to look first — not a verdict of harm.",
                "bullets": [
                    "The band comes from each pillar's Follow-Up Priority Score",
                    "Confidence dots: ● high (≥ 0.66) · ◐ moderate (≥ 0.33) · ○ low/none",
                    "Priority already folds in measurement quality, so weak signals score lower",
                ],
                "legend": [("High", "red"), ("Moderate", "amber"), ("Low", "green")],
            },
            {
                "title": "The indicator grid — what a tile shows",
                "body": "Each tile is one indicator; the big number is its severity.",
                "bullets": [
                    "Centre = how far from the local background (air: a z-score, in σ)",
                    "Corner word buckets it: |z| ≥ 2 is High, ≥ 1 is Concern",
                    "Sparse = too little usable data to score",
                ],
                "legend": [("High", "red"), ("Concern", "amber"),
                           ("Normal", "green"), ("Sparse", "grey")],
                "schematic": _C4B_TILE_SCHEMATIC,
            },
            {
                "title": "The grid — four ways of reading",
                "body": "Different indicators are read in different grammars.",
                "bullets": [
                    "Air pollutants — z-score vs the local background",
                    "Nightlights — sustained-contrast score (High ≥ 0.66, Concern ≥ 0.33)",
                    "Land cover — Dynamic World dominant class",
                    "Biodiversity — distance/overlap to the nearest Key Biodiversity Area",
                    "'Sparse' means unknown, not 'fine'",
                ],
            },
            {
                "title": "Critical-only vs Show all",
                "body": "By default the grid shows only the tiles that need attention.",
                "bullets": [
                    "High/Concern tiles only, topped up to at least three",
                    "'Show all indicators' reveals the rest",
                    "'View on map →' = spatial view · 'View trend →' = over time",
                ],
            },
            {
                "title": "The drill-down panels",
                "body": "Open a pillar panel to see how its score was built.",
                "bullets": [
                    "Follow-Up Priority = weighted sub-aggregates, each with confidence",
                    "Confidence dots: ● high (≥ 0.66) · ◐ moderate (≥ 0.33) · ○ low/none",
                    "'Coastal handling' note appears when the ring overlapped water",
                    "Hansen / ODIAC / CH₄ are reference datasets — not part of the score",
                ],
            },
            {
                "title": "Confidence, the summary & trend",
                "body": "The last surfaces tell you how much to trust the read.",
                "bullets": [
                    "The Confidence panel shows each pillar's limiting factor ('Limited by: …')",
                    "The written summary hides under partial coverage — the pillar table is the honest fallback",
                ],
            },
        ],
    },
    "P-06-TREND": {
        "title": "How to read this chart",
        "trigger_label": "❓ How to read this chart",
        "steps": [
            {
                "title": "What this chart is",
                "body": "One indicator's daily values over the analysis window.",
                "bullets": [
                    "Dots = daily readings ('Daily site value')",
                    "Red line = fitted 'Theil–Sen trend' (robust to outliers)",
                ],
            },
            {
                "title": "The verdict badge",
                "body": "The badge summarises the direction and strength.",
                "bullets": [
                    "↑ Rising · ↓ Falling · No significant trend · Trend unavailable",
                    "A pure function of the full window — zoom/pan never changes it",
                    "A short window may add '· possibly seasonal'",
                ],
            },
            {
                "title": "Is the trend real? (significance)",
                "body": "The significance line buckets the Mann–Kendall p-value.",
                "bullets": [
                    "p < 0.05 — significant",
                    "p < 0.10 — weak / emerging",
                    "otherwise — no significant trend",
                    "Weak/emerging = a hint of a direction, not enough to be sure",
                ],
            },
            {
                "title": "Seasonality and gaps",
                "body": "A few cautions when reading the line.",
                "bullets": [
                    "Window under a year → 'possibly seasonal'; treat the direction as provisional",
                    "Gaps in the dots mean missing data, not zero",
                    "A short or sparse window is itself a caution",
                    "Full definition lives in the Indicator Library →",
                ],
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

def _bullets_html(bullets: list[str]) -> str:
    """Tight accent-bulleted list — scannable, one short point per line."""
    body_font = TYPE_SCALE["body"]
    rows = "".join(
        f"""
    <div style="display:flex;gap:0.55rem;margin:0.32rem 0;align-items:flex-start;">
      <span style="color:{COLORS['accent_green']};flex:0 0 auto;line-height:1.45;">•</span>
      <span style="font-family:{body_font['family']};font-size:0.98rem;
          color:{COLORS['text_secondary']};line-height:1.45;">{html.escape(b)}</span>
    </div>"""
        for b in bullets
    )
    return f"<div style='margin-top:0.85rem;'>{rows}</div>"


def _legend_html(legend: list) -> str:
    """Coloured chip row — maps a vocab (e.g. severity words) to its colour."""
    chips = "".join(
        f"""
    <span style="display:inline-flex;align-items:center;gap:6px;
        padding:2px 10px;border-radius:999px;
        background:{COLORS['surface_elevated']};border:1px solid {COLORS['card_border']};
        font-family:{FONTS['sans_body']};font-size:{TYPE_SCALE['caption']['size']};
        color:{COLORS['text_secondary']};">
      <span style="width:9px;height:9px;border-radius:50%;flex:0 0 auto;
          background:{_tone_colour(tone)};"></span>{html.escape(label)}</span>"""
        for label, tone in legend
    )
    return (
        f"<div style='display:flex;flex-wrap:wrap;gap:0.4rem;margin-top:0.85rem;'>"
        f"{chips}</div>"
    )


def _step_card_html(step: dict) -> str:
    """Build the themed step container (title + lead + bullets/legend/schematic).

    Mirrors ``ui.theme.card._card_html`` chrome so the tour matches the
    GSCO card style. Interactive controls are rendered as native widgets
    *below* this block (HTML can't host Streamlit buttons).
    """
    body_font = TYPE_SCALE["body"]

    bullets_html = _bullets_html(step["bullets"]) if step.get("bullets") else ""
    legend_html = _legend_html(step["legend"]) if step.get("legend") else ""
    schematic = step.get("schematic", "")

    hint = step.get("control_hint")
    hint_html = ""
    if hint:
        hint_html = f"""
    <div style="
        margin-top: 0.85rem;
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
        color: {COLORS['text_primary']};
        margin: 0;
        line-height: 1.5;
    ">{html.escape(step['body'])}</p>{bullets_html}{legend_html}{schematic}{hint_html}
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

def render_tutorial_trigger(tutorial_id: str, start_step: int = 0) -> None:
    """Render the tutorial-trigger button and open the tour on click.

    Call once per page, just below the persistent nav (setup pages) or near
    the top of the results area (P-05 / P-06). ``tutorial_id`` must be one of
    the keys in ``TUTORIALS`` (setup: "P-02"/"P-04"/"P-07"; results:
    "P-05-RESULTS"/"P-06-TREND").

    The button label comes from the tutorial's ``trigger_label`` (falling back
    to ``TRIGGER_LABEL``) so copy stays centralised. The button is a
    right-aligned secondary action so it doesn't compete with the page's
    primary CTA.

    ``start_step`` (default 0) is the step the tour opens at — supports a
    future per-section "→" affordance that jumps straight to the relevant
    step. Each open resets the step index to ``start_step`` (clamped to the
    tutorial's range), so the tour is reopenable from a known point.
    """
    if tutorial_id not in TUTORIALS:
        raise ValueError(
            f"tutorial_id must be one of {sorted(TUTORIALS)}; got {tutorial_id!r}"
        )

    _ensure_state()

    spec = TUTORIALS[tutorial_id]
    label = spec.get("trigger_label", TRIGGER_LABEL)

    # Right-align the trigger so it reads as a secondary affordance.
    _, col = st.columns([5, 2])
    with col:
        clicked = st.button(
            label,
            key=f"_tutorial_trigger_{tutorial_id}",
            type="secondary",
            use_container_width=True,
        )

    # Open outside the column context so the modal renders at page top level.
    if clicked:
        n = len(spec["steps"])
        st.session_state[_STEP_STATE_KEY][tutorial_id] = _next_index(
            start_step, 0, n
        )
        _render_tour(tutorial_id)
