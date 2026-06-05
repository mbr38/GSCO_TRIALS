"""P-02 scope-setup form (M-P02).

Two-step state machine for the Scope Setup page:

    S1_ModePick  — user picks Supply Chain / Region / None.
    S2_Preview   — preview the picked scope; Confirm or Back.

The state lives in ``st.session_state`` under ``p02_stage`` /
``p02_pending_scope``; ``Confirm`` commits the pick to
``st.session_state["scope"]`` and ``st.switch_page``s onwards.

User-type hard branch — MNC sees Supply Chain + None; Policy Maker
sees Region + None. No cross-type access by design.

Authority: docs/Wireframes_All_v4.md §P-02; M-P02 design decisions.
"""

# M-P02
from __future__ import annotations

from typing import Literal

import streamlit as st

from demo.regions import Region, all_countries
from demo.scopes import SupplyChain, country_scopes, mnc_scopes
from ui.components.p02_preview import (
    render_country_regional_preview,
    render_none_preview,
    render_region_preview,
    render_supply_chain_preview,
)


# "country" is the Policy-Maker top-level card (its sub-choice resolves to
# either a "country_regional" or a "supply_chain" pending scope). "region"
# is retained only for the legacy preview branch / backward-compat.
Mode = Literal["supply_chain", "country", "country_regional", "region", "none"]


# ---------------------------------------------------------------------------
# Top-level state machine
# ---------------------------------------------------------------------------

def render_scope_setup() -> None:
    """Dispatch by current stage; fall back to ModePick defensively."""
    user_type = st.session_state.get("user_type")
    stage = st.session_state.get("p02_stage", "mode_pick")

    if stage == "mode_pick":
        _render_mode_pick(user_type)
    elif stage == "preview":
        _render_preview(user_type)
    else:
        st.session_state["p02_stage"] = "mode_pick"
        st.rerun()


# ---------------------------------------------------------------------------
# S1 — Mode pick
# ---------------------------------------------------------------------------

def _render_mode_pick(user_type: str | None) -> None:
    """Render the mode-selection screen, branched by user_type.

    MNC users (and the defensive fallback) get the curated-supply-chain
    cards. Policy Maker users get the Country card — country first, then
    a Regional-analysis / Supply-chain-analysis sub-choice — alongside
    No scope.
    """
    st.markdown("### Pick a scope mode")

    # M-PARTIAL-CAVEAT — uniform card heights for adjacent mode cards.
    st.markdown(
        """
        <style>
        [data-testid="stHorizontalBlock"] [data-testid="stVerticalBlockBorderWrapper"] {
            min-height: 280px;
            display: flex;
            flex-direction: column;
        }
        [data-testid="stHorizontalBlock"] [data-testid="stVerticalBlockBorderWrapper"] > div {
            flex-grow: 1;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if user_type == "policy_maker":
        _render_policy_maker_mode_pick()
    else:
        _render_mnc_mode_pick()


def _available_modes(user_type: str | None) -> tuple[Mode, ...]:
    """Top-level cards visible per user_type.

    MNC (and the defensive fallback) pick a curated supply chain or no
    scope. Policy Maker picks a Country (whose sub-choice resolves to a
    regional or a supply-chain scope) or no scope. The hard branch keeps
    each user type in its own scope grammar.
    """
    if user_type == "policy_maker":
        return ("country", "none")
    return ("supply_chain", "none")


# ---------------------------------------------------------------------------
# MNC mode pick — curated supply chains
# ---------------------------------------------------------------------------

def _render_mnc_mode_pick() -> None:
    """Two cards: a curated supply chain, or no scope."""
    cols = st.columns(2)
    with cols[0]:
        _render_mode_card("supply_chain")
    with cols[1]:
        _render_mode_card("none")


def _render_mode_card(mode: Mode) -> None:
    """One MNC mode card. Title + description + mode-specific picker."""
    descriptions: dict[Mode, tuple[str, str]] = {
        "supply_chain": (
            "Demo supply chain",
            "Load one of the curated supply chains. You'll be able to "
            "screen any node in the chain on the next page.",
        ),
        "none": (
            "No scope",
            "Skip scope setup and configure each screening from scratch "
            "using free coordinates.",
        ),
    }
    title, description = descriptions[mode]

    with st.container(border=True):
        st.markdown(f"#### {title}")
        st.caption(description)
        st.write("")

        if mode == "supply_chain":
            _render_supply_chain_picker()
        elif mode == "none":
            if st.button(
                "Continue without a scope",
                use_container_width=True,
                key="p02_pick_none",
            ):
                _set_pending_scope("none", None)
                st.rerun()


def _render_supply_chain_picker() -> None:
    """Dropdown of MNC (corporate) supply chains + Preview button.

    Uses ``mnc_scopes()`` so country supply chains (e.g. India EV,
    ``audience == "policy_maker"``) never surface in the MNC picker.
    """
    scopes = mnc_scopes()
    labels = [s.name for s in scopes]
    choice = st.selectbox(
        "Supply chain",
        options=labels,
        key="p02_supply_chain_choice",
        label_visibility="collapsed",
    )
    if st.button(
        "Preview",
        use_container_width=True,
        key="p02_preview_supply_chain",
    ):
        picked = next(s for s in scopes if s.name == choice)
        _set_pending_scope("supply_chain", picked)
        st.rerun()


# ---------------------------------------------------------------------------
# Policy-Maker mode pick — Country (regional / supply-chain) or none
# ---------------------------------------------------------------------------

def _render_policy_maker_mode_pick() -> None:
    """Two cards: Country analysis, or no scope."""
    cols = st.columns(2)
    with cols[0]:
        _render_country_card()
    with cols[1]:
        _render_mode_card("none")


def _render_country_card() -> None:
    """Country card: pick a country, then a regional / supply-chain analysis.

    - **Regional analysis** — no region picked here; the pending scope is
      ``country_regional`` (region chosen later on Inspect/Prioritisation).
    - **Supply-chain analysis** — pick from the supply chains available for
      the chosen country (``country_scopes``).
    """
    with st.container(border=True):
        st.markdown("#### Country")
        st.caption(
            "Screen a country. Choose a region-by-region analysis, or a "
            "supply chain operating in that country."
        )
        st.write("")

        countries = all_countries()
        default_idx = countries.index("India") if "India" in countries else 0
        country = st.selectbox(
            "Country",
            options=countries,
            index=default_idx,
            key="p02_pm_country",
        )

        analysis = st.radio(
            "Analysis type",
            options=["Regional analysis", "Supply-chain analysis"],
            key="p02_pm_analysis",
        )

        if analysis == "Regional analysis":
            st.caption(
                "Screen administrative regions. You'll pick the region(s) "
                "on the Inspect / Prioritisation page."
            )
            if st.button(
                "Preview",
                use_container_width=True,
                key="p02_preview_country_regional",
            ):
                _set_pending_scope("country_regional", {"country": country})
                st.rerun()
        else:
            _render_country_supply_chain_picker(country)


def _render_country_supply_chain_picker(country: str) -> None:
    """Supply chains available for ``country`` + Preview button."""
    scopes = country_scopes(country)
    if not scopes:
        st.info(
            f"No supply chains available for {country} yet. Use "
            f"**Regional analysis**, or pick another country."
        )
        return

    labels = [s.name for s in scopes]
    choice = st.selectbox(
        "Supply chain",
        options=labels,
        key="p02_pm_supply_chain_choice",
    )
    if st.button(
        "Preview",
        use_container_width=True,
        key="p02_preview_pm_supply_chain",
    ):
        picked = next(s for s in scopes if s.name == choice)
        _set_pending_scope("supply_chain", picked)
        st.rerun()


def _set_pending_scope(
    kind: Mode,
    data: SupplyChain | Region | dict | None,
) -> None:
    """Stash the pick in session_state and transition to Preview."""
    st.session_state["p02_pending_scope"] = {"kind": kind, "data": data}
    st.session_state["p02_stage"] = "preview"


# ---------------------------------------------------------------------------
# S2 — Preview
# ---------------------------------------------------------------------------

def _render_preview(user_type: str | None) -> None:
    """Render the pending-scope preview + nav buttons."""
    pending = st.session_state.get("p02_pending_scope")
    if not pending:
        # Defensive — somehow in preview without a pending scope.
        st.session_state["p02_stage"] = "mode_pick"
        st.rerun()
        return

    kind = pending["kind"]
    data = pending["data"]

    st.markdown("### Preview")
    if kind == "supply_chain":
        render_supply_chain_preview(data)
    elif kind == "country_regional":
        render_country_regional_preview(data["country"])
    elif kind == "region":
        # Legacy region scope — kept for backward-compat.
        render_region_preview(data)
    elif kind == "none":
        render_none_preview()

    st.divider()
    col_back, col_confirm = st.columns(2)
    with col_back:
        if st.button("← Back to mode pick", use_container_width=True):
            st.session_state.pop("p02_pending_scope", None)
            st.session_state["p02_stage"] = "mode_pick"
            st.rerun()
    with col_confirm:
        if st.button(
            "Confirm and continue",
            type="primary",
            use_container_width=True,
        ):
            _commit_scope_and_navigate(kind, data)


def _commit_scope_and_navigate(
    kind: Mode,
    data: SupplyChain | Region | None,
) -> None:
    """Write the confirmed scope and route to the Workflow Hub.

    M-P0103: P-03 now exists; routing is unconditional. The earlier
    try/except fallback to P-04 is no longer needed.
    """
    st.session_state["scope"] = {"kind": kind, "data": data}
    st.session_state.pop("p02_stage",         None)
    st.session_state.pop("p02_pending_scope", None)
    st.switch_page("pages/03_Workflow_Hub.py")
