"""P-03 Workflow Hub renderers (M-P0103).

Three stacked sections:

  1. Welcome line + scope-summary metrics (one card per scope kind).
  2. Two workflow cards: **Inspect** (active → P-04) and
     **Prioritisation** (placeholder until P-07/P-08 land).
  3. Three persistent-module cards: Indicator Library, Saved Analyses,
     Reports — all v1.x placeholders.

Authority: docs/Wireframes_All_v4.md §P-03.
"""

# M-P0103
from __future__ import annotations

import streamlit as st


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_workflow_hub() -> None:
    """Render the three P-03 sections, separated by dividers."""
    _render_welcome_and_scope_summary()
    st.divider()
    _render_workflow_cards()
    st.divider()
    _render_module_cards()


# ---------------------------------------------------------------------------
# Section 1 — Welcome + scope summary
# ---------------------------------------------------------------------------

def _render_welcome_and_scope_summary() -> None:
    user_label = st.session_state.get("user_type_label", "user")
    st.markdown(f"### Welcome, {user_label}.")
    _render_scope_summary(st.session_state.get("scope"))


def _render_scope_summary(scope: dict | None) -> None:
    """One-line scope description + a 3-metric block per scope kind."""
    if scope is None or scope.get("kind") == "none":
        st.info(
            "**No scope loaded.** You'll be able to screen any location "
            "ad-hoc on the Inspect page. To load a curated supply chain "
            "or a region, go to **Scope Setup**."
        )
        return
    if scope["kind"] == "supply_chain":
        chain = scope["data"]
        tiers = sorted({n.tier for n in chain.nodes})
        col1, col2, col3 = st.columns(3)
        col1.metric("Supply chain", chain.name)
        col2.metric("Nodes",        len(chain.nodes))
        col3.metric("Country",      chain.country)
        st.caption(
            f"Industry: *{chain.industry}* · Tiers: {', '.join(tiers)}"
        )
    elif scope["kind"] == "region":
        r = scope["data"]
        col1, col2, col3 = st.columns(3)
        col1.metric("Region",   f"{r.name}, {r.country}")
        col2.metric("Centroid", f"{r.centroid_lat:.2f}, {r.centroid_lon:.2f}")
        col3.metric(
            "Buffer", f"{r.radius_km} km",
            delta=("capped" if r.is_capped else None),
            delta_color="off",
        )


# ---------------------------------------------------------------------------
# Section 2 — Workflow cards
# ---------------------------------------------------------------------------

def _render_workflow_cards() -> None:
    st.markdown("### Workflows")
    col_inspect, col_priority = st.columns(2)
    with col_inspect:
        _render_inspect_card()
    with col_priority:
        _render_prioritisation_card()


def _render_inspect_card() -> None:
    with st.container(border=True):
        st.markdown("#### Inspect")
        st.caption(
            "Screen a single location across the three environmental "
            "pillars. Pick a centre, a buffer radius, and the "
            "indicators to run."
        )
        st.write("")
        if st.button(
            "Open Inspect →",
            use_container_width=True,
            type="primary",
            key="p03_open_inspect",
        ):
            st.switch_page("pages/04_Inspect_Setup.py")


def _render_prioritisation_card() -> None:
    with st.container(border=True):
        st.markdown("#### Prioritisation")
        st.caption(
            "Rank multiple suppliers by audit priority. Useful for "
            "Policy Maker reviews of a region or MNC reviews of a "
            "whole supply chain. Lands in a later milestone."
        )
        st.write("")
        st.button(
            "Open Prioritisation →",
            use_container_width=True,
            disabled=True,
            key="p03_open_prioritisation",
            help="Prioritisation (P-07/P-08) lands in a later milestone.",
        )


# ---------------------------------------------------------------------------
# Section 3 — Persistent module cards (all placeholders for v1)
# ---------------------------------------------------------------------------

def _render_module_cards() -> None:
    st.markdown("### Persistent modules")
    st.caption(
        "Reference and history surfaces, accessible from any page once "
        "they land."
    )
    col_library, col_saved, col_reports = st.columns(3)
    with col_library:
        _render_module_card(
            "Indicator Library",
            "Reference catalogue of every indicator the tool can "
            "compute — formulas, sources, decision relevance.",
        )
    with col_saved:
        _render_module_card(
            "Saved Analyses",
            "List of screenings you've saved. From here you can re-open "
            "any one back on its results page.",
        )
    with col_reports:
        _render_module_card(
            "Reports",
            "Generate PDF / CSV / JSON exports from your saved analyses.",
        )


def _render_module_card(title: str, description: str) -> None:
    """One disabled card for an upcoming persistent module."""
    with st.container(border=True):
        st.markdown(f"#### {title}")
        st.caption(description)
        st.write("")
        st.button(
            "Open →",
            disabled=True,
            use_container_width=True,
            key=f"p03_open_{title.lower().replace(' ', '_')}",
            help="Lands in a future milestone.",
        )
