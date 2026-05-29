"""P-05 state machine (M-UI-E.1).

Pure-Python state model for the Screening Results page. The Streamlit
page reads + writes ``PageState`` via session-state; this module owns the
shape and transition rules so they can be unit-tested without booting
Streamlit or Earth Engine.

See ``docs/Wireframes_All_v4.md`` §P-05 for the canonical state diagram:

    S1_Computing  --> S2_Results    (all indicators succeeded)
    S1_Computing  --> S2_Partial    (some indicators failed)
    S1_Computing  --> E1_AllFailed  (every pillar failed)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


StateName = Literal["S1_Computing", "S2_Results", "S2_Partial", "E1_AllFailed"]


# M-UX-A1 (2.6) — screening loader copy. Single source of truth for the
# S1_Computing spinner text (pages/05_Screening_Results.py). Static wording
# (locked decision UX2/UX3): the old "~30–60 seconds" estimate predated the
# M-PERF-A1 runtime work and no longer reflects observed runtimes, which run
# ~1–3 minutes and longer for large or coastal AOIs. Lives here (not inline
# in the page) so the copy is one-touch to update and unit-testable without
# booting Streamlit.
SCREENING_LOADER_COPY: str = (
    "Running screening — typically 1-3 minutes. Larger AOIs and coastal "
    "locations may take longer."
)


# Per-pillar aggregate keys used to decide whether a pillar produced any
# scores at all. Lifted from Indicator_ID_Schema_v2 §4 (per-pillar
# follow-up priorities). Kept in sync with the orchestrator's
# `_PILLAR_PRIORITY_IDS` in engine/orchestrator.py.
_PILLAR_AGGREGATE_KEYS: dict[str, str] = {
    "air":    "air.audit_followup_priority",
    "ghg":    "ghg.audit_followup_priority",
    "nature": "nature.followup_priority",
}


@dataclass(frozen=True)
class PageState:
    """The page's full state. ``st.session_state["page_state"]`` stores
    exactly one of these.

    ``name`` drives which components render. ``result`` is the engine
    output (``None`` while computing); ``error`` is a short message for
    E1_AllFailed. ``failures`` is the ``_failures`` block lifted out of
    the engine result — non-empty in S2_Partial. ``run_id`` is a UUID
    used to tag the current attempt for logging and to avoid double-runs
    across Streamlit reruns.
    """

    name: StateName
    run_id: str
    result: dict | None = None
    error: str | None = None
    failures: dict | None = None


# M-E1-INDICATOR-AWARE
def classify_result(
    result: dict,
    selected_indicators: list[str] | set[str] | None = None,
) -> StateName:
    """Map an engine result payload to the next state name.

    Selection-aware (M-E1-INDICATOR-AWARE): ``E1_AllFailed`` fires only
    when *every requested indicator* returned no data. Previously the
    classifier keyed on per-pillar follow-up priorities — those go to
    ``None`` whenever any sub-aggregate is missing (M-FOLLOWUP-FALLBACK
    strict-None), so a single-indicator run whose one selected indicator
    succeeded would still route to E1 because its pillar's aggregate was
    ``None`` over the unselected sub-aggregates. Bug reproduced with
    KBA-only screening at Bahia (`nature.kba.proximity_score = 0.24`
    real data, page showed "All pillars returned no data").

    Decision order with selection provided:

    1. **All-failed** — every entry in ``selected_indicators`` is
       missing from ``result`` or has value ``None``. Returns
       ``E1_AllFailed``.
    2. **Partial** — at least one selected indicator delivered a value
       AND either some other selected indicator returned ``None`` OR
       the orchestrator recorded indicator-level failures in
       ``_failures``. Returns ``S2_Partial``.
    3. Otherwise full success — ``S2_Results``.

    When ``selected_indicators`` is ``None`` or empty, falls back to
    the original pillar-aggregate logic (preserves backward
    compatibility for callers that don't thread the selection).
    """
    if not selected_indicators:
        return _classify_by_pillar_aggregates(result)

    any_success = any(
        result.get(ind) is not None for ind in selected_indicators
    )
    if not any_success:
        return "E1_AllFailed"

    all_success = all(
        result.get(ind) is not None for ind in selected_indicators
    )
    failures: dict = result.get("_failures", {})
    has_failures = any(
        isinstance(v, list) and len(v) > 0
        for v in failures.values()
    )
    if not all_success or has_failures:
        return "S2_Partial"
    return "S2_Results"


def _classify_by_pillar_aggregates(result: dict) -> StateName:
    """Original M-UI-E.1 classification logic.

    Kept for backwards compatibility — fires when ``classify_result``
    is called without a ``selected_indicators`` argument. The same
    decision tree as before M-E1-INDICATOR-AWARE.
    """
    pillars_run: list[str] = result.get("_meta", {}).get("pillars_run", [])
    failures: dict = result.get("_failures", {})

    all_failed = (
        bool(pillars_run)
        and all(_pillar_has_no_scores(result, p) for p in pillars_run)
    )
    if all_failed:
        return "E1_AllFailed"

    has_failures = any(
        isinstance(v, list) and len(v) > 0
        for v in failures.values()
    )
    if has_failures:
        return "S2_Partial"

    return "S2_Results"


def _pillar_has_no_scores(result: dict, pillar: str) -> bool:
    """Return True when the pillar's aggregate follow-up priority is
    ``None`` — the orchestrator writes ``None`` for every key under a
    pillar that hit a ``PillarComputeError``.
    """
    key = _PILLAR_AGGREGATE_KEYS.get(pillar)
    if key is None:
        return False
    return result.get(key) is None


# M-RING-UX
# ---------------------------------------------------------------------------
# E1 reason detection
# ---------------------------------------------------------------------------

# Codes that mean "an asset returned no usable pixels for this AOI" —
# distinct from background_ring_no_data which is about the §0.2 ring,
# not the site buffer. Kept in sync with the prose dicts in
# c4b_kpi_grid._SKIPPED_REASON_TRANSLATIONS and
# c9_partial_banner._SKIPPED_REASON_PROSE.
_NO_DATA_CODES: frozenset[str] = frozenset({
    "no_s5p_pixels",
    "no_cams_pixels",
    "no_maiac_pixels",
    "no_viirs_pixels",
    "no_dw_pixels",
    "no_hansen_pixels",
    "no_modis_pixels",
    "out_of_coverage",
})

E1Reason = Literal["ring_empty", "no_data_at_all", "unknown"]


def detect_e1_reason(result: dict | None) -> E1Reason:
    """Inspect an E1_AllFailed payload to decide which explanation to render.

    The engine's defensive skip paths (M-OCEAN-RING / M-AIR-GHG-DEFENSIVE /
    M-NATURE-DEFENSIVE) leave per-indicator ``skipped_reason`` codes on
    each ``_provenance.<pillar>.<indicator>`` block. When every selected
    indicator skipped, the orchestrator hands E1 a payload whose pillar
    follow-up priorities are all ``None`` but whose provenance blocks
    still carry the cause. This helper categorises the population of
    those codes into one of three buckets:

    - ``"ring_empty"`` — every skipped indicator carries
      ``background_ring_no_data``. Typical cause: a very large AOI where
      the §0.2 background ring lies entirely over water or over a
      sparse-coverage region (Acre, mid-ocean, polar). The E1 page
      renders a methodology-aware explanation with actionable
      suggestions (smaller buffer, switch to Free Coordinates).
    - ``"no_data_at_all"`` — every skipped indicator carries one of the
      ``_NO_DATA_CODES`` (or a mix of those with
      ``background_ring_no_data``). Typical cause: AOI over water, or
      time window outside an asset's coverage.
    - ``"unknown"`` — the payload doesn't fit either bucket (no
      provenance blocks, mixed with non-skip codes, etc.). The page
      falls back to the generic "all pillars returned no data" message.

    The implementation walks the flat dot-delimited keys directly —
    provenance is stored as ``_provenance.<pillar>.<indicator>`` rather
    than nested, so a simple ``startswith`` filter is enough.
    """
    if not result:
        return "unknown"

    skipped_reasons: list[str] = []
    for key, value in result.items():
        if not isinstance(key, str):
            continue
        if not key.startswith("_provenance."):
            continue
        if not isinstance(value, dict):
            continue
        reason = value.get("skipped_reason")
        if reason:
            skipped_reasons.append(reason)

    if not skipped_reasons:
        return "unknown"

    if all(r == "background_ring_no_data" for r in skipped_reasons):
        return "ring_empty"

    catch_all = _NO_DATA_CODES | {"background_ring_no_data"}
    if all(r in catch_all for r in skipped_reasons):
        return "no_data_at_all"

    return "unknown"
