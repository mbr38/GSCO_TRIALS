"""Pure presentation + persistence helpers for the per-indicator trend view.

No Streamlit, no Earth Engine — just functions over the M-TREND-A1
`compute_trend` contract. Shared by the live view (`trend_view`), the saved
record round-trip, and the P-11 report section, so the verdict grammar and
the saved-record shape stay in lockstep across all three (decision-log
U5/U6/U8).
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Verdict badge (UT6 / decision-log U5)
# ---------------------------------------------------------------------------

def verdict_badge(result: dict) -> dict:
    """Build the verdict badge from the trend result.

    Returns ``{"text": str, "tone": str}`` where tone ∈
    {"rising", "falling", "none", "unavailable"} — the view maps tone to a
    colour. The badge reflects the **computed** slope + significance bucket
    only; it never folds in confidence/seasonal/attributability (those are
    separate parallel surfaces, U5). A "· possibly seasonal" caveat is
    appended when the seasonal flag fires.

    This is a pure function of `result`, so the badge is invariant under any
    view-side axis pan/zoom (the UT5 invariant holds by construction).
    """
    bucket = result.get("significance_bucket")
    if bucket == "unavailable":
        n = (result.get("coverage") or {}).get("n_valid_days")
        suffix = f" (N={n})" if n is not None else ""
        return {"text": f"Trend unavailable — too few observations{suffix}",
                "tone": "unavailable"}

    slope = result.get("trend")
    seasonal = " · possibly seasonal" if result.get("seasonal_flag") else ""

    if bucket == "none" or slope is None or slope == 0:
        return {"text": f"No significant trend{seasonal}", "tone": "none"}

    direction = "Rising" if slope > 0 else "Falling"
    tone = "rising" if slope > 0 else "falling"
    qualifier = "significant" if bucket == "significant" else "weak/emerging"
    arrow = "↑" if slope > 0 else "↓"
    return {"text": f"{arrow} {direction} ({qualifier}){seasonal}", "tone": tone}


# ---------------------------------------------------------------------------
# Metrics (separate parallel surfaces, U5/UT6)
# ---------------------------------------------------------------------------

def significance_text(result: dict) -> str:
    """p-value + bucket, e.g. ``"p = 0.032 · significant"``."""
    bucket = result.get("significance_bucket")
    if bucket == "unavailable":
        return "unavailable"
    p = result.get("trend_p")
    label = {"significant": "significant",
             "weak_emerging": "weak / emerging",
             "none": "no significant trend"}.get(bucket, bucket or "—")
    p_str = "—" if p is None else f"p = {p:.3g}"
    return f"{p_str} · {label}"


def slope_display(result: dict, *, unit: str | None = None) -> str:
    """Raw Theil–Sen slope in display units per year, e.g. ``"+1.2e-05 /yr"``."""
    slope = result.get("trend")
    if slope is None:
        return "—"
    u = f" {unit}" if unit else ""
    return f"{slope:+.3g}{u}/yr"


def seasonal_caveat(result: dict) -> str | None:
    """The seasonal-flag caveat text, or None when not flagged."""
    if not result.get("seasonal_flag"):
        return None
    return (
        "Window spans under a year — an un-deseasonalised slope can read "
        "phenology as trend. Treat the direction as provisional."
    )


# ---------------------------------------------------------------------------
# Saved record (UT9 / decision-log U8)
# ---------------------------------------------------------------------------

def make_trend_entry(
    *,
    entry_id: str,
    name: str,
    indicator_id: str,
    display_name: str,
    screening_setup: dict,
    result: dict,
    date_saved_iso: str,
) -> dict:
    """Build a saved-analyses entry of `type="trend"` (UT9).

    Stored in the **shared** Saved Analyses store alongside `screening` /
    `prioritisation` records, discriminated by `type`. The full
    M-TREND-A1 `result` — **including the per-day `series`** — is persisted
    so both the re-opened view and the report SVG re-render from it with no
    recompute (the series is load-bearing). `screening_setup` is carried so
    the screening→trend relationship is preserved and the M-UX-A1 free-text
    search (name + supplier + location, extended to indicator) still works.
    """
    return {
        "id":            entry_id,
        "name":          name,
        "type":          "trend",
        "indicator_id":  indicator_id,
        "display_name":  display_name,
        # Relationship to the parent screening (same AOI/supplier metadata).
        "screening_setup": screening_setup,
        # The full per-indicator trend result, incl. the per-day series.
        "trend_result":  result,
        "date_saved":    date_saved_iso,
    }


def trend_search_indicator(save: dict) -> str:
    """The indicator string a trend save contributes to M-UX-A1 search.

    Empty for non-trend saves. Lets `p10_list._save_search_fields` add the
    indicator id + display name without special-casing record types inline.
    """
    if save.get("type") != "trend":
        return ""
    return f"{save.get('indicator_id') or ''} {save.get('display_name') or ''}".strip()
