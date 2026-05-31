"""Per-indicator trend drill-down view (M-TREND-A2).

Plot-first (decision-log U1): the per-day scatter + Theil–Sen line leads, then
a verdict badge, then the separate confidence / significance / seasonal /
attributability surfaces (U5). Reached from a screening via the "view trend →"
affordance (C4b tiles) or the single-indicator map "View trend" button, both of
which set the active trend indicator and route to the **dedicated P-06 page**
(`pages/06_Trend_View.py`). The trend is computed once over the screening
window (U4 — no window picker) and cached in session, so re-renders and overlay
toggles never re-fetch and the verdict badge is fixed (UT5).

Two render paths share the same presentation body:
- `render_active_trend(setup, result)` — live, reads the active trend indicator
  and computes on open via `trend_compute` (EE).
- `render_saved_trend(record)` — re-open from P-10, renders from the stored
  per-day series with no recompute (UT9).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import streamlit as st

from engine.core.trend import base_indicator_id
from ui.components.trend_compute import compute_trend_for_indicator
from ui.components.trend_plot import build_trend_figure
from ui.components.trend_record import (
    STALE_TREND_BANNER,
    is_stale_trend_record,
    make_trend_entry,
    seasonal_caveat,
    significance_text,
    slope_display,
    verdict_badge,
)

_ACTIVE_KEY = "active_trend_indicator"      # select_key | None
_DISPLAY_KEY = "active_trend_display_name"  # human label for the active indicator
_CACHE_KEY = "trend_result_cache"           # {run_id::base_id: result}
LOADED_RECORD_KEY = "loaded_trend_record"   # a saved record re-opened from P-10

_TONE_COLOUR = {
    "rising":      "#dc2626",
    "falling":     "#2563eb",
    "none":        "#6b7280",
    "unavailable": "#9ca3af",
}


# ---------------------------------------------------------------------------
# Session-state helpers (entry points call set_active_trend then switch_page)
# ---------------------------------------------------------------------------

def set_active_trend(select_key: str, display_name: str = "") -> None:
    st.session_state[_ACTIVE_KEY] = select_key
    st.session_state[_DISPLAY_KEY] = display_name


def get_active_trend() -> str | None:
    return st.session_state.get(_ACTIVE_KEY)


def clear_active_trend() -> None:
    st.session_state.pop(_ACTIVE_KEY, None)
    st.session_state.pop(_DISPLAY_KEY, None)


# ---------------------------------------------------------------------------
# Live render (P-06 page, computed from the active screening)
# ---------------------------------------------------------------------------

def render_active_trend(setup: dict, result: dict) -> None:
    """Render the live trend for the active indicator (computed on open).

    Computes once per (run_id, indicator) and caches in session, so overlay
    toggles and reruns never re-fetch. Returns early with an info note when
    no indicator is active.
    """
    active = get_active_trend()
    if active is None:
        st.info(
            "No indicator selected. Open a screening (P-05) and choose "
            "**view trend →** on an indicator tile, or **View trend** in the "
            "single-indicator map, to drill into its trend."
        )
        return

    base_id = base_indicator_id(active)
    display_name = st.session_state.get(_DISPLAY_KEY) or base_id
    st.subheader(f"Trend — {display_name}")

    run_id = _current_run_id()
    result_trend = _cached_trend(run_id, base_id, setup, result)
    if result_trend is None:
        return  # error already surfaced
    lat = (setup.get("centre") or {}).get("lat")
    _render_trend_body(result_trend, display_name, lat, key_prefix=base_id)
    _render_save_action(base_id, display_name, setup, result_trend)


def render_saved_trend(record: dict) -> None:
    """Re-open a saved trend record from P-10 — renders from the stored
    series with no recompute (UT9)."""
    display_name = record.get("display_name") or record.get("indicator_id") or "Trend"
    result_trend = record.get("trend_result") or {}
    setup = record.get("screening_setup") or {}
    lat = (setup.get("centre") or {}).get("lat")
    st.subheader(f"Trend — {display_name}")
    st.caption("Saved trend analysis (rendered from the stored per-day series).")
    # M-DIAG-A4 / DGC5 — stale-data banner for trends computed under an older
    # engine methodology (e.g. the pre-fix spatial-std denominator). The stored
    # series is still rendered (UT9: no recompute) but the user is told the
    # numbers don't reflect the current detector.
    if is_stale_trend_record(record):
        st.warning(STALE_TREND_BANNER)
    _render_trend_body(result_trend, display_name, lat, key_prefix="saved")


# ---------------------------------------------------------------------------
# Shared body (plot + verdict + metrics + overlays)
# ---------------------------------------------------------------------------

def _render_trend_body(result: dict, display_name: str, lat, *, key_prefix: str) -> None:
    seasonal = bool(result.get("seasonal_flag"))
    bucket = result.get("significance_bucket")

    # Overlay toggles (UT3): all default-off except the season-banded axis,
    # which is default-ON when the seasonal flag fires.
    with st.expander("Plot overlays", expanded=False):
        tcol1, tcol2, tcol3, tcol4 = st.columns(4)
        show_season = tcol1.checkbox(
            "Season bands", value=seasonal, key=f"{key_prefix}_ov_season",
        )
        show_conf = tcol2.checkbox("Confidence band", value=False, key=f"{key_prefix}_ov_conf")
        show_cov = tcol3.checkbox("Coverage details", value=False, key=f"{key_prefix}_ov_cov")
        show_anom = tcol4.checkbox("Anomaly days", value=False, key=f"{key_prefix}_ov_anom")

    anomaly_dates = ((result.get("provenance") or {}).get("anomaly_dates_utc")) or []
    fig = build_trend_figure(
        result,
        lat=lat,
        display_name=display_name,
        show_season_bands=show_season,
        show_confidence_band=show_conf,
        show_anomaly_markers=show_anom,
        anomaly_dates=anomaly_dates,
    )
    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_plot")
    st.caption(
        "Drag the slider beneath the chart (or box-select on the plot) to zoom "
        "into a date sub-window. Zoom is visual only — the verdict reflects the "
        "computed Theil–Sen slope + Mann–Kendall significance over the full "
        "window, not the displayed steepness."
    )
    if show_cov:
        _render_coverage_caption(result)

    # Verdict badge (leads the metrics; pure function of the result → fixed).
    badge = verdict_badge(result)
    colour = _TONE_COLOUR.get(badge["tone"], "#6b7280")
    st.markdown(
        f"<div style='font-size:1.25em;font-weight:700;color:{colour};"
        f"margin:8px 0 2px 0;'>{badge['text']}</div>",
        unsafe_allow_html=True,
    )

    if bucket == "unavailable":
        n = (result.get("coverage") or {}).get("n_valid_days")
        st.info(
            f"Too few observations for a reliable trend (N={n}). The scatter "
            "above shows the points that were available; enable the coverage "
            "strip overlay to make the sparsity explicit."
        )
        return

    # Separate parallel surfaces (U5): confidence / significance / raw slope.
    # Rendered as markdown (not st.metric) so the full significance string
    # "p = 0.159 · no significant trend" shows without ellipsis truncation.
    conf = result.get("trend_confidence")
    m1, m2 = st.columns(2)
    with m1:
        _metric_block("Trend confidence", "—" if conf is None else f"{conf:.2f}")
    with m2:
        _metric_block("Raw slope", slope_display(result))
    _metric_block("Significance", significance_text(result), full_width=True)

    caveat = seasonal_caveat(result)
    if caveat:
        st.caption(f"⚠️ Possibly seasonal — {caveat}")


def _metric_block(label: str, value: str, *, full_width: bool = False) -> None:
    """A metric-style label + value rendered as markdown, so long values
    (e.g. the full p-value + bucket string) wrap rather than truncate the way
    ``st.metric`` does."""
    st.markdown(
        f"<div style='line-height:1.25;margin:2px 0 8px 0;'>"
        f"<div style='font-size:0.82em;color:#6b7280;'>{label}</div>"
        f"<div style='font-size:1.35em;font-weight:700;'>{value}</div></div>",
        unsafe_allow_html=True,
    )


def _render_coverage_caption(result: dict) -> None:
    cov = result.get("coverage") or {}
    st.caption(
        f"Coverage — {cov.get('n_valid_days', '—')} valid days over a "
        f"{cov.get('span_days', '—')}-day window; largest gap "
        f"{cov.get('largest_gap_days', '—')} days. Gaps appear as breaks in "
        "the scatter (no interpolation)."
    )


# ---------------------------------------------------------------------------
# Save (UT9)
# ---------------------------------------------------------------------------

def _render_save_action(base_id: str, display_name: str, setup: dict, result: dict) -> None:
    if not st.button("💾 Save trend analysis", key=f"save_trend_{base_id}"):
        return
    if "saved_analyses" not in st.session_state:
        st.session_state["saved_analyses"] = []
    now = datetime.now(timezone.utc)
    meta = setup.get("centre_metadata") or {}
    where = meta.get("node_name") or meta.get("source") or "screening AOI"
    name = f"Trend · {display_name} · {where}"
    entry = make_trend_entry(
        entry_id=str(uuid.uuid4()),
        name=name,
        indicator_id=base_id,
        display_name=display_name,
        screening_setup=setup,
        result=result,
        date_saved_iso=now.isoformat(),
    )
    st.session_state["saved_analyses"].append(entry)
    st.toast(f"Saved trend — '{name}'.", icon="📈")


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _cached_trend(run_id: str, base_id: str, setup: dict, result: dict) -> dict | None:
    """Compute-once-per-(run, indicator); cache in session. None on error
    (a message is surfaced)."""
    cache = st.session_state.setdefault(_CACHE_KEY, {})
    key = f"{run_id}::{base_id}"
    if key in cache:
        return cache[key]
    try:
        with st.spinner(f"Computing trend for {base_id}…"):
            trend_result = compute_trend_for_indicator(base_id, setup, result)
    except Exception as exc:  # noqa: BLE001 — surface, don't crash the page
        st.error(f"Trend computation failed for {base_id}: {exc}")
        return None
    cache[key] = trend_result
    return trend_result


def _current_run_id() -> str:
    state = st.session_state.get("page_state")
    return getattr(state, "run_id", "no-run") if state is not None else "no-run"
