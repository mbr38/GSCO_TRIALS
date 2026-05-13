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
