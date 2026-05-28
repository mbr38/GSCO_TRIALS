"""M-ATTRIB-A1 dual-emit reader shim (Q-AT-3, 1-milestone window).

Holds the renamed-aggregate-ID fallback map and a tiny `payload_read`
helper. The engine emits both the new and the legacy IDs for one
milestone, so the UI should read the new ID **and** fall back to the
legacy ID — that way saved analyses generated *before* M-ATTRIB-A1
(which have only the legacy IDs) still render the pillar
confidence values correctly.

Without this shim the C3 chips, C5 headlines, C5 formula breakdown
and C6 confidence panel would render "No data" / "—" for the
Air and Nature pillar measurement-quality scores when an old saved
analysis is loaded, even though the legacy `air.attribution_confidence_score`
and `nature.quality_attribution` values are sitting right there in
the payload.

Remove this module when the legacy ID emit is removed next milestone
(M-ATTRIB-A1 spec §4.6 / Q-AT-3).
"""

from __future__ import annotations

# Renamed-aggregate IDs only. Per-indicator confidence IDs
# (`nature.habitat.confidence`, `air.no2.confidence`, etc.) were not
# renamed and are not in this map.
_LEGACY_ID_FALLBACK: dict[str, str] = {
    "air.measurement_quality_score": "air.attribution_confidence_score",
    "nature.measurement_quality":    "nature.quality_attribution",
}


def payload_read(payload: dict, key: str):
    """Read ``key`` from ``payload``; if absent and ``key`` was renamed
    by M-ATTRIB-A1, fall back to the legacy ID. Returns ``None`` when
    neither is present.
    """
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    if value is None and key in _LEGACY_ID_FALLBACK:
        return payload.get(_LEGACY_ID_FALLBACK[key])
    return value
