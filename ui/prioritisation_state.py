"""Prioritisation page state machine (M-P08.1).

Mirrors ui.page_state for P-05 but with batch semantics. The single
``PrioritisationState`` lives in ``st.session_state.prioritisation_state``
and accumulates per-supplier results as the executor loops.

States:
  - S1_Configuring : page entered with no setup or with stale setup
    that doesn't match (rare; user should arrive via P-07).
  - S2_Running     : the batch is executing. results dict is being
    filled supplier-by-supplier; cancelled flag may be set.
  - S3_Results     : the batch completed normally (every supplier
    attempted; per-supplier success or failure recorded).
  - E1_Failed      : the batch couldn't even start (e.g. setup
    missing, EE init failure, no suppliers). Distinct from
    "all suppliers failed" — that's S3_Results with all failures.
"""

# M-P08.1
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PrioritisationStateKind(str, Enum):
    S1_CONFIGURING = "S1_Configuring"
    S2_RUNNING     = "S2_Running"
    S3_RESULTS     = "S3_Results"
    E1_FAILED      = "E1_Failed"


@dataclass
class SupplierResult:
    """One supplier's screening outcome."""
    supplier_id: str
    name:        str
    lat:         float
    lon:         float
    source:      str           # "supply_chain" or "ad_hoc"
    status:      str           # "success" | "partial" | "failed" | "cancelled"
    result:      dict[str, Any] | None = None  # full screening payload
    error:       str | None = None


@dataclass
class PrioritisationState:
    """Lives in st.session_state.prioritisation_state.

    The setup is the snapshot at run start (not re-read live from
    session each rerun, so the user can edit P-07 while a batch is
    running without affecting it).
    """
    kind:               PrioritisationStateKind
    setup:              dict[str, Any] | None = None
    supplier_results:   list[SupplierResult] = field(default_factory=list)
    completed_count:    int = 0
    total_count:        int = 0
    cancelled:          bool = False
    error:              str | None = None


def classify(setup: dict | None) -> PrioritisationStateKind:
    """Decide which state to start in based on session context."""
    if not setup:
        return PrioritisationStateKind.E1_FAILED
    if not setup.get("suppliers"):
        return PrioritisationStateKind.E1_FAILED
    return PrioritisationStateKind.S2_RUNNING


# M-P08.1: pillar-presence helpers (used by both the executor and the
# column-hiding logic in the renderer).
_PILLAR_PREFIXES: dict[str, str] = {
    "air":    "air.",
    "ghg":    "ghg.",
    "nature": "nature.",
}


def selected_pillars(setup: dict | None) -> set[str]:
    """Infer which pillars are represented from the indicator list.

    M-P07-PILLAR-CONSTRAINT guarantees pillar-completeness: any
    indicator from a pillar means *all* of that pillar's indicators
    are present. So we only need to test for prefix presence.
    """
    if not setup:
        return set()
    ids = setup.get("indicators", [])
    return {
        pillar for pillar, prefix in _PILLAR_PREFIXES.items()
        if any(i.startswith(prefix) for i in ids)
    }
