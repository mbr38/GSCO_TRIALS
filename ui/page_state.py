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


def classify_result(result: dict) -> StateName:
    """Map an engine result payload to the next state name.

    Decision order:

    1. **All-failed** — every pillar listed in ``_meta.pillars_run``
       produced no aggregate score (the per-pillar follow-up priority
       is ``None``). Returns ``E1_AllFailed``. Requires
       ``pillars_run`` to be non-empty; an empty ``pillars_run`` never
       fires this branch (no pillars ran, so none failed).
    2. **Partial** — at least one pillar appears in ``_failures`` with
       a non-empty failure list. Returns ``S2_Partial``.
    3. Otherwise full success. Returns ``S2_Results``.
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
