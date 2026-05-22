"""P-11 JSON export (M-P11.4).

Report-wrapped JSON: metadata (title, template, generated_at) plus
the underlying source payloads. Self-describing for downstream
consumers — distinguishable from raw screening output by the
``report`` top-level key.
"""

# M-P11.4
from __future__ import annotations

import json
from datetime import datetime, timezone


def render_json(state, sources: list[dict], template) -> str:
    """Build a JSON string for the report.

    The shape is:

    .. code-block:: python

        {
          "report":  { ... metadata ... },
          "sources": [ { id, name, type, date_saved, payload }, ... ]
        }

    Per-source ``payload`` is shaped by source type — screening
    carries ``screening_setup`` + ``payload``; prioritisation carries
    ``prioritisation_setup`` + ``supplier_results`` + ``summary``.
    """
    report = {
        "report": {
            "title":         state.title or "Untitled report",
            "template_id":   state.template_id,
            "template_name": template.display_name if template else None,
            "generated_at":  datetime.now(timezone.utc).isoformat(),
            "notes":         (state.notes or None),
            "source_count":  len(sources),
        },
        "sources": [
            {
                "id":         s.get("id"),
                "name":       s.get("name"),
                "type":       s.get("type"),
                "date_saved": s.get("date_saved"),
                "payload":    _payload_for(s),
            }
            for s in sources
        ],
    }
    return json.dumps(report, indent=2, default=str)


def _payload_for(src: dict):
    """Extract the right payload fields by source type."""
    if src.get("type") == "prioritisation":
        return {
            "prioritisation_setup": src.get("prioritisation_setup"),
            "supplier_results":     src.get("supplier_results", []),
            "summary":              src.get("summary"),
        }
    return {
        "screening_setup": src.get("screening_setup"),
        "payload":         src.get("payload"),
    }
