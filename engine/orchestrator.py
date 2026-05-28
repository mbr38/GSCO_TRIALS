"""Cross-pillar orchestrator (Milestones 5c + 5b — Air + GHG + Nature).

`ScreeningRun` is the only entry point the UI result pages (P-05+) should
call. It takes the AOI + selected indicators + time range, runs each
pillar's `run_pillar` function, computes the cross-pillar composite + the
cross-pillar confidence per IC_v4 §4, namespaces failures into one
canonical structure, and attaches a `_meta` block.

Per Engine_Module_Skeleton_v1.md §3 the orchestrator is the only stateful
class in the engine — pillar modules stay stateless.

Cross-pillar payload flow (M5c): the orchestrator threads its accumulated
payload through each pillar's `run_pillar` via the `accumulated_payload`
kwarg. GHG uses it to borrow Air's `industrial_combustion_proxy` and
`smoke_dust_regional_transport`; pillars without borrows simply ignore it.

Future:
- `TrendRun` (mode="trend") subclass — deferred.
- `PrioritisationBatch` for P-08 — deferred.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from engine import air, ghg, nature
from engine.core.fallback import FallbackContext
from engine.exceptions import IndicatorComputeError, PillarComputeError


# Mapping of pillar name → run_pillar callable. Iteration order = execution
# order (Python 3.7+ dict ordering). CLAUDE.md §7 fixes the order as
# air → ghg → nature; GHG must run after Air so its cross-pillar borrows
# resolve via the accumulated payload.
# Note: function refs are captured at import time. To mock a pillar in tests,
# use monkeypatch.setitem(orchestrator._PILLARS, "<pillar>", ...) rather than
# monkeypatch.setattr on engine.<pillar>.run_pillar.
_PILLARS: dict[str, Callable[..., dict]] = {
    "air":    air.run_pillar,
    "ghg":    ghg.run_pillar,
    "nature": nature.run_pillar,
}

# IC_v4 §4 — composite score is the equal-weighted mean of per-pillar
# follow-up priorities across the pillars that produced one.
_PILLAR_PRIORITY_IDS: tuple[str, ...] = (
    "air.audit_followup_priority",
    "ghg.audit_followup_priority",
    "nature.followup_priority",
)

# IC_v4 §4 — composite confidence is the minimum across the pillars that
# produced a confidence aggregate.
_PILLAR_CONFIDENCE_IDS: tuple[str, ...] = (
    # M-ATTRIB-A1 (AT16 / AT13): renamed measurement-quality IDs.
    "air.measurement_quality_score",
    "ghg.data_quality_attribution",
    "nature.measurement_quality",
)


class ScreeningRun:
    """One screening computation for a single AOI.

    Used by P-05 (single-supplier screening) and reused by P-08's batch loop.
    Always operates in `mode="screening"` — `TrendRun` (deferred) will
    subclass this with `mode="trend"`.
    """

    def __init__(
        self,
        aoi: dict,
        selected_indicators: set[str],
        time_range: tuple[str, str],
        ee_client,
        centre_metadata: dict,
        *,
        strict_audit_mode: bool = False,
        climatology_fixture: dict | None = None,
        temporal_fallback_strategy: str = "sppy",
    ) -> None:
        self.aoi = aoi
        self.selected_indicators = selected_indicators
        self.time_range = time_range
        self.ee_client = ee_client
        self.centre_metadata = centre_metadata
        # M-FALLBACK-A1 — fallbacks are ON by default (FB6); the P-07 "Strict
        # audit mode" toggle flips `strict_audit_mode`, which makes the
        # context inert (six_step takes its no-fallback path). The context is
        # threaded to every pillar's run_pillar.
        self.strict_audit_mode = strict_audit_mode
        self.fallback = FallbackContext(
            strict_audit_mode=strict_audit_mode,
            temporal_fallback_strategy=temporal_fallback_strategy,
            climatology_fixture=climatology_fixture,
        )
        self.payload: dict = {}
        # Per-pillar `_failures` lists, captured as each pillar returns.
        # Kept separate from `self.payload` because pillars all write to
        # the same `_failures` key (any one would overwrite the others).
        self.indicator_failures: dict[str, list] = {}
        self.pillar_wide_failures: dict[str, dict] = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def run(self) -> dict:
        """Run every available pillar and assemble the unified result payload."""
        for pillar_name, run_pillar_fn in _PILLARS.items():
            self._run_one_pillar(pillar_name, run_pillar_fn)
        self._compute_composite()
        self._compute_composite_confidence()
        self._consolidate_failures()
        return self._full_result()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _pillar_selection(self, pillar_name: str) -> set[str]:
        """Subset of `self.selected_indicators` that begins with `<pillar_name>.`."""
        prefix = f"{pillar_name}."
        return {i for i in self.selected_indicators if i.startswith(prefix)}

    def _run_one_pillar(
        self,
        pillar: str,
        run_pillar_fn: Callable[..., dict],
    ) -> None:
        """Run one pillar, catching pillar-wide failures so the orchestrator
        keeps going. Per-indicator failures (the pillar's `_failures` list)
        are popped out of the return dict and stashed per-pillar so the next
        pillar doesn't overwrite them when it updates `self.payload`.

        Threads `accumulated_payload=self.payload` so GHG can read Air's
        borrowed sub-aggregate values when it runs second.
        """
        try:
            result = run_pillar_fn(
                aoi=self.aoi,
                time_range=self.time_range,
                mode="screening",
                selected_indicators=self._pillar_selection(pillar),
                ee_client=self.ee_client,
                accumulated_payload=self.payload,
                fallback=self.fallback,
            )
        except PillarComputeError as err:
            self.pillar_wide_failures[pillar] = {
                "indicator_ids": err.indicator_ids,
                "reason":        err.reason,
            }
            for ind_id in err.indicator_ids:
                self.payload[ind_id] = None
        else:
            # Pop the pillar's `_failures` list out before merging into
            # `self.payload` — otherwise the next pillar's `_failures`
            # (or lack thereof) would overwrite this one's.
            failures = result.pop("_failures", None)
            if failures is not None:
                self.indicator_failures[pillar] = failures
            self.payload.update(result)

    def _compute_composite(self) -> None:
        """IC_v4 §4 — equal-weighted mean of per-pillar follow-up priorities.

        M-FOLLOWUP-FALLBACK: strict-None propagation. If any pillar's
        priority is None, the composite is None. The prior survivor-mean
        behaviour produced misleading composite scores when a pillar
        failed entirely (Rio de Janeiro region screening saw composite
        = nature.followup_priority = nature.measurement_quality = 0.858
        because Air and GHG priorities were None and the mean was
        computed over the one survivor).
        """
        self.payload["composite.overall_screening"] = compute_composite_overall(
            self.payload,
        )

    def _compute_composite_confidence(self) -> None:
        """IC_v4 §4 — minimum of the per-pillar confidence aggregates.

        M-FOLLOWUP-FALLBACK: strict-None propagation. Same rationale as
        ``_compute_composite`` — a missing pillar confidence is a real
        gap, not a value to silently drop from the min. The prior
        "survivor min" behaviour propagated a single pillar's confidence
        as the composite, which is misleading when the others failed.
        """
        self.payload["composite.confidence"] = compute_composite_confidence(
            self.payload,
        )

    def _consolidate_failures(self) -> None:
        """Re-key per-pillar `_failures` lists into one namespaced structure.

        After consolidation, `payload["_failures"]["<pillar>"]` is a list of
        failure dicts. Per-indicator failures (captured per-pillar in
        `self.indicator_failures` during `_run_one_pillar`) keep their
        original shape. Pillar-wide failures (caught `PillarComputeError`s)
        get appended with a `"type": "pillar_wide"` marker so the UI can
        tell them apart.
        """
        all_failures: dict = {}
        # Per-indicator failures, one entry per pillar.
        for pillar, failure_list in self.indicator_failures.items():
            all_failures[pillar] = list(failure_list)
        # Pillar-wide failures (PillarComputeError caught in _run_one_pillar).
        for pillar, entry in self.pillar_wide_failures.items():
            all_failures.setdefault(pillar, []).append({
                "type": "pillar_wide",
                **entry,
            })
        if all_failures:
            self.payload["_failures"] = all_failures

    def _full_result(self) -> dict:
        """Wrap the payload with a `_meta` block before returning."""
        return {
            **self.payload,
            "_meta": {
                "aoi":                 self.aoi,
                "centre_metadata":     self.centre_metadata,
                "time_range":          self.time_range,
                "mode":                "screening",
                "computed_at":         datetime.now(timezone.utc).isoformat(),
                "selected_indicators": sorted(self.selected_indicators),
                "pillars_run":         list(_PILLARS.keys()),
            },
        }


# ---------------------------------------------------------------------------
# Composite helpers (IC_v4 §4) — module-level so the patch path reuses them
# ---------------------------------------------------------------------------

def compute_composite_overall(payload: dict) -> float | None:
    """Equal-weighted mean of the per-pillar follow-up priorities, or None
    if any pillar's priority is missing (strict-None, M-FOLLOWUP-FALLBACK)."""
    values = [payload.get(k) for k in _PILLAR_PRIORITY_IDS]
    if any(v is None for v in values):
        return None
    return sum(values) / len(values)


def compute_composite_confidence(payload: dict) -> float | None:
    """Minimum of the per-pillar confidence aggregates, or None if any is
    missing (strict-None, M-FOLLOWUP-FALLBACK)."""
    values = [payload.get(k) for k in _PILLAR_CONFIDENCE_IDS]
    if any(v is None for v in values):
        return None
    return min(values)


# ---------------------------------------------------------------------------
# M-FALLBACK-A1 §5.3 / FB18 — patch-on-existing single-indicator re-screening
# ---------------------------------------------------------------------------

# Indicators that flow through six_step and can therefore be retried with a
# fallback (FB10 climatology scope + the SPPY-eligible NDVI). co2 (ODIAC) and
# the static Nature reference indicators don't use six_step → no fallback.
_PATCHABLE_GHG: frozenset[str] = frozenset({"ghg.ch4", "ghg.viirs"})
_PATCHABLE_NATURE: frozenset[str] = frozenset({"nature.ndvi"})


def _pillar_subset(selected: set[str], pillar: str) -> set[str]:
    prefix = f"{pillar}."
    return {i for i in selected if i.startswith(prefix)}


def _recompute_one_indicator(
    indicator_id: str,
    *,
    aoi: dict,
    time_range: tuple[str, str],
    ee_client,
    fallback: FallbackContext,
) -> dict | None:
    """Recompute one fallback-eligible indicator's snapshot, or None if it's
    not patchable / still fails even with the fallback."""
    parts = indicator_id.split(".")
    if len(parts) < 2:
        return None
    pillar, name = parts[0], parts[1]
    try:
        if pillar == "air" and name in air.AIR_POLLUTANT_CONFIG:
            return air.compute_pollutant_snapshot(
                aoi, name, time_range, "screening", ee_client, fallback=fallback,
            )
        if indicator_id in _PATCHABLE_GHG:
            return ghg.compute_ghg_indicator_snapshot(
                aoi, name, time_range, "screening", ee_client, fallback=fallback,
            )
        if indicator_id in _PATCHABLE_NATURE:
            return nature.compute_ndvi_condition(
                aoi, time_range, "screening", ee_client, fallback=fallback,
            )
    except (IndicatorComputeError,):
        # Still no data even with the fallback — leave the existing (None)
        # entries untouched; the tile stays failed.
        return None
    return None


def patch_indicators(
    payload: dict,
    *,
    aoi: dict,
    indicator_ids: set[str],
    selected_indicators: set[str],
    time_range: tuple[str, str],
    ee_client,
    strategy: str = "sppy",
) -> dict:
    """Re-screen only `indicator_ids` on an existing `payload` with a forced
    fallback strategy, preserving every other entry (FB18 patch-on-existing).

    Recomputes each target indicator's snapshot (with the SPPY or
    sliding-lookback fallback forced on), splices it into a copy of the
    payload, then refreshes the affected pillars' aggregates and the
    cross-pillar composite so the screening stays internally consistent (R7).
    Indicators that still fail even with the fallback are left as-is.

    `indicator_ids` are base ids (e.g. ``"air.no2"``). `strategy` is
    ``"sppy"`` or ``"sliding_lookback"``. Returns the patched payload (the
    input is not mutated).
    """
    result = dict(payload)
    fallback = FallbackContext(
        strict_audit_mode=False, temporal_fallback_strategy=strategy,
    )

    affected_pillars: set[str] = set()
    for ind_id in indicator_ids:
        snapshot = _recompute_one_indicator(
            ind_id, aoi=aoi, time_range=time_range,
            ee_client=ee_client, fallback=fallback,
        )
        if snapshot is not None:
            result.update(snapshot)
            affected_pillars.add(ind_id.split(".")[0])

    # Refresh the affected pillars' aggregates (pure — no re-fetch of the
    # other indicators), then the composite.
    if "air" in affected_pillars:
        air.recompute_air_aggregates(
            result, _pillar_subset(selected_indicators, "air"), "screening",
        )
    if "ghg" in affected_pillars:
        ghg.recompute_ghg_aggregates(
            result, _pillar_subset(selected_indicators, "ghg"), "screening", aoi,
        )
    if "nature" in affected_pillars:
        nature.recompute_nature_aggregates(result, aoi, "screening")

    result["composite.overall_screening"] = compute_composite_overall(result)
    result["composite.confidence"] = compute_composite_confidence(result)
    return result
