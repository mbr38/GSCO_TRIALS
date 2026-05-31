"""Indicator Library content loader (M-P09).

Hybrid source: technical metadata from engine configs (asset ID,
native scale, data_type); narrative metadata from the JSON manifest
(definition, decision relevance, limitations, ESG alignment).

Builds one ``IndicatorCardContent`` per canonical indicator ID, using
``ui.components.p04_indicator_registry.ALL_INDICATOR_IDS`` as the
authoritative list of 19. The page renders cards from these
dataclasses.

The Nature canonical IDs don't all suffix with ``.score`` (e.g.
``nature.kba.proximity_score``, ``nature.dw.trees_pct``), so the
loader carries an explicit per-pillar map from canonical ID to the
engine config key. Keeps the source-of-truth single (the registry)
without forcing one suffix convention on the Nature configs.
"""

# M-P09
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from engine.air import AIR_POLLUTANT_CONFIG
from engine.ghg import GHG_INDICATOR_CONFIG
from engine.nature import NATURE_INDICATOR_CONFIG
from ui.components.p04_indicator_registry import (
    ALL_INDICATOR_IDS,
    INDICATORS_BY_PILLAR,
)
# M-P09-COMPOSITES: live source for derived-entry formulas.
from ui.components.c5_drilldown import (
    _AIR_FORMULA,
    _GHG_FORMULA,
    _NATURE_FORMULA,
)


_LIBRARY_JSON = Path(__file__).parent / "indicator_library.json"


@dataclass(frozen=True)
class IndicatorCardContent:
    indicator_id:       str
    pillar:             str
    sub_section:        str
    display_name:       str
    definition:         str
    decision_relevance: str
    limitations:        str
    esg_alignment:      str
    # Technical metadata — populated for raw entries; empty / None for
    # derived entries (which carry formula + weights instead).
    asset_id:           str
    native_scale_m:     float | None
    data_type:          str
    data_source:        str
    temporal_frequency: str
    # M-P09-COMPOSITES — derived-entry metadata.
    kind:               str               = "raw"   # "raw" | "derived"
    formula:            str       | None  = None
    weights:            dict      | None  = None
    # M-P09-COMPOSITES v2: component scores show a conceptual inputs
    # list (no exact weights) until M-COMPONENT-WEIGHTS lands.
    inputs:             list[str] | None  = None
    # M-UI-A2: two-sentence summary surfaced via the P-05 indicator-name
    # info popover. None when no copy has been written yet (HS12: silent
    # missing fallback — the popover is omitted rather than rendering a
    # placeholder).
    tooltip_summary:    str       | None  = None
    # M-ATTRIB-A2: attributability framing — a plain-language "what this
    # measures" note stating that severity is a site-vs-region anomaly, not
    # an absolute reading. None when no copy exists (silent-missing, like
    # tooltip_summary). AOD carries the full anchor text; the other Air
    # indicators carry a single indicator-specific line (the shared rationale
    # lives in the Air-tab callout + IC_v4 §0.7, not repeated per card).
    what_this_measures: str       | None  = None


# Canonical-ID → engine-config-key map per pillar. Air and GHG follow
# the uniform ``<pillar>.<slug>.score`` convention, so the slug *is* the
# config key. Nature's headline IDs vary per indicator — explicit map.
_NATURE_ID_TO_CONFIG_KEY: dict[str, str] = {
    "nature.kba.proximity_score":     "kba",
    "nature.dw.trees_pct":            "dw",
    "nature.habitat.natural_loss_ha": "habitat",
    "nature.forest_loss.ha":          "forest_loss",
    "nature.ndvi.score":              "ndvi",
    "nature.water.area_now_ha":       "water",
    "nature.recovery.score":          "recovery",
}

# M-P09-COMPOSITES: derived-indicator IDs added to the library on top of
# the 19 raw ALL_INDICATOR_IDS. 12 component scores (4 per pillar) + 3
# pillar aggregates + 1 composite = 16 derived. The list is built from
# the live c5_drilldown formula tuples so adding a sub-aggregate term
# there automatically grows the library — single source of truth.
_PILLAR_AGGREGATE_IDS: tuple[str, ...] = (
    "air.audit_followup_priority",
    "ghg.audit_followup_priority",
    "nature.followup_priority",
)
_COMPOSITE_ID: str = "composite.overall_screening"


def _derived_indicator_ids() -> tuple[str, ...]:
    """Build the derived-ID list at module-load: 12 component scores +
    3 pillar aggregates + 1 composite. Component scores are pulled from
    the c5_drilldown formula tuples' ``payload_key`` field — same single
    source of truth used by the formula display."""
    component_ids: list[str] = []
    for formula in (_AIR_FORMULA, _GHG_FORMULA, _NATURE_FORMULA):
        component_ids.extend(term.payload_key for term in formula)
    return tuple(component_ids) + _PILLAR_AGGREGATE_IDS + (_COMPOSITE_ID,)


DERIVED_INDICATOR_IDS: tuple[str, ...] = _derived_indicator_ids()


@cache
def load_library() -> dict[str, IndicatorCardContent]:
    """Build the indicator library at first call. Cached for reuse.

    M-P09-COMPOSITES: builds both raw entries (19 indicators with
    engine-config technical metadata) and derived entries (16 component
    scores / pillar aggregates / composite with live-sourced formulas).
    """
    manifest = _load_manifest()
    library:  dict[str, IndicatorCardContent] = {}

    for indicator_id in ALL_INDICATOR_IDS:
        library[indicator_id] = _build_raw_card(indicator_id, manifest)

    for indicator_id in DERIVED_INDICATOR_IDS:
        library[indicator_id] = _build_derived_card(indicator_id, manifest)

    return library


def _build_raw_card(indicator_id: str, manifest: dict) -> IndicatorCardContent:
    tech_meta = _technical_metadata_for(indicator_id)
    entry     = manifest.get(indicator_id) or _stub_entry(indicator_id)
    return IndicatorCardContent(
        indicator_id=indicator_id,
        pillar=_pillar_for(indicator_id),
        sub_section=entry["sub_section"],
        display_name=entry["display_name"],
        definition=entry["definition"],
        decision_relevance=entry["decision_relevance"],
        limitations=entry["limitations"],
        esg_alignment=entry["esg_alignment"],
        asset_id=tech_meta["asset_id"],
        native_scale_m=tech_meta["native_scale_m"],
        data_type=tech_meta["data_type"],
        data_source=tech_meta["data_source"],
        temporal_frequency=_describe_frequency(tech_meta["asset_id"]),
        kind="raw",
        tooltip_summary=entry.get("tooltip_summary"),
        what_this_measures=entry.get("what_this_measures"),  # M-ATTRIB-A2
    )


# M-P09-COMPOSITES
def _build_derived_card(
    indicator_id: str, manifest: dict,
) -> IndicatorCardContent:
    """Build a card for a derived (component / aggregate / composite)
    indicator. Narrative content from the manifest; formula + weights
    pulled live from c5_drilldown."""
    entry = manifest.get(indicator_id) or _stub_entry(indicator_id)
    live  = _resolve_live_formula(indicator_id)
    pillar = entry.get("pillar") or _pillar_for(indicator_id)
    return IndicatorCardContent(
        indicator_id=indicator_id,
        pillar=pillar,
        sub_section=entry["sub_section"],
        display_name=entry["display_name"],
        definition=entry["definition"],
        decision_relevance=entry["decision_relevance"],
        limitations=entry["limitations"],
        esg_alignment=entry["esg_alignment"],
        # Derived entries don't have engine-asset technical metadata.
        asset_id="",
        native_scale_m=None,
        data_type="",
        data_source="",
        temporal_frequency="",
        kind="derived",
        formula=live["formula"] if live else None,
        weights=live["weights"] if live else None,
        # M-P09-COMPOSITES v2: conceptual inputs list from the manifest.
        # Only component scores carry this; aggregates / composite use
        # the live-sourced formula/weights instead.
        inputs=entry.get("inputs"),
        tooltip_summary=entry.get("tooltip_summary"),
    )


# M-P09-COMPOSITES
def _resolve_live_formula(indicator_id: str) -> dict | None:
    """Return ``{"formula": <str>, "weights": <dict>}`` or ``None``.

    Reads from the live engine sources so the library page stays in
    automatic lockstep with the engine. Three cases:

    - **Composite** (``composite.overall_screening``) — hardcoded
      equal-weighted mean over the three pillar follow-up priorities,
      matching the orchestrator's `_compute_composite` semantics.
    - **Pillar aggregates** (e.g. ``nature.followup_priority``) — build
      formula and weights from the c5_drilldown formula tuple.
    - **Component scores** (e.g. ``nature.biodiversity_exposure``) —
      no inner formula in v1 (most are single-input passthroughs),
      so returns ``None`` and the renderer omits the formula section.
    """
    if indicator_id == _COMPOSITE_ID:
        return {
            "formula": (
                "mean(air.audit_followup_priority, "
                "ghg.audit_followup_priority, "
                "nature.followup_priority)"
            ),
            "weights": {
                "air.audit_followup_priority": 1 / 3,
                "ghg.audit_followup_priority": 1 / 3,
                "nature.followup_priority":    1 / 3,
            },
        }

    formula_for_aggregate = {
        "air.audit_followup_priority": _AIR_FORMULA,
        "ghg.audit_followup_priority": _GHG_FORMULA,
        "nature.followup_priority":    _NATURE_FORMULA,
    }
    formula_tuple = formula_for_aggregate.get(indicator_id)
    if formula_tuple is None:
        return None

    parts = [
        f"{term.weight:.2f} × {term.display_name}"
        for term in formula_tuple
    ]
    return {
        "formula": " + ".join(parts),
        "weights": {term.payload_key: term.weight for term in formula_tuple},
    }


def get_esg_caveat() -> str:
    """Top-level caveat for the ESG field. Rendered once at page top."""
    return _load_manifest().get("_meta", {}).get("esg_caveat", "")


# M-UI-A2
def tooltip_summary_for(indicator_id: str) -> str | None:
    """Return the two-sentence summary for an indicator, or None.

    Used by the P-05 indicator-name info popover. Lookup is direct on
    the library's canonical IDs (e.g. ``air.no2.score``,
    ``nature.kba.proximity_score``). Unknown IDs and IDs without a
    written summary both return None — the popover helper treats both
    cases as "silent missing" per spec HS12 and omits the popover
    entirely rather than rendering a placeholder.
    """
    card = load_library().get(indicator_id)
    if card is None:
        return None
    return card.tooltip_summary


# ──────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────

def _load_manifest() -> dict:
    return json.loads(_LIBRARY_JSON.read_text())


def _pillar_for(indicator_id: str) -> str:
    return indicator_id.split(".", 1)[0]


def _technical_metadata_for(indicator_id: str) -> dict:
    """Pull asset_id / scale_m / data_type / data_source from the right
    engine config based on the indicator's pillar."""
    pillar = _pillar_for(indicator_id)
    if pillar == "air":
        # "air.<slug>.score" → slug.
        slug = indicator_id.split(".")[1]
        cfg  = AIR_POLLUTANT_CONFIG[slug]
        return _config_to_meta(cfg)
    if pillar == "ghg":
        slug = indicator_id.split(".")[1]
        cfg  = GHG_INDICATOR_CONFIG[slug]
        return _config_to_meta(cfg)
    if pillar == "nature":
        cfg = NATURE_INDICATOR_CONFIG[_NATURE_ID_TO_CONFIG_KEY[indicator_id]]
        return _config_to_meta(cfg)
    raise KeyError(f"Unknown pillar for indicator {indicator_id!r}")


def _config_to_meta(cfg) -> dict:
    """Extract the four common fields from any pillar's config dataclass.

    KBA's ``scale_m=0.0`` (vector asset) surfaces as ``None`` so the
    UI can render "—" instead of a misleading "0 m".
    """
    scale = getattr(cfg, "scale_m", None)
    return {
        "asset_id":       cfg.asset_id,
        "native_scale_m": scale if scale else None,
        "data_type":      getattr(cfg, "data_type", "satellite_observation"),
        "data_source":    getattr(cfg, "data_source", ""),
    }


# Asset-ID substring → human-readable frequency string. Substring match
# keeps the table simple and covers every v1 asset.
_FREQUENCY_LOOKUP: tuple[tuple[str, str], ...] = (
    ("S5P",          "Daily (Sentinel-5P TROPOMI)"),
    ("CAMS",         "Daily (CAMS NRT analysis)"),
    ("MCD19A2",      "Daily (MODIS MAIAC AOD)"),
    ("VNP46A2",      "Daily (VIIRS Day/Night Band)"),
    ("DYNAMICWORLD", "~5 days (Dynamic World V1)"),
    ("MOD13Q1",      "16 days (MODIS NDVI)"),
    ("hansen",       "Annual (Hansen Global Forest Change)"),
    ("odiac",        "Annual (ODIAC fossil-fuel inventory)"),
    ("KBA",          "Static (KBA Partnership, annual refresh)"),
)


def _describe_frequency(asset_id: str) -> str:
    """Convert an EE asset ID to a human-readable frequency string."""
    for needle, label in _FREQUENCY_LOOKUP:
        if needle in asset_id:
            return label
    return "Varies"


def _stub_entry(indicator_id: str) -> dict:
    """Placeholder content if the manifest is missing an indicator.

    Renders as a degraded card with a "documentation pending" note —
    the page stays usable; the gap is obvious to the user.
    """
    return {
        "sub_section":        "single_value",
        "display_name":       indicator_id,
        "definition":         f"Documentation pending for {indicator_id}.",
        "decision_relevance": "—",
        "limitations":        "—",
        "esg_alignment":      "—",
    }
