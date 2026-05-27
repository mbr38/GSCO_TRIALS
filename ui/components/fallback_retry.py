"""Single-supplier fallback retry → patch-on-existing re-screening (§5.3).

The C4b failure-tile "Why?" expander offers two retry buttons on a
fallback-eligible indicator that failed for sparse coverage. Clicking one
re-screens **only that indicator** with the chosen fallback strategy
(``engine.orchestrator.patch_indicators``), preserving the rest of the
payload, and invalidates only that indicator's map tile (M-UI-A5 / FB18).

`patch_result` is the pure, testable core (no Streamlit). `apply_retry` is
the thin Streamlit-coupled wrapper the button click calls.
"""

from __future__ import annotations

import streamlit as st

from engine.orchestrator import patch_indicators
from ui.components.multi_map_state import invalidate_indicator

# Indicators that flow through six_step and can be recovered with a fallback
# (FB10 climatology scope + SPPY-eligible NDVI). Mirrors orchestrator's
# patchable set; co2/static-Nature indicators don't use six_step.
_RETRYABLE_NON_AIR: frozenset[str] = frozenset({"ghg.ch4", "ghg.viirs", "nature.ndvi"})

# Sparse-coverage skipped reasons the fallback can actually address. Coverage
# gaps (out_of_coverage, Mode 4) and user-input issues (buffer too small) are
# NOT retryable — a fallback can't conjure data the asset never had here.
RETRYABLE_SKIPPED_REASONS: frozenset[str] = frozenset({
    "no_s5p_pixels", "no_cams_pixels", "no_maiac_pixels", "no_viirs_pixels",
    "no_modis_pixels", "no_dw_pixels", "background_ring_no_data",
})

# Strategy labels for the two buttons (§5.3).
STRATEGY_SPPY: str = "sppy"
STRATEGY_SLIDING: str = "sliding_lookback"


def is_retryable(indicator_id: str) -> bool:
    """True when `indicator_id` is a fallback-eligible (six_step) indicator."""
    return indicator_id.startswith("air.") or indicator_id in _RETRYABLE_NON_AIR


def reason_is_retryable(skipped_reason: str | None) -> bool:
    """True when a fallback could plausibly recover this failure."""
    return skipped_reason in RETRYABLE_SKIPPED_REASONS


def patch_result(
    result: dict,
    indicator_id: str,
    strategy: str,
    ee_client=None,
) -> dict:
    """Pure core: return a patched copy of `result` with `indicator_id`
    recomputed under `strategy`. No-op (returns `result`) if the payload
    lacks the `_meta` needed to re-screen.
    """
    meta = result.get("_meta") or {}
    aoi = meta.get("aoi")
    time_range = meta.get("time_range")
    if aoi is None or not time_range:
        return result
    selected = set(meta.get("selected_indicators") or [])
    return patch_indicators(
        result,
        aoi=aoi,
        indicator_ids={indicator_id},
        selected_indicators=selected,
        time_range=tuple(time_range),
        ee_client=ee_client,
        strategy=strategy,
    )


def apply_retry(indicator_id: str, strategy: str) -> bool:
    """Patch the current P-05 screening for `indicator_id` and invalidate its
    map tile. Returns True if a screening was present and patched.

    Wired to the C4b retry buttons. After this returns True the caller
    should ``st.rerun()`` so the grid re-renders with the patched value.
    """
    state = st.session_state.get("page_state")
    result = getattr(state, "result", None)
    if state is None or not isinstance(result, dict):
        return False
    state.result = patch_result(result, indicator_id, strategy)
    invalidate_indicator(st.session_state, indicator_id)
    return True
