"""P-08 ranked table component (M-P08.2).

Replaces M-P08.1's minimum-viable dataframe with a sortable ranked
table. Three pieces:
  - Rank-by selector (radio) drives default ordering + Rank column.
  - Rank column (leftmost) re-numbers per the active rank-by.
  - Streamlit column_config marks numeric columns as sortable.

Failed and cancelled suppliers sort to the end with no rank number.
Composite rank-by is only offered when all 3 pillars are selected
(composite is undefined otherwise).
"""

# M-P08.2
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.prioritisation_state import (
    PrioritisationState,
    SupplierResult,
    selected_pillars,
)


# Pillar columns shipped from M-P08.1's renderer — copied here so the
# ranked-table module is self-contained.
_PILLAR_COLS: tuple[tuple[str, str, str], ...] = (
    ("air",    "Air",    "air.audit_followup_priority"),
    ("ghg",    "GHG",    "ghg.audit_followup_priority"),
    ("nature", "Nature", "nature.followup_priority"),
)

_STATUS_LABELS: dict[str, str] = {
    "success":   "✅ Success",
    "partial":   "🟡 Partial",
    "failed":    "❌ Failed",
    "cancelled": "⏸ Cancelled",
}


# M-P08.2-FIX
def render_rank_by_selector(state: PrioritisationState) -> str:
    """Render the rank-by radio. Returns the selected label.

    Caller must render this ONCE per page render, *outside* any
    container that is re-entered by the S2_Running progress loop —
    Streamlit's same-key check fires a duplicate-key crash otherwise.
    """
    pillars        = selected_pillars(state.setup)
    show_composite = pillars == {"air", "ghg", "nature"}
    if not pillars:
        # Defensive — no pillars selected (shouldn't happen post-P-07).
        return "Composite"
    return _render_rank_by_selector(pillars, show_composite)


# M-P08.2-FIX
def render_ranked_table(state: PrioritisationState, rank_by: str) -> None:
    """Render the ranked dataframe. Takes ``rank_by`` as input — the
    selector is rendered separately (see ``render_rank_by_selector``).

    Safe to call repeatedly inside an ``st.empty()`` container during
    the S2_Running progress loop.
    """
    if not state.supplier_results:
        st.info(
            "Results will appear here as each supplier completes.",
            icon="📋",
        )
        return

    pillars        = selected_pillars(state.setup)
    show_composite = pillars == {"air", "ghg", "nature"}

    df            = _build_ranked_dataframe(
        state.supplier_results, pillars, show_composite, rank_by,
    )
    column_config = _build_column_config(pillars, show_composite)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
    )


def _render_rank_by_selector(
    pillars: set[str], show_composite: bool,
) -> str:
    """Radio button group above the table.

    Returns the rank-by key — one of "Composite", "Air", "GHG",
    "Nature". Composite only offered when all 3 pillars selected.
    """
    options: list[str] = []
    if show_composite:
        options.append("Composite")
    for pillar, label, _ in _PILLAR_COLS:
        if pillar in pillars:
            options.append(label)

    # Default: first option (Composite when available, else first pillar).
    default_index = 0

    col_label, col_radio = st.columns([1, 4])
    with col_label:
        st.markdown("**Rank by:**")
    with col_radio:
        choice = st.radio(
            "Rank by",
            options=options,
            index=default_index,
            horizontal=True,
            label_visibility="collapsed",
            key="p08_rank_by",
        )
    return choice


def _build_ranked_dataframe(
    supplier_results: list[SupplierResult],
    pillars: set[str],
    show_composite: bool,
    rank_by: str,
) -> pd.DataFrame:
    """Build the dataframe sorted by ``rank_by``.

    Sort order: success + partial first (descending by rank-by score),
    then failed + cancelled at the end with no rank number.
    """
    rank_by_key = _rank_by_to_payload_key(rank_by)

    rows: list[dict] = []
    has_error = any(
        r.status == "failed" and r.error for r in supplier_results
    )
    for r in supplier_results:
        row: dict = {
            "Supplier":    r.name,
            "Status":      _STATUS_LABELS.get(r.status, r.status),
            "_status":     r.status,                                # sort helper
            "_rank_score": _extract_score(r.result, rank_by_key),   # sort helper
        }
        for pillar, label, key in _PILLAR_COLS:
            if pillar in pillars:
                row[label] = _extract_score(r.result, key)
        if show_composite:
            row["Composite"] = _extract_score(
                r.result, "composite.overall_screening",
            )
        if has_error:
            # Add an Error column to every row (NaN where absent) so the
            # column appears as soon as any supplier in the batch failed.
            row["Error"] = (
                r.error[:60]
                if (r.status == "failed" and r.error)
                else None
            )
        rows.append(row)

    df = pd.DataFrame(rows)

    completed_mask = df["_status"].isin(["success", "partial"])
    completed = df[completed_mask].sort_values(
        "_rank_score", ascending=False, na_position="last",
    )
    incomplete = df[~completed_mask]  # failed + cancelled, original order
    df_sorted = pd.concat([completed, incomplete], ignore_index=True)

    # Rank column: only success/partial rows with a real rank-by score
    # get numeric ranks; failed/cancelled/no-score rows get NaN.
    ranks: list[object] = []
    rank_counter = 0
    for _, row in df_sorted.iterrows():
        if (
            row["_status"] in ("success", "partial")
            and pd.notna(row["_rank_score"])
        ):
            rank_counter += 1
            ranks.append(rank_counter)
        else:
            ranks.append(None)
    df_sorted.insert(0, "Rank", ranks)

    df_sorted = df_sorted.drop(columns=["_status", "_rank_score"])
    return df_sorted


def _rank_by_to_payload_key(rank_by: str) -> str:
    """Map the user-facing label to the engine payload key."""
    if rank_by == "Composite":
        return "composite.overall_screening"
    for _, label, key in _PILLAR_COLS:
        if label == rank_by:
            return key
    # Defensive fallback.
    return "composite.overall_screening"


def _extract_score(result: dict | None, key: str) -> float | None:
    """Pull a score out of a screening result. None on missing/failure."""
    if result is None:
        return None
    value = result.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_column_config(
    pillars: set[str], show_composite: bool,
) -> dict:
    """Streamlit column config — formats numeric columns and marks them
    sortable. Score columns formatted to 2 decimal places."""
    config: dict = {
        "Rank": st.column_config.NumberColumn(
            "Rank",
            help="Rank by the selected pillar",
            width="small",
        ),
        "Supplier": st.column_config.TextColumn(
            "Supplier", width="medium",
        ),
        "Status": st.column_config.TextColumn(
            "Status", width="small",
        ),
    }
    for pillar, label, _ in _PILLAR_COLS:
        if pillar in pillars:
            config[label] = st.column_config.NumberColumn(
                label, format="%.2f", width="small",
            )
    if show_composite:
        config["Composite"] = st.column_config.NumberColumn(
            "Composite", format="%.2f", width="small",
        )
    return config
