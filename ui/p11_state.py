"""Reports page state machine (M-P11.1).

States for v1:
  S1_TemplateAndSource : pick template + sources, click Preview.
  S2_Preview           : (M-P11.2) review the rendered preview.
  S3_Export            : (M-P11.3 / .4) generate + download file.
  E1_Failed            : (M-P11.3+) export generation failed.

Only S1 is wired up in M-P11.1; the others are scaffolded with
placeholder renderers that surface "lands in M-P11.X" messages.
The dispatch shape is locked now so M-P11.2 can plug in cleanly
without restructuring the page.
"""

# M-P11.1
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ReportStateKind(str, Enum):
    S1_TEMPLATE_AND_SOURCE = "S1_TemplateAndSource"
    S2_PREVIEW             = "S2_Preview"
    S3_EXPORT              = "S3_Export"
    E1_FAILED              = "E1_Failed"


@dataclass
class ReportState:
    """Lives in ``st.session_state.report_state``."""
    kind:        ReportStateKind = ReportStateKind.S1_TEMPLATE_AND_SOURCE
    template_id: str | None      = None
    source_ids:  list[str]       = field(default_factory=list)
    title:       str             = ""
    notes:       str             = ""
    error:       str | None      = None
    # M-REPORT-A1: the active user type, captured at S1. Threaded into the
    # assembler so the General report's dual framing (RT8) and the ESRS layer
    # (RT4) can branch at render time off this — not off two separate template
    # IDs. Default "" keeps pre-existing state objects valid on reload.
    user_type:   str             = ""
    # M-REPORT-COOP: the user-chosen pillar for the supplier cooperation report
    # (that template renders one pillar, selected at S1 rather than fixed by the
    # template). ``None`` for every other template — the assembler only applies
    # it to the cooperation template, so a stale value can't leak elsewhere.
    pillar:      str | None      = None


# M-P11.4
def route_to_p11_with_source(session_state, source_id: str) -> None:
    """Pre-populate P-11's state with a source pre-selected.

    Pure state-mutator — does *not* call ``st.switch_page``; callers
    do that after invoking this helper. Splitting the two keeps the
    state mutation unit-testable against a plain dict.

    Behaviour:
      - Initialises ``report_state`` if missing.
      - Resets ``kind`` to ``S1_TEMPLATE_AND_SOURCE`` so the user
        always lands in template selection (even if a prior session
        had progressed to S2 / S3).
      - Adds the source ID to ``source_ids`` if not already present;
        never duplicates.
    """
    report_state = session_state.get("report_state") or ReportState()
    report_state.kind = ReportStateKind.S1_TEMPLATE_AND_SOURCE
    if source_id not in report_state.source_ids:
        report_state.source_ids = [*report_state.source_ids, source_id]
    session_state["report_state"] = report_state
