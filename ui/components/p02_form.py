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

from demo.regions import Region, all_countries, regions_for_country
from demo.scopes import SupplyChain, all_scopes
from ui.components.p02_preview import (
    render_none_preview,
    render_region_preview,
    render_supply_chain_preview,
)


Mode = Literal["supply_chain", "region", "none"]


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
    """Render the mode-selection screen, branched by user_type."""
    st.markdown("### Pick a scope mode")
    modes_for_user = _available_modes(user_type)
    cols = st.columns(len(modes_for_user))
    for col, mode in zip(cols, modes_for_user):
        with col:
            _render_mode_card(mode)


def _available_modes(user_type: str | None) -> tuple[Mode, ...]:
    """Modes visible per user_type. Defensive fallback returns all three.

    The hard branch keeps MNC users out of the country/region picker
    (their scopes are curated supply chains) and Policy Maker users
    out of the supply-chain picker (their scopes are administrative
    regions). Both can opt into None.
    """
    if user_type == "mnc":
        return ("supply_chain", "none")
    if user_type == "policy_maker":
        return ("region", "none")
    return ("supply_chain", "region", "none")


def _render_mode_card(mode: Mode) -> None:
    """One mode card. Title + description + mode-specific picker."""
    descriptions: dict[Mode, tuple[str, str]] = {
        "supply_chain": (
            "Demo supply chain",
            "Load one of the curated supply chains. You'll be able to "
            "screen any node in the chain on the next page.",
        ),
        "region": (
            "Country / region",
            "Screen a whole administrative region. You'll get a "
            "representative buffer at the region's centroid.",
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
        elif mode == "region":
            _render_region_picker()
        elif mode == "none":
            if st.button(
                "Continue without a scope",
                use_container_width=True,
                key="p02_pick_none",
            ):
                _set_pending_scope("none", None)
                st.rerun()


def _render_supply_chain_picker() -> None:
    """Dropdown of demo supply chains + Preview button."""
    scopes = all_scopes()
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


def _render_region_picker() -> None:
    """Country dropdown → region dropdown → Preview button.

    First-time pick of a country fires one EE round-trip via
    ``regions_for_country`` (~2s); subsequent picks within the same
    country are instant thanks to the module-level cache.
    """
    countries = all_countries()
    default_country_idx = (
        countries.index("Brazil") if "Brazil" in countries else 0
    )
    country = st.selectbox(
        "Country",
        options=countries,
        index=default_country_idx,
        key="p02_country_choice",
    )

    with st.spinner("Loading regions…"):
        regions = regions_for_country(country)

    if not regions:
        st.warning(
            f"No screenable regions found for {country}. Try another "
            f"country or use **No scope** to screen ad-hoc."
        )
        return

    region_labels = [r.name for r in regions]
    region_choice = st.selectbox(
        "Region",
        options=region_labels,
        key="p02_region_choice",
    )
    if st.button(
        "Preview",
        use_container_width=True,
        key="p02_preview_region",
    ):
        picked = next(r for r in regions if r.name == region_choice)
        _set_pending_scope("region", picked)
        st.rerun()


def _set_pending_scope(
    kind: Mode,
    data: SupplyChain | Region | None,
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
    elif kind == "region":
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
    """Write the confirmed scope and route to the next page."""
    st.session_state["scope"] = {"kind": kind, "data": data}
    st.session_state.pop("p02_stage",          None)
    st.session_state.pop("p02_pending_scope",  None)

    # P-03 Workflow Hub is the canonical next stop; route to P-04 until
    # it lands. ``st.switch_page`` raises ``StreamlitAPIException`` for
    # missing pages; catch broadly to be tolerant of API changes.
    try:
        st.switch_page("pages/03_Workflow_Hub.py")
    except Exception:  # noqa: BLE001
        st.switch_page("pages/04_Inspect_Setup.py")
