"""P-08 risk matrix component (M-P08.3).

2D scatter plot of supplier composite/pillar scores. Two axes are
independently selectable from the pillars the user picked in P-07
(plus Composite if all 3 pillars selected).

Failed and cancelled suppliers are omitted from the plot (locked Q3)
— a caption below the plot reports their count so the user knows
what's missing.

Hides the matrix entirely with an explanatory banner when fewer
than 2 axis options are available (locked Q2 — single-pillar batch).
"""

# M-P08.3
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from engine.constants import TRAFFIC_LIGHT_THRESHOLDS
from ui.prioritisation_state import (
    PrioritisationState,
    SupplierResult,
    selected_pillars,
)


# Mirror the table component's pillar config for consistency.
_PILLAR_COLS: tuple[tuple[str, str, str], ...] = (
    ("air",    "Air",    "air.audit_followup_priority"),
    ("ghg",    "GHG",    "ghg.audit_followup_priority"),
    ("nature", "Nature", "nature.followup_priority"),
)

# M-P08.3: traffic-light colour tokens from Appendix C of the
# Wireframes spec. Used for point colour on the composite score.
_BAND_COLOURS: dict[str, str] = {
    "red":   "#ef4444",
    "amber": "#f59e0b",
    "green": "#22c55e",
    "grey":  "#9ca3af",
}


def render_risk_matrix(state: PrioritisationState) -> None:
    """Render the axis selector + matrix scatter plot."""
    pillars        = selected_pillars(state.setup)
    show_composite = pillars == {"air", "ghg", "nature"}
    axis_options   = _build_axis_options(pillars, show_composite)

    # Q2: hide the matrix when fewer than 2 axes available.
    if len(axis_options) < 2:
        st.info(
            "**Risk matrix unavailable** — at least 2 pillars are "
            "needed to plot a 2D matrix. Your batch ran "
            f"{len(axis_options)} pillar(s). Use the **Ranking** "
            "tab for single-pillar prioritisation.",
        )
        return

    # Axis selectors.
    col_x, col_y = st.columns(2)
    with col_x:
        x_axis = st.selectbox(
            "X axis",
            options=axis_options,
            index=_default_x_index(axis_options),
            key="p08_matrix_x_axis",
        )
    with col_y:
        y_axis = st.selectbox(
            "Y axis",
            options=axis_options,
            index=_default_y_index(axis_options, x_axis),
            key="p08_matrix_y_axis",
        )

    if x_axis == y_axis:
        st.warning(
            "X and Y axes are the same — pick two different "
            "pillars to see clusters.",
        )
        return

    plottable, omitted_count = _filter_plottable(
        state.supplier_results, x_axis, y_axis,
    )

    if not plottable:
        st.info(
            "No suppliers have scores for both selected pillars. "
            "Check the Ranking tab for per-supplier status.",
        )
        return

    fig = _build_figure(plottable, x_axis, y_axis)
    # M-P08.4: point-click selection drills into that supplier's P-05.
    chart_event = st.plotly_chart(
        fig,
        use_container_width=True,
        on_select="rerun",
        selection_mode="points",
        key="p08_risk_matrix",
    )

    selected_points = (
        chart_event.selection.points
        if chart_event and getattr(chart_event, "selection", None)
        else []
    )
    if selected_points:
        point_idx = selected_points[0].get("point_index")
        if point_idx is not None and 0 <= point_idx < len(plottable):
            from ui.components.p08_ranked_table import drill_to_supplier
            drill_to_supplier(state, plottable[point_idx]["name"])

    # Numbered key — markers show an index (not the full name) to avoid label
    # overlap when suppliers cluster. Full names live here and on hover.
    _render_marker_key(plottable)

    # Q3: caption reporting omitted suppliers.
    if omitted_count > 0:
        st.caption(
            f"⏸ {omitted_count} supplier(s) failed, were cancelled, "
            f"or have no score for the selected pillars and aren't "
            f"shown. See the **Ranking** tab for the complete list."
        )


def _render_marker_key(plottable: list[dict]) -> None:
    """Render the number→supplier key beneath the matrix.

    Two columns to stay compact for batches of up to 20 suppliers.
    """
    with st.expander("Marker key (number → supplier)", expanded=True):
        half = (len(plottable) + 1) // 2
        col_a, col_b = st.columns(2)
        for col, chunk_start in ((col_a, 0), (col_b, half)):
            lines = [
                f"**{i + 1}.** {p['name']}"
                for i, p in enumerate(plottable)
                if chunk_start <= i < chunk_start + half
            ]
            if lines:
                col.markdown("  \n".join(lines))


def _build_axis_options(
    pillars: set[str], show_composite: bool,
) -> list[str]:
    """Build the list of axis options.

    Order: Composite (if available), Air, GHG, Nature — only those
    the user selected in P-07.
    """
    options: list[str] = []
    if show_composite:
        options.append("Composite")
    for pillar, label, _ in _PILLAR_COLS:
        if pillar in pillars:
            options.append(label)
    return options


def _default_x_index(axis_options: list[str]) -> int:
    """Wireframes spec default x = Air. Fall back to first option."""
    for i, opt in enumerate(axis_options):
        if opt == "Air":
            return i
    return 0


def _default_y_index(axis_options: list[str], x_axis: str) -> int:
    """Wireframes spec default y = Nature. If unavailable or equals
    x, pick the first option that isn't x."""
    for i, opt in enumerate(axis_options):
        if opt == "Nature" and opt != x_axis:
            return i
    for i, opt in enumerate(axis_options):
        if opt != x_axis:
            return i
    return 0


def _filter_plottable(
    supplier_results: list[SupplierResult], x_axis: str, y_axis: str,
) -> tuple[list[dict], int]:
    """Return (plottable_points, omitted_count).

    A supplier is plottable iff:
      - Status is "success" or "partial"
      - Both x_axis and y_axis scores are non-None
    """
    x_key = _axis_to_payload_key(x_axis)
    y_key = _axis_to_payload_key(y_axis)

    plottable: list[dict] = []
    omitted   = 0
    for r in supplier_results:
        if r.status not in ("success", "partial"):
            omitted += 1
            continue
        if r.result is None:
            omitted += 1
            continue
        x_val = r.result.get(x_key)
        y_val = r.result.get(y_key)
        if x_val is None or y_val is None:
            omitted += 1
            continue
        composite = r.result.get("composite.overall_screening")
        plottable.append({
            "name":        r.name,
            "x":           float(x_val),
            "y":           float(y_val),
            "composite":   composite,
            "supplier_id": r.supplier_id,
        })
    return plottable, omitted


def _axis_to_payload_key(axis: str) -> str:
    """Map axis label to engine payload key."""
    if axis == "Composite":
        return "composite.overall_screening"
    for _, label, key in _PILLAR_COLS:
        if label == axis:
            return key
    return "composite.overall_screening"  # Defensive.


def _build_figure(
    points: list[dict], x_axis: str, y_axis: str,
) -> go.Figure:
    """Build the Plotly scatter figure."""
    low_threshold, high_threshold = TRAFFIC_LIGHT_THRESHOLDS

    colours = [_band_colour(p["composite"]) for p in points]
    # Markers carry a short index instead of the full name — clustered
    # suppliers overlap illegibly with on-marker names (and zoom doesn't help,
    # since the text is marker-anchored). The number maps to the key rendered
    # below the chart; full names stay available on hover.
    labels  = [str(i + 1) for i in range(len(points))]
    xs      = [p["x"] for p in points]
    ys      = [p["y"] for p in points]
    hover   = [
        f"<b>{i + 1}. {p['name']}</b><br>"
        f"{x_axis}: {p['x']:.2f}<br>"
        f"{y_axis}: {p['y']:.2f}<br>"
        f"Composite: {_fmt_composite(p['composite'])}"
        for i, p in enumerate(points)
    ]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=ys,
        mode="markers+text",
        marker=dict(
            size=20,
            color=colours,
            line=dict(width=1, color="#1f2937"),
        ),
        text=labels,
        textposition="middle center",
        textfont=dict(color="#0b0f17", size=10),
        hovertext=hover,
        hoverinfo="text",
        showlegend=False,
    ))

    # Threshold lines on BOTH axes at the moderate (0.33) and high (0.66)
    # bands. High = dashed (the audit-first cut); moderate = lighter dotted so
    # the grid reads as a 3×3 band without becoming chaotic.
    for thr, dash, colour in (
        (low_threshold,  "dot",  "#4b5563"),
        (high_threshold, "dash", "#9ca3af"),
    ):
        fig.add_hline(y=thr, line_dash=dash, line_color=colour)
        fig.add_vline(x=thr, line_dash=dash, line_color=colour)

    fig.add_annotation(
        x=0.05, y=0.95, xref="paper", yref="paper",
        text=f"<i>High {y_axis}<br>only</i>",
        showarrow=False, font=dict(color="#6b7280", size=11),
    )
    fig.add_annotation(
        x=0.95, y=0.95, xref="paper", yref="paper",
        text="<b>High both<br>(audit first)</b>",
        showarrow=False, font=dict(color="#dc2626", size=11),
        xanchor="right",
    )
    fig.add_annotation(
        x=0.05, y=0.05, xref="paper", yref="paper",
        text="<i>Low both</i>",
        showarrow=False, font=dict(color="#6b7280", size=11),
    )
    fig.add_annotation(
        x=0.95, y=0.05, xref="paper", yref="paper",
        text=f"<i>High {x_axis}<br>only</i>",
        showarrow=False, font=dict(color="#6b7280", size=11),
        xanchor="right",
    )

    # Ticks at the band edges (moderate + high) so the axes read against the
    # same thresholds as the gridlines.
    tickvals  = [0.0, low_threshold, high_threshold, 1.0]
    ticktext  = ["0", f"{low_threshold:.2f}", f"{high_threshold:.2f}", "1"]
    axis_base = dict(
        range=[-0.05, 1.05],
        tickmode="array", tickvals=tickvals, ticktext=ticktext,
    )
    fig.update_layout(
        xaxis=dict(title=f"{x_axis} Follow-Up Priority", **axis_base),
        yaxis=dict(title=f"{y_axis} Follow-Up Priority", **axis_base),
        margin=dict(l=60, r=20, t=20, b=60),
        height=560,
        hovermode="closest",
    )
    return fig


def _band_colour(composite: float | None) -> str:
    """Map composite score to traffic-light point colour.

    Mirrors Appendix C of the Wireframes spec — same thresholds as
    the rest of the UI uses for chip / cell colouring.
    """
    if composite is None:
        return _BAND_COLOURS["grey"]
    low_threshold, high_threshold = TRAFFIC_LIGHT_THRESHOLDS
    if composite >= high_threshold:
        return _BAND_COLOURS["red"]
    if composite >= low_threshold:
        return _BAND_COLOURS["amber"]
    return _BAND_COLOURS["green"]


def _fmt_composite(composite: float | None) -> str:
    if composite is None:
        return "—"
    return f"{composite:.2f}"
