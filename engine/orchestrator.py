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

import concurrent.futures
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from engine import air, ghg, nature
from engine.core.fallback import FallbackContext
from engine.exceptions import IndicatorComputeError, PillarComputeError


# M-PERF-PARALLEL (cause #3): Air and Nature don't read the cross-pillar
# `accumulated_payload`, so they can run concurrently. GHG must still wait
# for Air to finish — it merges Air's `industrial_combustion_proxy` and
# `smoke_dust_regional_transport` into its own payload before computing the
# combustion-proxy / fire-transport sub-aggregates. Wall-time savings ≈ the
# shorter of Air vs Nature.
_PARALLEL_STAGE_1_PILLARS: tuple[str, ...] = ("air", "nature")
_SEQUENTIAL_STAGE_2_PILLARS: tuple[str, ...] = ("ghg",)


@dataclass
class _PillarOutcome:
    """Pillar-thread result, captured for main-thread merging into self.payload.

    Either ``result`` (the pillar's return dict) is set, or ``pillar_failure``
    (a ``PillarComputeError``) is — never both. The worker thread never
    mutates ``ScreeningRun.payload``; the orchestrator merges the outcome on
    the main thread so per-pillar key writes stay single-threaded.
    """

    result: dict | None
    pillar_failure: PillarComputeError | None


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
        """Run every available pillar and assemble the unified result payload.

        M-PERF-PARALLEL (cause #3): Stage 1 runs Air + Nature concurrently
        in a `ThreadPoolExecutor` (both are independent of cross-pillar
        payload borrows); Stage 2 runs GHG sequentially after Stage 1's
        results have been merged into `self.payload` (GHG reads Air's
        sub-aggregates via `accumulated_payload`). The worker threads
        never mutate `self.payload` — outcomes are captured and merged on
        the main thread in canonical pillar order, so per-key writes stay
        single-threaded.
        """
        # Stage 1 — Air + Nature in parallel.
        stage1: dict[str, _PillarOutcome] = {}
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(_PARALLEL_STAGE_1_PILLARS),
            thread_name_prefix="gsco-pillar",
        ) as ex:
            futures = {
                ex.submit(self._call_pillar, name, _PILLARS[name]): name
                for name in _PARALLEL_STAGE_1_PILLARS
            }
            for fut in concurrent.futures.as_completed(futures):
                name = futures[fut]
                stage1[name] = fut.result()
        # Merge in canonical order so any (unlikely) shared key resolves
        # the same way as the prior sequential implementation did.
        for name in _PARALLEL_STAGE_1_PILLARS:
            self._apply_pillar_outcome(name, stage1[name])

        # Stage 2 — GHG (reads Air's keys via accumulated_payload).
        for name in _SEQUENTIAL_STAGE_2_PILLARS:
            self._run_one_pillar(name, _PILLARS[name])

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
        """Sequential dispatch — call the pillar then merge its outcome.

        Convenience wrapper used by Stage 2 (GHG). Stage 1 (Air + Nature)
        calls `_call_pillar` directly in a thread pool and applies outcomes
        via `_apply_pillar_outcome` on the main thread.
        """
        self._apply_pillar_outcome(pillar, self._call_pillar(pillar, run_pillar_fn))

    def _call_pillar(
        self,
        pillar: str,
        run_pillar_fn: Callable[..., dict],
    ) -> _PillarOutcome:
        """Invoke `run_pillar_fn` and capture its outcome.

        **Thread-safe**: never mutates `self.payload`. Returns a
        ``_PillarOutcome`` for the main thread to merge via
        ``_apply_pillar_outcome``. Passes a copy of ``self.payload`` to the
        pillar's ``accumulated_payload`` so concurrent Stage-1 pillars
        can't observe each other's partial writes (GHG-only borrows still
        work in Stage 2 because by then both Stage-1 outcomes have been
        merged).
        """
        try:
            result = run_pillar_fn(
                aoi=self.aoi,
                time_range=self.time_range,
                mode="screening",
                selected_indicators=self._pillar_selection(pillar),
                ee_client=self.ee_client,
                # Snapshot, not a live reference — keeps Stage 1 thread-safe.
                accumulated_payload=dict(self.payload),
                fallback=self.fallback,
            )
            return _PillarOutcome(result=result, pillar_failure=None)
        except PillarComputeError as err:
            return _PillarOutcome(result=None, pillar_failure=err)

    def _apply_pillar_outcome(
        self,
        pillar: str,
        outcome: _PillarOutcome,
    ) -> None:
        """Merge a pillar's outcome into `self.payload` (main thread only).

        Mirrors the previous body of `_run_one_pillar`. Per-indicator
        failures (the pillar's ``_failures`` list) are popped out of the
        return dict and stashed per-pillar so a subsequent pillar's
        ``_failures`` (or absence thereof) doesn't overwrite this one's.
        """
        if outcome.pillar_failure is not None:
            err = outcome.pillar_failure
            self.pillar_wide_failures[pillar] = {
                "indicator_ids": err.indicator_ids,
                "reason":        err.reason,
            }
            for ind_id in err.indicator_ids:
                self.payload[ind_id] = None
            return
        # Success path — outcome.result is non-None by _PillarOutcome contract.
        result = outcome.result
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
