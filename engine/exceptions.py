"""Engine error hierarchy per docs/Engine_Module_Skeleton_v1.md §6.

`IndicatorComputeError` — single-indicator failure (recoverable: the
orchestrator marks that indicator's IDs as missing in the payload).
`PillarComputeError` — non-recoverable pillar-wide failure (the orchestrator
catches this to render the P-05 S2_Partial UI state).
"""

from __future__ import annotations


class IndicatorComputeError(Exception):
    """Raised when a single indicator can't be computed.

    Typical cause: the site or background buffer has zero valid pixels for the
    requested band/time-range. The orchestrator catches this internally where
    graceful degradation is possible (e.g. CAMS → AAI fallback per IC_v4 §1.2).
    """

    def __init__(self, indicator_id: str, reason: str) -> None:
        super().__init__(f"{indicator_id}: {reason}")
        self.indicator_id = indicator_id
        self.reason = reason


# M-OCEAN-RING
class BackgroundRingNoDataError(IndicatorComputeError):
    """Raised when the §0.2 background ring reduces to no usable pixels.

    Specialises ``IndicatorComputeError`` so existing ``except
    IndicatorComputeError`` blocks still trip (preserving the per-indicator
    failure path for callers that don't care about the distinction). Pillar
    dispatchers (``engine.air.run_pillar`` / ``engine.ghg.run_pillar``)
    catch this specific subclass *before* the generic handler so they can
    emit a canonical "skipped" payload — provenance with
    ``skipped_reason="background_ring_no_data"`` — instead of an entry in
    ``_failures``. Surfaces in C9 (partial banner) and C4b (failed tile)
    with a user-actionable explanation.

    Typical trigger: coastal AOIs where the ring's outer extent lands
    over water (e.g. Rio de Janeiro state at 281 km buffer → 562 km ring,
    largely Atlantic Ocean → reduceRegion returns NaN).
    """
    # No new fields; the subclass is the signal.


# M-AIR-GHG-DEFENSIVE
class SiteBufferNoDataError(IndicatorComputeError):
    """Raised when the §0.2 site buffer reduces to no usable pixels.

    Parallel to ``BackgroundRingNoDataError`` but for the site half of
    the six-step pipeline. Pillar dispatchers catch this subclass before
    the generic handler so they can emit a canonical "skipped" payload
    with an asset-family-specific ``skipped_reason`` (e.g.
    ``no_s5p_pixels``, ``no_cams_pixels``) instead of routing the
    indicator into ``_failures`` with a stack-trace-style message.

    Typical trigger: deep-Amazon AOIs (e.g. Acre) where Sentinel-5P has
    no usable overpasses in the screening window due to persistent
    cloud cover; or sparse-coverage assets over arbitrary AOIs.

    The pixel-size pre-checks in the pillar modules (buffer smaller
    than native pixel) still raise plain ``IndicatorComputeError`` —
    that's a user-input issue, not a coverage statement, so it goes
    into ``_failures`` rather than the skipped path.
    """
    # No new fields; the subclass is the signal.


class PillarComputeError(Exception):
    """Raised when a whole pillar can't be computed.

    Carries `indicator_ids` so the orchestrator can mark every affected ID as
    `None` in the payload and surface them in the failures list.
    """

    def __init__(self, pillar: str, indicator_ids: list[str], reason: str) -> None:
        super().__init__(f"pillar {pillar}: {reason}")
        self.pillar = pillar
        self.indicator_ids = indicator_ids
        self.reason = reason
