"""Interactive Plotly trend chart for the live P-06 view (M-TREND-A2).

The live view uses Plotly (already a project dependency — see
`p08_risk_matrix`) so the user can **box-zoom / pan and drag a date-range
slider to inspect a sub-window close-up** (UX feedback), with hover read-outs
and legible fonts. The P-11 *report* keeps the static inline SVG
(`trend_svg.py`) because the PDF path can't embed an interactive chart — the
two share the same grammar (per-day scatter + red Theil–Sen line + season
context), just different renderers.

UT5 invariant preserved: zoom is client-side and never recomputes anything, so
the verdict badge (a pure function of the trend result, rendered separately)
stays fixed regardless of the displayed window.
"""

from __future__ import annotations

from datetime import date
from statistics import median

from ui.components.trend_svg import _season_label, season_regime

_DOT = "#2563eb"
_LINE = "#dc2626"
_BAND = "rgba(148,163,184,0.16)"
_CONF = "rgba(37,99,235,0.15)"
_ANOMALY = "#f59e0b"


def build_trend_figure(
    result: dict,
    *,
    lat: float | None = None,
    display_name: str = "Site value",
    show_season_bands: bool = False,
    show_confidence_band: bool = False,
    show_anomaly_markers: bool = False,
    anomaly_dates: list[str] | None = None,
):
    """Build an interactive Plotly figure for the trend result.

    Returns a `plotly.graph_objects.Figure`. Below the hard floor
    (`trend is None`) the Theil–Sen line is omitted and only the scatter is
    drawn. Overlays are caller-controlled booleans.
    """
    import plotly.graph_objects as go  # lazy — keeps trend_view import light

    fig = go.Figure()
    series = result.get("series") or []
    if not series:
        fig.add_annotation(text="No observations in the window.",
                           showarrow=False, font=dict(size=14, color="#64748b"))
        fig.update_layout(height=320, paper_bgcolor="white", plot_bgcolor="white")
        return fig

    xs = [iso for iso, _ in series]
    ys = [float(v) for _, v in series]

    # Season context behind the data (shapes are added via layout below).
    regime = season_regime(lat)
    shapes, annotations = [], []
    if show_season_bands and regime in ("n_temperate", "s_temperate"):
        shapes, annotations = _season_shapes(xs[0], xs[-1], regime)
    elif show_season_bands and regime == "tropical":
        annotations.append(dict(
            xref="paper", yref="paper", x=0.0, y=1.04, yanchor="top",
            showarrow=False,
            text="Seasonality unclear at this latitude — tropical wet/dry "
                 "varies regionally, so no season bands are drawn.",
            font=dict(size=11, color="#000000"), align="left",
        ))

    # Confidence band (drawn first so it sits behind the markers/line).
    slope = result.get("trend")
    if slope is not None:
        ords = [date.fromisoformat(i).toordinal() for i in xs]
        xy = [o / 365.25 for o in ords]
        intercept = median(v - slope * x for v, x in zip(ys, xy))
        if show_confidence_band:
            _add_confidence_band(fig, go, xs, ys, slope, intercept, xy)

    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers", name="Daily site value",
        marker=dict(color=_DOT, size=7, opacity=0.72),
        hovertemplate="%{x|%d %b %Y}<br>%{y:.4g}<extra></extra>",
    ))

    if slope is not None:
        x0, x1 = ords[0], ords[-1]
        line_y = [slope * (x0 / 365.25) + intercept, slope * (x1 / 365.25) + intercept]
        fig.add_trace(go.Scatter(
            x=[xs[0], xs[-1]], y=line_y, mode="lines", name="Theil–Sen trend",
            line=dict(color=_LINE, width=3),
            hovertemplate="Theil–Sen trend<extra></extra>",
        ))

    if show_anomaly_markers and anomaly_dates:
        aset = set(anomaly_dates)
        ax = [i for i in xs if i in aset]
        ay = [v for i, v in zip(xs, ys) if i in aset]
        if ax:
            fig.add_trace(go.Scatter(
                x=ax, y=ay, mode="markers", name="Anomaly day",
                marker=dict(color=_ANOMALY, size=11, symbol="diamond",
                            line=dict(color="white", width=1)),
                hovertemplate="Anomaly · %{x|%d %b %Y}<br>%{y:.4g}<extra></extra>",
            ))

    # Range-slider label. The slider strip renders *below* the main plot, i.e.
    # at NEGATIVE paper-y (paper y=0 is the main x-axis; y=1 its top). It's laid
    # out client-side so its exact band isn't in the JSON — y≈-0.18 lands on the
    # strip for the current thickness/height; nudge if it drifts.
    annotations = list(annotations) + [dict(
        xref="paper", yref="paper", x=0.012, xanchor="left",
        y=-0.18, yanchor="middle", showarrow=False,
        text="range-slider", font=dict(size=11, color="#64748b"),
    )]

    fig.update_layout(
        # Taller frame (vs the original 520) so the plot reads clearly.
        height=640,
        # Top margin gives the title + the (optional) tropical caveat line room
        # to stack without colliding; bottom is kept tight because the slider +
        # x-title get their space from `automargin` (below), which expands these
        # minimums to fit the rotated y-title / x-title / slider as needed.
        margin=dict(l=70, r=28, t=96, b=70),
        title=dict(text=f"{display_name} — daily site value",
                   font=dict(size=18, color="#000000")),
        font=dict(size=14, color="#000000"),
        paper_bgcolor="white",
        plot_bgcolor="white",
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(size=12, color="#000000")),
        shapes=shapes,
        annotations=annotations,
    )
    # Word-format dates + a draggable range slider to zoom a sub-window.
    # Explicit black tick + title fonts so the axes read clearly (the chart
    # paints its own white background, independent of the app theme). The
    # slider is a faithful miniature of the whole chart (dots + trend +
    # anomalies) — see the labelled caption in trend_view.py — so a thicker
    # strip makes that mini-map legible rather than a cramped smear.
    fig.update_xaxes(
        title_text="Date", title_standoff=16, automargin=True,
        type="date", tickformat="%d %b %Y",
        gridcolor="#e5e7eb", linecolor="#94a3b8",
        tickfont=dict(color="#000000"), title_font=dict(color="#000000"),
        rangeslider=dict(visible=True, thickness=0.16,
                         bgcolor="#f8fafc", bordercolor="#cbd5e1", borderwidth=1),
    )
    fig.update_yaxes(
        title_text=display_name, title_standoff=16, automargin=True,
        gridcolor="#e5e7eb", linecolor="#94a3b8",
        tickfont=dict(color="#000000"), title_font=dict(color="#000000"),
    )
    return fig


def _add_confidence_band(fig, go, xs, ys, slope, intercept, xy) -> None:
    """±1 residual-std envelope around the line (a geometric fit cue, not a
    formal CI — UT3)."""
    resid = [v - (slope * x + intercept) for v, x in zip(ys, xy)]
    if len(resid) < 2:
        return
    mean_r = sum(resid) / len(resid)
    sd = (sum((r - mean_r) ** 2 for r in resid) / (len(resid) - 1)) ** 0.5
    upper = [slope * x + intercept + sd for x in xy]
    lower = [slope * x + intercept - sd for x in xy]
    fig.add_trace(go.Scatter(
        x=xs + xs[::-1], y=upper + lower[::-1], fill="toself",
        fillcolor=_CONF, line=dict(width=0), name="±1σ band",
        hoverinfo="skip", showlegend=True,
    ))


def _season_shapes(start_iso: str, end_iso: str, regime: str):
    """Alternating season vrects + labels across the window (temperate only)."""
    start, end = date.fromisoformat(start_iso), date.fromisoformat(end_iso)
    boundaries = sorted(
        date(yr, m, 1)
        for yr in range(start.year - 1, end.year + 2)
        for m in (3, 6, 9, 12)
    )
    shapes, annotations = [], []
    prev = start
    shade = False
    for b in boundaries:
        if b <= start:
            continue
        seg_end = min(b, end)
        if seg_end > prev:
            if shade:
                shapes.append(dict(
                    type="rect", xref="x", yref="paper",
                    x0=prev.isoformat(), x1=seg_end.isoformat(), y0=0, y1=1,
                    fillcolor=_BAND, line=dict(width=0), layer="below",
                ))
            mid = date.fromordinal((prev.toordinal() + seg_end.toordinal()) // 2)
            annotations.append(dict(
                x=mid.isoformat(), y=1.0, yref="paper", showarrow=False,
                text=_season_label(mid.month, regime),
                font=dict(size=10, color="#000000"), yanchor="bottom",
            ))
            shade = not shade
        prev = seg_end
        if prev >= end:
            break
    return shapes, annotations
