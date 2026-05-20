"""Partial-selection caveat banner (M-PARTIAL-CAVEAT).

Shown on P-05 when the user ran fewer than all 19 indicators. Explains
that pillar scores and the composite priority are computed from
selected indicators only — not a full pillar assessment.

Distinct from C9 (partial-coverage banner): C9 fires when selected
indicators *failed* during the run; this banner fires when the user
*chose* to run a subset. Both can fire on the same page.

Authority: locked Q1 (compute against selected + caveat banner).
"""

# M-PARTIAL-CAVEAT
from __future__ import annotations

import streamlit as st

from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS


def render_partial_caveat(selected_indicators: set[str]) -> None:
    """Render the caveat banner when the user ran a partial selection.

    No-op when the user ran the full canonical set.
    """
    total = len(ALL_INDICATOR_IDS)
    selected_count = len(selected_indicators & set(ALL_INDICATOR_IDS))
    if selected_count >= total:
        return

    st.info(
        f"**Partial screening** — pillar scores and the composite "
        f"priority below are computed from the **{selected_count} of "
        f"{total} indicators** you selected. They reflect what was "
        f"measured, not a full pillar assessment.",
        icon="ℹ️",
    )
