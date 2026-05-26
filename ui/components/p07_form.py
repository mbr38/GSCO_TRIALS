"""P-07 setup form (M-P07).

Three-mode interface: supply chain (when scope loaded), ad hoc list,
country database (disabled placeholder). Indicator + radius selection
reuses P-04's components.
"""

# M-P07
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import streamlit as st

from ui.components.p04_indicator_registry import (
    ALL_INDICATOR_IDS,
    INDICATORS_BY_PILLAR,
    display_name,
)


_MAX_SUPPLIERS: int = 20


@dataclass(frozen=True)
class Supplier:
    """One supplier to be screened in the batch."""
    id:     str
    name:   str
    lat:    float
    lon:    float
    source: str  # "supply_chain" or "ad_hoc"


def render_prioritisation_setup() -> None:
    """Top-level orchestrator. Composes mode tabs, indicator picker,
    radius, run button."""
    suppliers  = _render_supplier_section()
    radius_km  = _render_radius_section()
    indicators = _render_indicator_section()
    _render_run_section(suppliers, radius_km, indicators)


# ──────────────────────────────────────────────────────────────────
# Supplier section — three modes
# ──────────────────────────────────────────────────────────────────

def _render_supplier_section() -> list[Supplier]:
    """Three-mode tab interface. Returns the chosen supplier list."""
    scope = st.session_state.get("scope")
    has_supply_chain = bool(scope) and scope.get("kind") == "supply_chain"

    # Three tabs, order by relevance to current scope.
    if has_supply_chain:
        tab_chain, tab_adhoc, tab_db = st.tabs([
            "Supply chain",
            "Ad hoc locations",
            "Country database (v1.x)",
        ])
    else:
        tab_adhoc, tab_chain, tab_db = st.tabs([
            "Ad hoc locations",
            "Supply chain (load a scope first)",
            "Country database (v1.x)",
        ])

    suppliers: list[Supplier] = []
    with tab_chain:
        if has_supply_chain:
            suppliers = _render_supply_chain_picker(scope["data"])
        else:
            _render_no_chain_loaded()

    with tab_adhoc:
        adhoc_suppliers = _render_ad_hoc_textarea()
        if not has_supply_chain:
            # Ad hoc is the active tab when no chain is loaded.
            suppliers = adhoc_suppliers

    with tab_db:
        _render_country_db_placeholder()

    return suppliers


def _render_supply_chain_picker(chain) -> list[Supplier]:
    """Render the supply chain's nodes as checkboxes; return selected."""
    # Generation counter pattern from M-P04 reset for clean state.
    if "p07_chain_generation" not in st.session_state:
        st.session_state["p07_chain_generation"] = 0
    if "p07_selected_chain_ids" not in st.session_state:
        st.session_state["p07_selected_chain_ids"] = {n.id for n in chain.nodes}

    selected_ids = st.session_state["p07_selected_chain_ids"]
    generation   = st.session_state["p07_chain_generation"]

    with st.container(border=True):
        header_cols = st.columns([4, 2])
        with header_cols[0]:
            st.markdown(f"**{chain.name}**")
            st.caption(
                f"{chain.industry} · {len(chain.nodes)} nodes · {chain.country}"
            )
        with header_cols[1]:
            col_reset, col_deselect = st.columns(2)
            with col_reset:
                if st.button("Select all", use_container_width=True):
                    st.session_state["p07_selected_chain_ids"] = {
                        n.id for n in chain.nodes
                    }
                    st.session_state["p07_chain_generation"] += 1
                    st.rerun()
            with col_deselect:
                if st.button("Deselect all", use_container_width=True):
                    st.session_state["p07_selected_chain_ids"] = set()
                    st.session_state["p07_chain_generation"] += 1
                    st.rerun()

        st.divider()

        for node in chain.nodes:
            checked = node.id in selected_ids
            new_checked = st.checkbox(
                f"{node.name} ({node.tier}) — ({node.lat:.4f}, {node.lon:.4f})",
                value=checked,
                key=f"p07_chain_{node.id}_v{generation}",
            )
            if new_checked and node.id not in selected_ids:
                selected_ids.add(node.id)
            elif not new_checked and node.id in selected_ids:
                selected_ids.discard(node.id)

    # Build Supplier list from selected nodes.
    return [
        Supplier(
            id=n.id, name=n.name, lat=n.lat, lon=n.lon, source="supply_chain",
        )
        for n in chain.nodes if n.id in selected_ids
    ]


def _render_no_chain_loaded() -> None:
    """Shown in the Supply Chain tab when no scope is loaded."""
    st.info(
        "No supply chain loaded. Go to **Scope Setup** (P-02) to "
        "load one, or use **Ad hoc locations** to paste your own list."
    )
    if st.button("Go to Scope Setup", key="p07_to_p02"):
        st.switch_page("pages/02_Scope_Setup.py")


def _render_ad_hoc_textarea() -> list[Supplier]:
    """Textarea for pasting 'name, lat, lon' per line."""
    with st.container(border=True):
        st.markdown("**Paste a list of locations**")
        st.caption(
            "Format: `name, lat, lon` per line. Lines starting with `#` "
            "are ignored. Max 20 locations per batch."
        )
        text = st.text_area(
            "Locations",
            placeholder=(
                "# Example:\n"
                "São Paulo HQ, -23.5505, -46.6333\n"
                "Rio Distribution, -22.9068, -43.1729\n"
            ),
            height=180,
            label_visibility="collapsed",
            key="p07_adhoc_text",
        )
        parsed, errors = _parse_ad_hoc(text)
        if errors:
            with st.expander(
                f"⚠️ {len(errors)} line(s) couldn't be parsed"
            ):
                for line_no, line, reason in errors:
                    st.caption(f"Line {line_no}: `{line}` — {reason}")
        if parsed:
            st.success(f"Parsed {len(parsed)} location(s).")
        return parsed


def _parse_ad_hoc(
    text: str,
) -> tuple[list[Supplier], list[tuple[int, str, str]]]:
    """Parse the textarea. Return (suppliers, errors).

    Errors are (line_number, raw_line, reason) tuples for the expander.
    """
    suppliers: list[Supplier] = []
    errors:    list[tuple[int, str, str]] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            errors.append((line_no, raw, "expected 3 comma-separated fields"))
            continue
        name, lat_str, lon_str = parts
        if not name:
            errors.append((line_no, raw, "name is empty"))
            continue
        try:
            lat, lon = float(lat_str), float(lon_str)
        except ValueError:
            errors.append((line_no, raw, "lat/lon must be numbers"))
            continue
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            errors.append((line_no, raw, "lat/lon out of range"))
            continue
        suppliers.append(Supplier(
            id=f"adhoc_{line_no}",
            name=name, lat=lat, lon=lon, source="ad_hoc",
        ))
    return suppliers, errors


def _render_country_db_placeholder() -> None:
    """The disabled v1.x country database tab."""
    st.info(
        "**Country supplier database** — screen every supplier in a "
        "country at once. Lands in a later milestone. For Policy Maker "
        "users this will unlock 'scan every cement factory in Brazil' "
        "and similar at-scale audit workflows. Requires integration "
        "with a supplier database (e.g. Open Supply Hub, CARMA)."
    )
    st.button(
        "Coming in v1.x", disabled=True, use_container_width=True,
        help="v1.x feature.",
    )


# ──────────────────────────────────────────────────────────────────
# Radius + indicators — reuse P-04 patterns
# ──────────────────────────────────────────────────────────────────

# Same radius stops as P-04's MNC mode.
_RADIUS_STOPS_KM = (1, 5, 10, 25, 50, 100)


def _render_radius_section() -> int:
    """Shared radius — same buffer applied to every supplier."""
    with st.container(border=True):
        st.markdown("### Buffer radius")
        st.caption(
            "Same radius applied to every supplier in the batch. Pick "
            "based on the typical scale of your suppliers — smaller "
            "buffers for individual sites, larger for districts or "
            "industrial clusters."
        )
        return st.select_slider(
            "Radius (km)",
            options=_RADIUS_STOPS_KM,
            value=5,
            key="p07_radius",
        )


def _render_indicator_section() -> set[str]:
    """Indicator picker — same pattern as P-04, all selected by default."""
    # M-P07: reuse the same generation-counter pattern as P-04.
    if "p07_selected_indicators" not in st.session_state:
        st.session_state["p07_selected_indicators"] = set(ALL_INDICATOR_IDS)
    if "p07_indicator_generation" not in st.session_state:
        st.session_state["p07_indicator_generation"] = 0

    generation = st.session_state["p07_indicator_generation"]

    with st.container(border=True):
        header_cols = st.columns([3, 2])
        with header_cols[0]:
            st.markdown("### Indicators")
            st.caption("Same indicators applied to every supplier.")
        with header_cols[1]:
            col_a, col_b = st.columns(2)
            # M-P07-POLISH: labels match the supply chain picker above.
            with col_a:
                if st.button(
                    "Select all", use_container_width=True, key="p07_ind_all",
                ):
                    st.session_state["p07_selected_indicators"] = set(
                        ALL_INDICATOR_IDS
                    )
                    st.session_state["p07_indicator_generation"] += 1
                    st.rerun()
            with col_b:
                if st.button(
                    "Deselect all",
                    use_container_width=True, key="p07_ind_none",
                ):
                    st.session_state["p07_selected_indicators"] = set()
                    st.session_state["p07_indicator_generation"] += 1
                    st.rerun()

        for pillar, label in [
            ("air",    "Air Pollution"),
            ("ghg",    "GHG emissions"),
            ("nature", "Nature/Land"),
        ]:
            _render_pillar_indicators_p07(pillar, label, generation)

    return st.session_state["p07_selected_indicators"]


def _render_pillar_indicators_p07(
    pillar: str, label: str, generation: int,
) -> None:
    """Per-pillar expander for indicator selection.

    The pillar-level toggle at the top of the expander is the parallel of
    P-04's: one click selects/deselects every indicator in this pillar
    independently of the other two. Same generation-counter pattern, so
    the per-indicator checkboxes below it refresh cleanly.
    """
    pillar_ids = INDICATORS_BY_PILLAR[pillar]
    selected   = st.session_state["p07_selected_indicators"]
    n_selected = sum(1 for ind in pillar_ids if ind in selected)
    all_in_pillar_selected = all(ind in selected for ind in pillar_ids)
    with st.expander(
        f"{label} ({n_selected} / {len(pillar_ids)} selected)",
        expanded=True,
    ):
        new_all = st.checkbox(
            f"**Select all {label}**",
            value=all_in_pillar_selected,
            key=f"p07_pillar_all_{pillar}_v{generation}",
        )
        if new_all and not all_in_pillar_selected:
            selected.update(pillar_ids)
            st.session_state["p07_indicator_generation"] += 1
            st.rerun()
        elif not new_all and all_in_pillar_selected:
            for ind in pillar_ids:
                selected.discard(ind)
            st.session_state["p07_indicator_generation"] += 1
            st.rerun()

        st.divider()

        cols = st.columns(3)
        for i, indicator_id in enumerate(pillar_ids):
            col = cols[i % 3]
            with col:
                checked = indicator_id in selected
                new_checked = st.checkbox(
                    display_name(indicator_id),
                    value=checked,
                    key=f"p07_ind_{indicator_id}_v{generation}",
                )
                if new_checked and indicator_id not in selected:
                    selected.add(indicator_id)
                elif not new_checked and indicator_id in selected:
                    selected.discard(indicator_id)


# ──────────────────────────────────────────────────────────────────
# Run section — validation + Run button
# ──────────────────────────────────────────────────────────────────

def _render_run_section(
    suppliers: list[Supplier], radius_km: int, indicators: set[str],
) -> None:
    """Final summary + Run button. Validates and warns."""
    with st.container(border=True):
        st.markdown("### Run")
        n_suppliers   = len(suppliers)
        n_indicators  = len(indicators)
        estimated_min = n_suppliers * 1  # ~1 min/supplier rough estimate

        st.markdown(
            f"**Suppliers.** {n_suppliers} "
            f"&nbsp;&nbsp; **Buffer.** {radius_km} km "
            f"&nbsp;&nbsp; **Indicators.** {n_indicators} "
            f"&nbsp;&nbsp; **Est. time.** ~{estimated_min} min"
        )

        # Validation.
        errors: list[str] = []
        if n_suppliers == 0:
            errors.append("Pick at least one supplier above.")
        if n_suppliers > _MAX_SUPPLIERS:
            errors.append(
                f"At most {_MAX_SUPPLIERS} suppliers per batch "
                f"(you have {n_suppliers}). Reduce the list."
            )
        if n_indicators == 0:
            errors.append("Select at least one indicator.")

        for err in errors:
            st.warning(err)

        if n_suppliers >= 10:
            st.info(
                f"⏱️ Batch screening runs sequentially — expect ~"
                f"{estimated_min} minutes for this batch. You can "
                f"leave the tab and come back; the run continues."
            )

        can_run = not errors
        if st.button(
            "Run Prioritisation",
            type="primary",
            disabled=not can_run,
            use_container_width=True,
        ):
            _commit_and_navigate(suppliers, radius_km, indicators)


def _commit_and_navigate(
    suppliers: list[Supplier], radius_km: int, indicators: set[str],
) -> None:
    """Write prioritisation_setup and navigate to P-08."""
    today = date.today()
    start = today - timedelta(days=90)
    st.session_state["prioritisation_setup"] = {
        "suppliers":  [
            {
                "id": s.id, "name": s.name,
                "lat": s.lat, "lon": s.lon, "source": s.source,
            }
            for s in suppliers
        ],
        "radius_km":  radius_km,
        "time_range": [start.isoformat(), today.isoformat()],
        "indicators": sorted(indicators),
        "mode":       "prioritisation",
    }
    # Clear any prior P-08 state.
    st.session_state.pop("prioritisation_state", None)
    # M-P07: P-08 doesn't exist yet — stub navigation. Until then, surface
    # a toast and stay on P-07.
    try:
        st.switch_page("pages/08_Prioritisation_Results.py")
    except Exception:
        st.toast(
            "✓ Setup saved to session. P-08 (results) lands in M-P08.1.",
            icon="📋",
        )
