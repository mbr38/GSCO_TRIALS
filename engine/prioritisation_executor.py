"""Sequential batch executor (M-P08.1).

Walks suppliers in setup order, calls ScreeningRun per supplier,
records each outcome. Catches per-supplier exceptions (Q2: continue
on errors). Checks state.cancelled between suppliers (Q3).

Streamlit reruns between iterations are NOT used — that would lose
in-progress state. Instead, the executor blocks the page until
the batch completes (or is cancelled). The callback updates the
session state and triggers a partial Streamlit redraw via the
caller's container handles.
"""

# M-P08.1
from __future__ import annotations

from typing import Callable

from engine.orchestrator import ScreeningRun
from ui.prioritisation_state import (
    PrioritisationState,
    PrioritisationStateKind,
    SupplierResult,
)


# Type alias for the progress callback: (latest_result, done, total).
ProgressCallback = Callable[[SupplierResult, int, int], None]


def run_batch(
    state: PrioritisationState,
    setup: dict,
    on_progress: ProgressCallback,
) -> None:
    """Execute the batch sequentially.

    Args:
        state: mutable PrioritisationState; will be updated in place.
        setup: the locked-in setup snapshot (suppliers, radius_km,
            time_range, indicators).
        on_progress: callback invoked after each supplier completes
            with (latest_result, completed_count, total_count). The
            caller uses this to trigger UI redraws.

    Cancellation: check ``state.cancelled`` between suppliers. If
    set, mark remaining suppliers as ``cancelled`` status with no
    result, transition to S3_RESULTS, return.
    """
    suppliers   = setup["suppliers"]
    radius_km   = setup["radius_km"]
    time_range  = tuple(setup["time_range"])
    indicators  = set(setup["indicators"])
    # M-FALLBACK-A1 §5.1 — P-07 "Strict audit mode" toggle. Absent in
    # pre-milestone / legacy setups → defaults False (fallbacks ON, FB16).
    strict_audit_mode = bool(setup.get("strict_audit_mode", False))

    state.total_count = len(suppliers)

    if not suppliers:
        # Defensive — caller should have routed to E1 already.
        state.kind = PrioritisationStateKind.S3_RESULTS
        return

    for i, supplier in enumerate(suppliers):
        # Cancel check between suppliers. The current supplier hasn't
        # started yet, so mark it + the rest as cancelled.
        if state.cancelled:
            for remaining in suppliers[i:]:
                state.supplier_results.append(SupplierResult(
                    supplier_id=remaining["id"],
                    name=remaining["name"],
                    lat=remaining["lat"],
                    lon=remaining["lon"],
                    source=remaining["source"],
                    status="cancelled",
                ))
            state.kind = PrioritisationStateKind.S3_RESULTS
            return

        # Run one supplier. Region suppliers (Regional analysis) carry their
        # own area-matched radius; node / ad-hoc suppliers fall back to the
        # shared page-level radius.
        try:
            supplier_radius = supplier.get("radius_km") or radius_km
            aoi = {
                "centre":    {"lat": supplier["lat"], "lon": supplier["lon"]},
                "radius_km": supplier_radius,
            }
            centre_metadata = {
                "source":    f"P-08 batch · {supplier['source']}",
                "node_id":   supplier["id"],
                "node_name": supplier["name"],
            }
            result = ScreeningRun(
                aoi=aoi,
                selected_indicators=indicators,
                time_range=time_range,
                ee_client=None,
                centre_metadata=centre_metadata,
                strict_audit_mode=strict_audit_mode,
            ).run()
            # M-E1-INDICATOR-AWARE: thread the user's selection so a
            # subset run with real per-indicator data doesn't get
            # flagged "failed" when pillar aggregates go None.
            status = _classify_per_supplier(result, indicators)
            outcome = SupplierResult(
                supplier_id=supplier["id"],
                name=supplier["name"],
                lat=supplier["lat"],
                lon=supplier["lon"],
                source=supplier["source"],
                status=status,
                result=result,
            )
        except Exception as exc:  # noqa: BLE001
            # M-P08.1 Q2: continue on per-supplier errors. Capture the
            # error string so the UI can surface it later.
            outcome = SupplierResult(
                supplier_id=supplier["id"],
                name=supplier["name"],
                lat=supplier["lat"],
                lon=supplier["lon"],
                source=supplier["source"],
                status="failed",
                error=str(exc),
            )

        state.supplier_results.append(outcome)
        state.completed_count = i + 1
        on_progress(outcome, state.completed_count, state.total_count)

    state.kind = PrioritisationStateKind.S3_RESULTS


# M-E1-INDICATOR-AWARE
def _classify_per_supplier(
    result: dict,
    selected_indicators: list[str] | set[str] | None = None,
) -> str:
    """Map a single supplier's result to a status string.

    Selection-aware (M-E1-INDICATOR-AWARE): mirrors
    ``ui.page_state.classify_result``. "failed" means *every requested
    indicator returned None*, not "every pillar aggregate is None".

    - "failed"  : no requested indicator delivered a value
    - "partial" : at least one delivered AND either some other
                  requested indicator returned None OR a non-empty
                  ``_failures`` list is present
    - "success" : every requested indicator delivered AND nothing
                  in ``_failures`` flagged an indicator-level failure

    When ``selected_indicators`` is ``None`` or empty, falls back to
    the pre-M-E1-INDICATOR-AWARE pillar-aggregate logic so direct
    callers that don't have the setup handy still get sensible
    behaviour.
    """
    if selected_indicators:
        any_success = any(
            result.get(ind) is not None for ind in selected_indicators
        )
        if not any_success:
            return "failed"
        all_success = all(
            result.get(ind) is not None for ind in selected_indicators
        )
        if not all_success or _has_failures(result):
            return "partial"
        return "success"

    # Fallback — original pillar-aggregate logic.
    air    = result.get("air.audit_followup_priority")
    ghg    = result.get("ghg.audit_followup_priority")
    nature = result.get("nature.followup_priority")
    pillar_scores = [p for p in (air, ghg, nature) if p is not None]

    if not pillar_scores:
        return "failed"
    if _has_failures(result):
        return "partial"
    return "success"


def _has_failures(result: dict) -> bool:
    """True iff ``_failures`` holds a non-empty per-pillar failure list.

    Mirrors ``ui.page_state.classify_result`` exactly so a supplier in the
    P-08 batch gets the same status it would on the P-05 screening page.

    Provenance ``skipped_reason`` codes are deliberately NOT treated as
    failures: they mark *normal* defensive-skip outcomes (background ring
    over water, sparse coverage, reference-only indicators, etc.) that the
    screening classifier ignores. Counting them here was a divergence that
    flipped virtually every supplier to "partial" — even runs where every
    selected indicator delivered a value (M-PRIO-STATUS fix)."""
    failures = result.get("_failures", {})
    return any(
        isinstance(v, list) and len(v) > 0
        for v in failures.values()
    )
