"""Fallback composition logic for M-FALLBACK-A1 (pure, no Earth Engine).

This module holds the *decisions* and *date math* for the two coordinated
fallbacks; the EE-touching execution (re-querying the site over a previous
window, substituting a climatology baseline) lives in
``engine.core.repeatable_core.six_step`` and ``engine.core.climatology``.

Three concerns:

1. **Window math** — ``sppy_window`` shifts a window back exactly one year
   (1.1 SPPY); ``sliding_lookback_windows`` enumerates the backward search
   windows for the user-triggered sliding-lookback retry (FB5).
2. **Composition decision** — ``resolve_fallback_plan`` implements the §4.5
   decision table: given the current-year site/ring outcomes (and whether
   the ring is structurally water post-land-mask), it returns which
   fallbacks to attempt. Site-first per FB2.
3. **Provenance** — ``aoi_scale_class`` (FB19/§4.7) and
   ``build_fallback_extra`` assemble the additive ``provenance.extra``
   fields (FB20) recording exactly which fallback fired.

Spec authority: docs/M-FALLBACK-A1_spec (1).md §4.5, §4.6, §4.7.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

from engine.constants import (
    AOI_SCALE_CLASS_REGIONAL_MAX_KM,
    AOI_SCALE_CLASS_SITE_MAX_KM,
    SLIDING_LOOKBACK_MAX_STEPS,
    SLIDING_LOOKBACK_STEP_DAYS,
)


# ---------------------------------------------------------------------------
# Window math  (§4.1)
# ---------------------------------------------------------------------------

def _shift_back_one_year(iso: str) -> str:
    """Return ``iso`` shifted back exactly one calendar year.

    Feb-29 in a leap year has no Feb-29 the year before, so it clamps to
    Feb-28 — the conventional non-leap fallback. All other dates map
    cleanly via ``date.replace``.
    """
    d = date.fromisoformat(iso)
    try:
        return d.replace(year=d.year - 1).isoformat()
    except ValueError:
        # Feb 29 → Feb 28 of the prior (non-leap) year.
        return d.replace(year=d.year - 1, day=28).isoformat()


def sppy_window(time_range: tuple[str, str]) -> tuple[str, str]:
    """Same-period-previous-year window for `time_range`.

    e.g. ``("2026-03-01", "2026-05-31") → ("2025-03-01", "2025-05-31")``.
    Preserves the calendar period and varies only the year (§4.1).
    """
    start, end = time_range
    return (_shift_back_one_year(start), _shift_back_one_year(end))


def sliding_lookback_windows(
    time_range: tuple[str, str],
    *,
    step_days: int = SLIDING_LOOKBACK_STEP_DAYS,
    max_steps: int = SLIDING_LOOKBACK_MAX_STEPS,
) -> list[tuple[str, str]]:
    """Backward-search windows for the sliding-lookback retry (FB5).

    Slides the *whole* window backward in ``step_days`` increments,
    preserving its length. Window k (1-indexed) is the original window
    shifted back ``k · step_days`` days. The caller tries them in order and
    stops at the first with adequate coverage.

    Returns ``max_steps`` candidate windows (does not include the original).
    """
    start = date.fromisoformat(time_range[0])
    end = date.fromisoformat(time_range[1])
    windows: list[tuple[str, str]] = []
    for k in range(1, max_steps + 1):
        shift = timedelta(days=step_days * k)
        windows.append(
            ((start - shift).isoformat(), (end - shift).isoformat())
        )
    return windows


# ---------------------------------------------------------------------------
# Composition decision table  (§4.5)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FallbackContext:
    """Per-run fallback configuration threaded from the orchestrator.

    Passing a context to ``six_step`` activates the fallback machinery;
    ``six_step(fallback=None)`` (the default) is the pre-milestone path with
    no fallbacks, which keeps every direct-call test unchanged. When
    ``strict_audit_mode`` is True the context is present but inert (FB16) —
    indicators fail exactly as before.
    """

    strict_audit_mode: bool = False
    temporal_fallback_strategy: str = "sppy"  # "sppy" | "sliding_lookback"
    climatology_fixture: dict | None = None   # pre-loaded; None → loader reads from disk


@dataclass(frozen=True)
class FallbackOutcome:
    """What actually fired for one indicator — feeds confidence + provenance."""

    temporal_used: bool = False
    temporal_strategy: str | None = None
    temporal_window: tuple[str, str] | None = None
    climatology_used: bool = False
    climatology_vintage: str | None = None


# Shared no-op outcome (frozen → safe to share) for the normal / strict path.
NO_FALLBACK: Final[FallbackOutcome] = FallbackOutcome()


@dataclass(frozen=True)
class FallbackPlan:
    """The fallback chain to apply, derived from the current-year outcomes.

    `mode` is a machine-readable label for the §4.5 row that fired (used in
    tests and analytics). The three booleans are the actions six_step then
    executes — site-first per FB2:

    - ``attempt_sppy_site`` — re-query the SITE reduction over the SPPY window.
    - ``attempt_sppy_ring`` — re-query the RING reduction over the SPPY window
      (only Mode C, where both current-year reductions failed).
    - ``use_climatology`` — substitute the per-country climatology baseline
      for the ring if the ring is still unavailable after any SPPY attempt.
    """

    mode: str
    attempt_sppy_site: bool
    attempt_sppy_ring: bool
    use_climatology: bool


# Pre-built singletons for the table rows (frozen → safe to share).
_NORMAL = FallbackPlan("normal", False, False, False)
_STRICT_SKIP = FallbackPlan("strict_skip", False, False, False)


def resolve_fallback_plan(
    *,
    site_current_ok: bool,
    ring_current_ok: bool,
    ring_is_water: bool,
    strict_audit_mode: bool,
) -> FallbackPlan:
    """Map current-year site/ring outcomes to a fallback chain (§4.5).

    Args:
        site_current_ok:   the current-window site reduction produced a value.
        ring_current_ok:   the current-window ring reduction produced a value.
        ring_is_water:     the ring is structurally water (land_fraction below
                           the land-mask threshold) — Mode 1. Takes precedence
                           over a generic ring failure because the cause is
                           geographic, not temporal: SPPY won't recover a
                           ring that is permanently ocean, so we skip 1.1 for
                           the ring and fire climatology directly.
        strict_audit_mode: when True, all fallbacks are disabled and the
                           indicator fails exactly as in pre-milestone code
                           (FB16). This is the P-07 "Strict audit mode" toggle.

    Returns:
        FallbackPlan describing which fallbacks to attempt.
    """
    if strict_audit_mode:
        return _STRICT_SKIP

    # Mode 1 — water ring (post-M-TIER-A3 land mask). Climatology fires
    # directly for the ring; SPPY only matters for a co-failing site.
    if ring_is_water:
        return FallbackPlan(
            mode="mode_1_water",
            attempt_sppy_site=not site_current_ok,
            attempt_sppy_ring=False,
            use_climatology=True,
        )

    if site_current_ok and ring_current_ok:
        return _NORMAL

    # Mode A — site fails, background fine. SPPY the site; climatology not
    # relevant because the ring baseline is good.
    if not site_current_ok and ring_current_ok:
        return FallbackPlan("mode_a", True, False, False)

    # Mode B — background fails, site fine. Auto-apply climatology (FB15);
    # no site retry needed.
    if site_current_ok and not ring_current_ok:
        return FallbackPlan("mode_b", False, False, True)

    # Mode C — both fail. SPPY both reductions; if the SPPY ring still
    # fails, climatology substitutes (compound 0.60 × 0.75 confidence).
    return FallbackPlan("mode_c", True, True, True)


# ---------------------------------------------------------------------------
# Provenance  (§4.7 / FB20)
# ---------------------------------------------------------------------------

def aoi_scale_class(radius_km: float) -> str:
    """Classify a site-buffer radius (FB19 / §4.7).

    ``≤25 km → "site"``, ``25–100 km → "regional"``, ``>100 km → "biome"``.
    Always stamped into provenance.extra so a reviewer can see whether the
    background ring reflects local surroundings or regional-scale context.
    """
    if radius_km <= AOI_SCALE_CLASS_SITE_MAX_KM:
        return "site"
    if radius_km <= AOI_SCALE_CLASS_REGIONAL_MAX_KM:
        return "regional"
    return "biome"


def build_fallback_extra(
    *,
    radius_km: float,
    temporal_fallback_used: bool = False,
    temporal_fallback_strategy: str | None = None,
    temporal_fallback_source_window: tuple[str, str] | None = None,
    climatology_fallback_used: bool = False,
    climatology_fallback_vintage: str | None = None,
) -> dict:
    """Assemble the additive provenance.extra fields for one indicator (§4.7).

    All keys are emitted on every call so downstream readers never have to
    distinguish "absent" from "False" for the booleans; ``aoi_scale_class``
    is always present. The detail fields (``*_strategy``,
    ``*_source_window``, ``*_vintage``) are ``None`` unless the matching
    fallback fired. Naming follows the M-TIER-A1 / M-TIER-A3 snake_case,
    boolean-and-detail-paired convention (FB20).
    """
    window_str: str | None = None
    if temporal_fallback_source_window is not None:
        window_str = (
            f"{temporal_fallback_source_window[0]}/"
            f"{temporal_fallback_source_window[1]}"
        )
    return {
        "aoi_scale_class": aoi_scale_class(radius_km),
        "temporal_fallback_used": temporal_fallback_used,
        "temporal_fallback_strategy": temporal_fallback_strategy,
        "temporal_fallback_source_window": window_str,
        "climatology_fallback_used": climatology_fallback_used,
        "climatology_fallback_vintage": climatology_fallback_vintage,
    }
