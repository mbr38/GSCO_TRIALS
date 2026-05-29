"""Inline-SVG trend graph — shared by the live trend view and the P-11 report.

One plot grammar (decision-log U2 / UT2): a per-day scatter + the Theil–Sen
line, with optional toggleable overlays (confidence band, coverage strip,
anomaly-day markers) and a season-banded time axis. Pure string construction —
no JS, no external assets, only `<svg>/<rect>/<line>/<polyline>/<circle>/<text>`
— so the identical output renders in the Streamlit view (`st.markdown`,
`unsafe_allow_html=True`) and survives the weasyprint PDF path unchanged (the
report's M-P11.3 requirement, decision-log U9 / UT10).

The graph paints its **own white background**, gridlines, axis ticks + titles,
a title and a legend, so it reads clearly regardless of the host app's light /
dark theme (M-TREND-A2 UX feedback). It is deliberately static: per UT5 the
verdict reflects the computed statistics, not the displayed steepness, so there
is no interactive zoom to keep in sync — the verdict badge (built separately in
`trend_record`) is a pure function of the trend result and is invariant by
construction.
"""

from __future__ import annotations

import html
from datetime import date
from statistics import median

# Layout (px). Generous margins for the y-axis title + ticks (left), the
# title + legend (top), and the x-axis ticks + title (bottom).
_PAD_L, _PAD_R, _PAD_T, _PAD_B = 66, 22, 46, 54
_DOT_R = 3.0
_N_Y_TICKS = 5

# Palette — readable on the SVG's own white background.
_BG = "#ffffff"
_FRAME = "#94a3b8"
_GRID = "#e5e7eb"
_AXIS_TEXT = "#000000"
_TITLE_TEXT = "#000000"
_DOT = "#2563eb"
_LINE = "#dc2626"
_BAND_FILL = "#f1f5f9"
_CONF_FILL = "rgba(37,99,235,0.12)"
_COVERAGE = "#60a5fa"
_ANOMALY = "#f59e0b"

_TROPICAL_LAT = 23.5


def season_regime(lat: float | None) -> str:
    """Classify the AOI latitude for season banding (UT4 / U3-SEASON).

    `"n_temperate"` / `"s_temperate"` get hemisphere-correct meteorological
    season bands; `"tropical"` (|lat| < 23.5°) degrades to "seasonality
    unclear" — no computed wet/dry calendar in v1, so no bands.
    """
    if lat is None:
        return "unknown"
    if abs(lat) < _TROPICAL_LAT:
        return "tropical"
    return "n_temperate" if lat >= 0 else "s_temperate"


_N_SEASON = {12: "Winter", 1: "Winter", 2: "Winter",
             3: "Spring", 4: "Spring", 5: "Spring",
             6: "Summer", 7: "Summer", 8: "Summer",
             9: "Autumn", 10: "Autumn", 11: "Autumn"}
_S_SEASON = {12: "Summer", 1: "Summer", 2: "Summer",
             3: "Autumn", 4: "Autumn", 5: "Autumn",
             6: "Winter", 7: "Winter", 8: "Winter",
             9: "Spring", 10: "Spring", 11: "Spring"}


def _season_label(month: int, regime: str) -> str:
    return (_S_SEASON if regime == "s_temperate" else _N_SEASON)[month]


def build_trend_svg(
    result: dict,
    *,
    lat: float | None = None,
    width: int = 760,
    height: int = 380,
    y_label: str = "Site value",
    title: str | None = None,
    show_season_bands: bool = False,
    show_confidence_band: bool = False,
    show_coverage_strip: bool = False,
    show_anomaly_markers: bool = False,
    anomaly_dates: list[str] | None = None,
) -> str:
    """Render the trend graph as a self-contained inline SVG string.

    `result` is the M-TREND-A1 `compute_trend` contract (uses `series`,
    `trend`, `coverage`). `y_label` titles the value axis (e.g. the
    indicator + unit). Below the hard floor (`trend is None`) the Theil–Sen
    line is omitted and only the scatter renders. Overlays are
    caller-controlled booleans (the view applies the default-off /
    season-on-when-flagged policy).
    """
    series = result.get("series") or []
    plot_w = width - _PAD_L - _PAD_R
    plot_h = height - _PAD_T - _PAD_B
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'font-family="-apple-system,Segoe UI,Roboto,sans-serif" '
        f'role="img" aria-label="Per-day trend scatter with Theil-Sen line">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="{_BG}"/>',
    ]
    if title:
        parts.append(
            f'<text x="{_PAD_L}" y="20" font-size="13" font-weight="700" '
            f'fill="{_TITLE_TEXT}">{html.escape(title)}</text>'
        )

    if not series:
        parts.append(
            f'<text x="{width / 2}" y="{height / 2}" text-anchor="middle" '
            f'font-size="12" fill="{_AXIS_TEXT}">'
            f'No observations in the window.</text></svg>'
        )
        return "".join(parts)

    # --- data → ordinals + values ---
    ords = [date.fromisoformat(iso).toordinal() for iso, _ in series]
    vals = [float(v) for _, v in series]
    x_min, x_max = min(ords), max(ords)
    y_min, y_max = min(vals), max(vals)
    x_span = max(1, x_max - x_min)
    y_span = (y_max - y_min) or (abs(y_max) or 1.0)
    y_lo = y_min - 0.08 * y_span
    y_hi = y_max + 0.08 * y_span
    y_range = (y_hi - y_lo) or 1.0

    def sx(o: float) -> float:
        return _PAD_L + (o - x_min) / x_span * plot_w

    def sy(v: float) -> float:
        return _PAD_T + (y_hi - v) / y_range * plot_h

    # --- season bands (behind everything) ---
    regime = season_regime(lat)
    if show_season_bands and regime in ("n_temperate", "s_temperate"):
        parts.extend(_season_bands(x_min, x_max, sx, regime, plot_h))

    # --- gridlines + ticks ---
    parts.extend(_y_gridlines(y_lo, y_hi, sx, sy, x_min, x_max))
    parts.extend(_x_ticks(x_min, x_max, sx, height))

    # --- plot frame ---
    parts.append(
        f'<rect x="{_PAD_L}" y="{_PAD_T}" width="{plot_w}" height="{plot_h}" '
        f'fill="none" stroke="{_FRAME}" stroke-width="1"/>'
    )

    # --- coverage strip ---
    if show_coverage_strip:
        parts.extend(_coverage_strip(ords, sx, height))

    # --- confidence band + Theil-Sen line ---
    slope = result.get("trend")
    intercept = None
    if slope is not None:
        x_years = [o / 365.25 for o in ords]
        intercept = median(v - slope * xy for v, xy in zip(vals, x_years))
        if show_confidence_band:
            parts.append(_confidence_band(ords, vals, slope, intercept, sx, sy))

    # --- scatter ---
    anomaly_set = set(anomaly_dates or [])
    for (iso, _), o, v in zip(series, ords, vals):
        is_anom = show_anomaly_markers and iso in anomaly_set
        colour = _ANOMALY if is_anom else _DOT
        r = _DOT_R + 1.0 if is_anom else _DOT_R
        parts.append(
            f'<circle cx="{sx(o):.1f}" cy="{sy(v):.1f}" r="{r:.1f}" '
            f'fill="{colour}" fill-opacity="0.7"/>'
        )

    if slope is not None and intercept is not None:
        y0 = slope * (x_min / 365.25) + intercept
        y1 = slope * (x_max / 365.25) + intercept
        parts.append(
            f'<line x1="{sx(x_min):.1f}" y1="{sy(y0):.1f}" '
            f'x2="{sx(x_max):.1f}" y2="{sy(y1):.1f}" '
            f'stroke="{_LINE}" stroke-width="2.5"/>'
        )

    # --- axis titles + legend ---
    parts.extend(_axis_titles(y_label, width, height, plot_h))
    parts.extend(_legend(width, slope is not None))

    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Decoration builders
# ---------------------------------------------------------------------------

def _y_gridlines(y_lo, y_hi, sx, sy, x_min, x_max) -> list[str]:
    out: list[str] = []
    x0, x1 = sx(x_min), sx(x_max)
    for i in range(_N_Y_TICKS):
        v = y_lo + (y_hi - y_lo) * i / (_N_Y_TICKS - 1)
        y = sy(v)
        out.append(
            f'<line x1="{x0:.1f}" y1="{y:.1f}" x2="{x1:.1f}" y2="{y:.1f}" '
            f'stroke="{_GRID}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{_PAD_L - 8:.1f}" y="{y + 3:.1f}" text-anchor="end" '
            f'font-size="9" fill="{_AXIS_TEXT}">{_fmt_num(v)}</text>'
        )
    return out


def _x_ticks(x_min, x_max, sx, height) -> list[str]:
    out: list[str] = []
    n = 4
    yb = height - _PAD_B + 14
    for i in range(n):
        o = x_min + (x_max - x_min) * i / (n - 1)
        x = sx(o)
        anchor = "start" if i == 0 else "end" if i == n - 1 else "middle"
        out.append(
            f'<line x1="{x:.1f}" y1="{_PAD_T}" x2="{x:.1f}" '
            f'y2="{height - _PAD_B}" stroke="{_GRID}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{x:.1f}" y="{yb}" text-anchor="{anchor}" font-size="9" '
            f'fill="{_AXIS_TEXT}">{date.fromordinal(int(o)).isoformat()}</text>'
        )
    return out


def _axis_titles(y_label, width, height, plot_h) -> list[str]:
    cx = _PAD_L + (width - _PAD_L - _PAD_R) / 2
    cy = _PAD_T + plot_h / 2
    return [
        f'<text x="{cx:.1f}" y="{height - 8}" text-anchor="middle" '
        f'font-size="10" fill="{_AXIS_TEXT}">Date</text>',
        f'<text x="16" y="{cy:.1f}" text-anchor="middle" font-size="10" '
        f'fill="{_AXIS_TEXT}" transform="rotate(-90 16 {cy:.1f})">'
        f'{html.escape(y_label)}</text>',
    ]


def _legend(width, has_line) -> list[str]:
    x = width - 250
    y = 16
    out = [
        f'<circle cx="{x}" cy="{y - 3}" r="3.5" fill="{_DOT}" fill-opacity="0.7"/>',
        f'<text x="{x + 8}" y="{y}" font-size="9" fill="{_AXIS_TEXT}">'
        f'Daily site value</text>',
    ]
    if has_line:
        lx = x + 110
        out.append(
            f'<line x1="{lx}" y1="{y - 3}" x2="{lx + 18}" y2="{y - 3}" '
            f'stroke="{_LINE}" stroke-width="2.5"/>'
        )
        out.append(
            f'<text x="{lx + 24}" y="{y}" font-size="9" fill="{_AXIS_TEXT}">'
            f'Theil–Sen trend</text>'
        )
    return out


def _season_bands(x_min, x_max, sx, regime, plot_h) -> list[str]:
    """Alternating shaded bands at meteorological-season boundaries with
    hemisphere-correct labels (UT4). Pure rendering from the date axis."""
    out: list[str] = []
    start, end = date.fromordinal(x_min), date.fromordinal(x_max)
    boundaries = sorted(
        date(yr, m, 1)
        for yr in range(start.year - 1, end.year + 2)
        for m in (3, 6, 9, 12)
    )
    prev = start
    shade = False
    for b in boundaries:
        if b <= start:
            continue
        seg_end = min(b, end)
        if seg_end > prev:
            x0, x1 = sx(prev.toordinal()), sx(seg_end.toordinal())
            if shade:
                out.append(
                    f'<rect x="{x0:.1f}" y="{_PAD_T}" width="{(x1 - x0):.1f}" '
                    f'height="{plot_h}" fill="{_BAND_FILL}"/>'
                )
            mid = date.fromordinal((prev.toordinal() + seg_end.toordinal()) // 2)
            out.append(
                f'<text x="{(x0 + x1) / 2:.1f}" y="{_PAD_T + 11}" '
                f'text-anchor="middle" font-size="8" fill="{_AXIS_TEXT}">'
                f'{_season_label(mid.month, regime)}</text>'
            )
            shade = not shade
        prev = seg_end
        if prev >= end:
            break
    return out


def _coverage_strip(ords, sx, height) -> list[str]:
    """Ticks under the x-axis marking days with an observation (UT3) — makes
    gaps explicit without interpolating."""
    y = height - _PAD_B + 18
    out = [
        f'<text x="{_PAD_L - 8}" y="{y + 6}" text-anchor="end" font-size="8" '
        f'fill="{_AXIS_TEXT}">coverage</text>'
    ]
    for o in ords:
        out.append(
            f'<rect x="{sx(o) - 0.8:.1f}" y="{y:.1f}" width="1.6" height="6" '
            f'fill="{_COVERAGE}"/>'
        )
    return out


def _confidence_band(ords, vals, slope, intercept, sx, sy) -> str:
    """A shaded ±1 residual-std envelope around the Theil–Sen line — a
    geometric sense of fit (UT3). A first-pass visual cue, not a formal CI."""
    x_years = [o / 365.25 for o in ords]
    resid = [v - (slope * xy + intercept) for v, xy in zip(vals, x_years)]
    if len(resid) < 2:
        return ""
    mean_r = sum(resid) / len(resid)
    sd = (sum((r - mean_r) ** 2 for r in resid) / (len(resid) - 1)) ** 0.5
    x0, x1 = min(ords), max(ords)
    y0 = slope * (x0 / 365.25) + intercept
    y1 = slope * (x1 / 365.25) + intercept
    pts_top = f"{sx(x0):.1f},{sy(y0 + sd):.1f} {sx(x1):.1f},{sy(y1 + sd):.1f}"
    pts_bot = f"{sx(x1):.1f},{sy(y1 - sd):.1f} {sx(x0):.1f},{sy(y0 - sd):.1f}"
    return f'<polygon points="{pts_top} {pts_bot}" fill="{_CONF_FILL}" stroke="none"/>'


def _fmt_num(v: float) -> str:
    if abs(v) < 1e-12:
        return "0"
    a = abs(v)
    if a < 0.01 or a >= 1e5:
        return f"{v:.1e}"
    if a < 1:
        return f"{v:.3g}"
    return f"{v:.4g}"
