"""Traffic-light band + confidence-dot helpers (M-UI-E.2).

Pure-Python, no Streamlit. Locks the visual scoring grammar to the same
``TRAFFIC_LIGHT_THRESHOLDS`` used by ``engine/verbal_summary.py``, so the
chip colours rendered in C3 and the prose buckets selected by C7 cannot
disagree at the boundaries.

Authority: ``docs/Wireframes_All_v4.md`` Appendix C.1 (bands) and C.2
(confidence dot glyphs).
"""

# M-UI-E.2
from __future__ import annotations

from typing import Literal

from engine.constants import TRAFFIC_LIGHT_THRESHOLDS


Band = Literal["high", "moderate", "low"]


def band_for_score(score: float | None) -> Band | None:
    """Map a 0–1 score to its tertile band.

    Per Appendix C.1, the boundaries 0.33 and 0.66 land in the higher-
    severity band (``>=`` comparisons). ``None`` propagates as ``None``
    so callers can render a neutral chip without a sentinel score.
    """
    if score is None:
        return None
    low_thr, high_thr = TRAFFIC_LIGHT_THRESHOLDS  # (0.33, 0.66)
    if score >= high_thr:
        return "high"
    if score >= low_thr:
        return "moderate"
    return "low"


def confidence_glyph(score: float | None) -> str:
    """Map a 0–1 confidence score to its dot glyph (●/◐/○).

    Same threshold table as ``band_for_score`` (Appendix C.2). ``None``
    renders as the empty dot (lowest-confidence affordance).
    """
    band = band_for_score(score)
    return {"high": "●", "moderate": "◐", "low": "○", None: "○"}[band]


def band_colour(band: Band | None) -> str:
    """Map a band to its CSS hex. ``None`` → neutral grey.

    Palette chosen for colour-blind safety. Hue must never be the sole
    semantic carrier — pair with ``band_label`` per Appendix C.4.
    """
    return {
        "high":     "#dc2626",  # red-600
        "moderate": "#f59e0b",  # amber-500
        "low":      "#16a34a",  # green-600
        None:       "#9ca3af",  # grey-400
    }[band]


def band_label(band: Band | None) -> str:
    """Map a band to its textual label.

    Required accompaniment to the colour per Appendix C.4 (accessibility:
    hue is never the sole semantic carrier). ``None`` → ``"—"``.
    """
    return {"high": "High", "moderate": "Moderate", "low": "Low", None: "—"}[band]
