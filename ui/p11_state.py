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
