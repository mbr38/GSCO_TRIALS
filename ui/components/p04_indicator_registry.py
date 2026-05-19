"""P-04 indicator registry (M-P04).

Single source of truth for the 19 indicators P-04 exposes to the user.
Each entry pairs a canonical engine ID (the same string that
``engine.orchestrator.ScreeningRun(selected_indicators=...)`` accepts)
with a user-facing display name and a pillar grouping.

The IDs here are a curated *subset* of ``engine.ids.ALL_INDICATOR_IDS``
— the engine emits many keys per indicator (`.site`, `.anomaly`,
`.z`, `.score`, …), but P-04 only ever surfaces the one ID per
indicator that the user can usefully *select*. The cross-reference
test in ``tests/test_p04_indicator_registry.py`` asserts each ID here
is valid per ``engine.ids.is_valid_id``.
"""

# M-P04
from __future__ import annotations


# Ordered per pillar. Within each pillar, the order matches the
# precedence used elsewhere in the UI (Air rows in C5a, GHG rows in
# C5b, Nature panels in C5c) so the visual experience reads the same
# across pages.
_INDICATORS_BY_PILLAR_RAW: dict[str, list[tuple[str, str]]] = {
    "air": [
        ("air.no2.score",  "NO₂"),
        ("air.so2.score",  "SO₂"),
        ("air.co.score",   "CO"),
        ("air.hcho.score", "HCHO"),
        ("air.pm25.score", "PM₂.₅"),
        ("air.pm10.score", "PM₁₀"),
        ("air.o3.score",   "O₃"),
        ("air.aai.score",  "AAI (Aerosol Absorbing Index)"),
        ("air.aod.score",  "AOD (Aerosol Optical Depth)"),
    ],
    "ghg": [
        ("ghg.ch4.score",   "CH₄"),
        ("ghg.co2.score",   "CO₂ (ODIAC)"),
        ("ghg.viirs.score", "Nighttime lights (VIIRS)"),
    ],
    "nature": [
        ("nature.kba.proximity_score",     "Key Biodiversity Areas"),
        ("nature.dw.trees_pct",            "Dynamic World land cover"),
        ("nature.habitat.natural_loss_ha", "Habitat conversion"),
        ("nature.forest_loss.ha",          "Forest loss (Hansen)"),
        ("nature.ndvi.score",              "NDVI (vegetation index)"),
        ("nature.water.area_now_ha",       "Water / flooded vegetation"),
        ("nature.recovery.score",          "Vegetation recovery"),
    ],
}

INDICATORS_BY_PILLAR: dict[str, list[str]] = {
    pillar: [ind_id for ind_id, _ in items]
    for pillar, items in _INDICATORS_BY_PILLAR_RAW.items()
}

ALL_INDICATOR_IDS: tuple[str, ...] = tuple(
    ind_id
    for items in _INDICATORS_BY_PILLAR_RAW.values()
    for ind_id, _ in items
)

_DISPLAY_NAMES: dict[str, str] = {
    ind_id: name
    for items in _INDICATORS_BY_PILLAR_RAW.values()
    for ind_id, name in items
}


def display_name(indicator_id: str) -> str:
    """Look up the user-facing label for a canonical indicator ID.

    Unknown IDs fall back to the raw string — callers can render
    arbitrary engine IDs without crashing if the registry hasn't yet
    caught up.
    """
    return _DISPLAY_NAMES.get(indicator_id, indicator_id)
