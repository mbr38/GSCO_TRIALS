"""Reusable analysis-window picker (M-UI-A3).

Profile-driven Streamlit component for selecting the analysis time
range on P-04 (Inspect setup) and P-07 (Prioritisation setup). Built
generically so future item 1.4 can drop the same component onto P-06
with a ``trend`` profile via a fixture-only change.

UI layout (collapsed):

    Analysis window
    [ 30 d ] [ 90 d ] [ 6 mo ] [ 12 mo ] [ Custom ]

    Estimated compute time: ~95 seconds (approximate)

    ▸ Advanced options

When the user picks ``Custom``, a date-range pair appears below the
chips. When ``Advanced options`` is expanded (in preset mode only),
the end-date anchor toggle reveals; in Custom mode the toggle hides to
avoid two controls editing the same end date.

The pure helpers (``compute_estimate_seconds``, ``validate_window``,
``complexity_factor_for``) are testable without Streamlit; the render
function is the only Streamlit-coupled surface.
"""

# M-UI-A3
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

import streamlit as st

from demo.window_picker_profiles import (
    ComputeEstimateCoefficients,
    Preset,
    WindowProfile,
    load_profile,
)
from engine.constants import EARLIEST_SCREENING_DATE


_CUSTOM_KEY: str = "custom"


# ---------------------------------------------------------------------------
# Return value
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WindowSelection:
    """User's window choice. Returned by the render function on success."""

    start_date:        date
    end_date:          date
    days:              int
    estimated_seconds: float

    def as_iso_tuple(self) -> tuple[str, str]:
        """Engine-facing format — ``(YYYY-MM-DD, YYYY-MM-DD)``."""
        return (self.start_date.isoformat(), self.end_date.isoformat())


# ---------------------------------------------------------------------------
# Pure helpers — no Streamlit, fully unit-testable
# ---------------------------------------------------------------------------

def complexity_factor_for(
    aoi_buffer_km: float | None,
    coefs:         ComputeEstimateCoefficients,
) -> float:
    """Map AOI buffer radius to the compute-cost complexity factor.

    None / unknown buffer falls back to the "large" factor so the
    estimate over-promises rather than under-promises — the user is
    less likely to be surprised by a longer-than-shown wait.
    """
    if aoi_buffer_km is None:
        return coefs.complexity_factor_large
    if aoi_buffer_km <= coefs.complexity_small_max_km:
        return coefs.complexity_factor_small
    if aoi_buffer_km <= coefs.complexity_medium_max_km:
        return coefs.complexity_factor_medium
    return coefs.complexity_factor_large


def compute_estimate_seconds(
    days:          int,
    aoi_buffer_km: float | None,
    coefs:         ComputeEstimateCoefficients,
    n_suppliers:   int = 1,
) -> float:
    """WP10 compute-time formula (placeholder coefficients).

    Per-supplier formula::

        base_overhead + (days * per_day_coef * complexity_factor)
                      + long_window_penalty   if days > threshold

    Multiplied by ``n_suppliers`` for batch screening (P-07 aggregate
    estimate, spec §12 Q-A3-1 resolution).

    Coefficients live in the profile fixture; recalibrate there as
    real benchmark data becomes available.
    """
    factor = complexity_factor_for(aoi_buffer_km, coefs)
    per_supplier = coefs.base_overhead_s + (
        days * coefs.per_day_coef_s * factor
    )
    if days > coefs.long_window_threshold_days:
        per_supplier += coefs.long_window_penalty_s
    return per_supplier * max(1, n_suppliers)


def format_estimate(seconds: float) -> str:
    """Render ``~XX seconds`` for short estimates, ``~X.X minutes`` long."""
    if seconds >= 120:
        minutes = seconds / 60
        return f"~{minutes:.1f} minutes"
    return f"~{round(seconds)} seconds"


def validate_window(
    start:         date,
    end:           date,
    profile:       WindowProfile,
    earliest_date: date,
    today:         date,
) -> list[str]:
    """Return a list of validation error messages (empty when valid).

    Order matters: most-fundamental errors first so the user sees the
    blocking issue at the top.
    """
    errors: list[str] = []
    msgs = profile.validation_messages

    if end > today:
        errors.append(msgs["end_in_future"])
    if start >= end:
        errors.append(msgs["start_after_end"])
    if start < earliest_date:
        errors.append(
            msgs["start_too_early"].format(earliest_date=earliest_date.isoformat())
        )

    days = max(0, (end - start).days)
    if days < profile.min_days:
        errors.append(msgs["below_min"])
    if days > profile.max_days:
        errors.append(msgs["above_max"])

    return errors


# ---------------------------------------------------------------------------
# Streamlit render path
# ---------------------------------------------------------------------------

def render_analysis_window_picker(
    *,
    profile_name:  str = "screening",
    key_prefix:    str,
    aoi_buffer_km: float | None = None,
    n_suppliers:   int  = 1,
    saved_window:  tuple[str, str] | None = None,
) -> WindowSelection | None:
    """Render the picker and return the user's selection.

    Parameters
    ----------
    profile_name
        Which profile from ``demo/window_picker_profiles.json`` to use.
        ``"screening"`` today; ``"trend"`` planned for item 1.4.
    key_prefix
        Per-call prefix for all internal ``st.session_state`` keys —
        lets the same page host two pickers (not used in v1 but
        future-proof).
    aoi_buffer_km
        AOI buffer radius for the compute-estimate complexity factor.
        ``None`` falls back to the large-AOI factor.
    n_suppliers
        For P-07 batch: multiplies the per-supplier estimate. Default 1
        keeps P-04's per-screening behaviour.
    saved_window
        WP11: when the user landed on the form via a saved-analysis
        load, pre-populate the picker with the saved (start, end) and
        surface a "Loaded from saved analysis" hint.

    Returns
    -------
    WindowSelection | None
        The user's choice. ``None`` when validation fails — callers
        should disable their Run button based on this.
    """
    profile      = load_profile(profile_name)
    earliest     = date.fromisoformat(EARLIEST_SCREENING_DATE)
    today        = date.today()
    coefs        = profile.coefficients

    # First render: seed state from saved_window (WP11) or from the
    # profile default. After first render, state survives in session.
    _initialise_state(key_prefix, profile, saved_window)

    st.markdown(f"**{profile.label}**")

    if saved_window is not None:
        s_iso, e_iso = saved_window
        st.caption(
            f"Loaded from saved analysis (window: {s_iso} → {e_iso}). "
            f"Change to re-run."
        )

    _render_preset_chips(key_prefix, profile)

    selected_preset = st.session_state[f"{key_prefix}_preset"]
    is_custom = selected_preset == _CUSTOM_KEY

    if is_custom:
        start, end = _render_custom_range(key_prefix, today, earliest)
    else:
        start, end = _resolve_preset_range(key_prefix, profile, today)

    errors = validate_window(start, end, profile, earliest, today)

    days = max(0, (end - start).days)
    estimate = compute_estimate_seconds(
        days, aoi_buffer_km, coefs, n_suppliers=n_suppliers,
    )

    _render_estimate(estimate, coefs, n_suppliers)
    _render_advanced_options(key_prefix, is_custom, today, earliest)

    if errors:
        for err in errors:
            st.warning(err)
        return None

    return WindowSelection(
        start_date=start,
        end_date=end,
        days=days,
        estimated_seconds=estimate,
    )


# ---------------------------------------------------------------------------
# Private render helpers
# ---------------------------------------------------------------------------

def _initialise_state(
    key_prefix:   str,
    profile:      WindowProfile,
    saved_window: tuple[str, str] | None,
) -> None:
    """Populate session-state defaults on first call. Idempotent."""
    preset_key = f"{key_prefix}_preset"
    if preset_key not in st.session_state:
        if saved_window is not None:
            # The saved window may not match a preset — fall through to
            # Custom mode with the saved dates pre-filled.
            st.session_state[preset_key] = _CUSTOM_KEY
            s_iso, e_iso = saved_window
            st.session_state[f"{key_prefix}_custom_start"] = date.fromisoformat(s_iso)
            st.session_state[f"{key_prefix}_custom_end"]   = date.fromisoformat(e_iso)
        else:
            st.session_state[preset_key] = profile.default_preset

    st.session_state.setdefault(f"{key_prefix}_advanced_open", False)
    st.session_state.setdefault(f"{key_prefix}_end_anchor",    "today")
    st.session_state.setdefault(f"{key_prefix}_anchor_date",   date.today())


def _render_preset_chips(key_prefix: str, profile: WindowProfile) -> None:
    """Horizontal row of preset buttons + a ``Custom`` button.

    The currently-selected chip renders with ``type="primary"`` so it
    visually stands out; the others stay secondary. Clicking a chip
    writes its key to ``{key_prefix}_preset``.
    """
    selected = st.session_state[f"{key_prefix}_preset"]
    chip_specs: list[tuple[str, str]] = [(p.key, p.label) for p in profile.presets]
    chip_specs.append((_CUSTOM_KEY, "Custom"))

    cols = st.columns(len(chip_specs))
    for col, (chip_key, chip_label) in zip(cols, chip_specs):
        with col:
            if st.button(
                chip_label,
                key=f"{key_prefix}_chip_{chip_key}",
                type="primary" if chip_key == selected else "secondary",
                use_container_width=True,
            ):
                st.session_state[f"{key_prefix}_preset"] = chip_key
                st.rerun()


def _resolve_preset_range(
    key_prefix: str,
    profile:    WindowProfile,
    today:      date,
) -> tuple[date, date]:
    """For preset mode: resolve (start, end) from the chip + end anchor."""
    preset_key = st.session_state[f"{key_prefix}_preset"]
    preset = next((p for p in profile.presets if p.key == preset_key), None)
    if preset is None:
        # Defensive — shouldn't happen unless session state was tampered.
        preset = next(p for p in profile.presets if p.key == profile.default_preset)

    end = _resolve_end_anchor(key_prefix, today)
    start = end - timedelta(days=preset.days)
    return start, end


def _render_custom_range(
    key_prefix: str,
    today:      date,
    earliest:   date,
) -> tuple[date, date]:
    """Date-range input for Custom mode. Returns the picked (start, end)."""
    start_default = st.session_state.get(
        f"{key_prefix}_custom_start", today - timedelta(days=90),
    )
    end_default = st.session_state.get(
        f"{key_prefix}_custom_end", today,
    )

    col_from, col_to = st.columns(2)
    with col_from:
        start = st.date_input(
            "From",
            value=start_default,
            min_value=earliest,
            max_value=today,
            key=f"{key_prefix}_custom_start",
        )
    with col_to:
        end = st.date_input(
            "To",
            value=end_default,
            min_value=earliest,
            max_value=today,
            key=f"{key_prefix}_custom_end",
        )

    days = max(0, (end - start).days)
    st.caption(f"Window: {days} days")
    return start, end


def _resolve_end_anchor(key_prefix: str, today: date) -> date:
    """For preset mode: today or the user's custom end-date override."""
    if not st.session_state.get(f"{key_prefix}_advanced_open", False):
        return today
    if st.session_state.get(f"{key_prefix}_end_anchor", "today") == "today":
        return today
    anchor = st.session_state.get(f"{key_prefix}_anchor_date", today)
    return anchor if isinstance(anchor, date) else today


def _render_estimate(
    estimate_seconds: float,
    coefs:            ComputeEstimateCoefficients,
    n_suppliers:      int,
) -> None:
    """Live compute-time estimate caption + soft warning for long windows."""
    suffix = "" if n_suppliers <= 1 else f" (batch of {n_suppliers} suppliers)"
    st.caption(
        f"Estimated compute time: **{format_estimate(estimate_seconds)}**"
        f" (approximate{suffix})"
    )
    if estimate_seconds > coefs.soft_warning_threshold_s:
        st.info(coefs.long_window_warning)


def _render_advanced_options(
    key_prefix: str,
    is_custom:  bool,
    today:      date,
    earliest:   date,
) -> None:
    """Advanced toggle revealing the end-date-anchor controls.

    Hidden entirely in Custom mode — the Custom "To" picker already
    owns the end date, so the toggle would be a second control fighting
    over the same value (spec §4.4 final bullet).
    """
    if is_custom:
        # Keep state stable so toggling back to a preset restores the
        # user's previous anchor — but don't render the controls.
        return

    open_key = f"{key_prefix}_advanced_open"
    with st.expander("Advanced options", expanded=st.session_state[open_key]):
        st.session_state[open_key] = True
        anchor = st.radio(
            "End date",
            options=["today", "custom"],
            format_func=lambda v: "Today" if v == "today" else "Pick a different date",
            index=0 if st.session_state.get(f"{key_prefix}_end_anchor", "today") == "today" else 1,
            key=f"{key_prefix}_end_anchor",
            horizontal=True,
        )
        if anchor == "custom":
            st.date_input(
                "End date",
                value=st.session_state.get(f"{key_prefix}_anchor_date", today),
                min_value=earliest,
                max_value=today,
                key=f"{key_prefix}_anchor_date",
            )
