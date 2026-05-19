"""Deterministic verbal summary generator (M-UI-E.0).

Produces the rule-based prose paragraphs rendered on P-05's C7 component
(and reused on P-06, plus seeded into P-11 report templates).
Authority: docs/Verbal_Summary_Templates_v1.md. Templates are copied
verbatim from that doc; bucketing matches Wireframes Appendix C.1–C.2.

Public API:
    - `VerbalSummary` — frozen dataclass with `overview`, `air`, `ghg`,
      `nature` paragraph fields, plus `joined()` for the concatenated form.
    - `generate_verbal_summary(payload)` — entry point; takes a fully
      populated `screeningResult` dict (the shape `ScreeningRun.run()`
      returns) and returns a `VerbalSummary`.

Design properties (per Verbal_Summary_Templates_v1.md §0):
  1. Deterministic — same input always returns the same output. No LLM
     calls, no randomness, no stateful behaviour.
  2. Defensible — never invents indicator values, never speculates
     causation, never implies facility-level attribution.
  3. Auditable — every rendered sentence traces back to a template ID
     and a slot-resolution rule. The template ID is reported in
     `VerbalSummary.template_ids` for debug/audit purposes.
  4. Aligned with the UI — bucketing matches Wireframes Appendix C.1–C.2
     (TRAFFIC_LIGHT_THRESHOLDS = 0.33 / 0.66).

See docs/Verbal_Summary_Templates_v1.md for the full design rationale
and the worked end-to-end example in §9.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from engine.constants import (
    DOMINANT_CONTRIBUTOR_SHARE_THRESHOLD,
    TRAFFIC_LIGHT_THRESHOLDS,
)


# ---------------------------------------------------------------------------
# Public types  (M-UI-E.0)
# ---------------------------------------------------------------------------

Bucket = Literal["high", "moderate", "low"]
Pillar = Literal["air", "ghg", "nature"]
DominantPath = Literal["main", "fallback"]
Shape = Literal["0", "M", "1", "2", "3"]


@dataclass(frozen=True)
class VerbalSummary:
    """Four-paragraph verbal summary of a screening result.

    `overview` summarises the cross-pillar picture; `air`, `ghg`, and
    `nature` describe each pillar in turn. `joined()` concatenates the
    four with double-newline breaks for inline display; reports consume
    each paragraph individually for the per-pillar interpretation blocks.

    `template_ids` is provided for debugging and audit logging —
    downstream code can verify which templates fired without re-reading
    the templates table.
    """
    overview: str
    air: str
    ghg: str
    nature: str
    template_ids: dict[str, str] = field(default_factory=dict)

    def joined(self) -> str:
        return "\n\n".join([self.overview, self.air, self.ghg, self.nature])


# Fixed pillar order — see Verbal_Summary_Templates_v1.md §8 (rendering
# order is air → ghg → nature regardless of priority).
_PILLARS: tuple[Pillar, ...] = ("air", "ghg", "nature")

# Canonical IDs for each pillar's follow-up priority and confidence
# aggregate, bridging the doc's pseudo-code ("{p}.followup_priority")
# to the engine's actual payload shape (Air/GHG use audit_followup_priority).
_PRIORITY_KEY: dict[Pillar, str] = {
    "air":    "air.audit_followup_priority",
    "ghg":    "ghg.audit_followup_priority",
    "nature": "nature.followup_priority",
}
_CONFIDENCE_KEY: dict[Pillar, str] = {
    "air":    "air.attribution_confidence_score",
    "ghg":    "ghg.data_quality_attribution",
    "nature": "nature.quality_attribution",
}

# Per-pillar display names — used in the overview templates. Doc §7.2.
# (Note: only "GHG emissions" lower-cases the second word per the doc.)
_PILLAR_DISPLAY: dict[Pillar, str] = {
    "air":    "Air Pollution",
    "ghg":    "GHG emissions",
    "nature": "Nature/Land",
}


# ---------------------------------------------------------------------------
# Bucketing  (M-UI-E.0; doc §1)
# ---------------------------------------------------------------------------

def _bucket(score: float | None) -> Bucket | None:
    """Tertile-based score → bucket. Matches Wireframes Appendix C.1.

    A score of exactly 0.33 or 0.66 lands in the higher-severity band.
    None propagates as None; downstream rendering treats None as "low"
    for template selection (the low/low cell already carries the
    "data is sparse" caveat).
    """
    if score is None:
        return None
    low_thr, high_thr = TRAFFIC_LIGHT_THRESHOLDS  # (0.33, 0.66)
    if score >= high_thr:
        return "high"
    if score >= low_thr:
        return "moderate"
    return "low"


# ---------------------------------------------------------------------------
# Dominant-contributor candidates  (M-UI-E.0; doc §3)
# ---------------------------------------------------------------------------

# Doc §3.1 — Air Pollution Proxy Score candidates.
_AIR_DOMINANT_CANDIDATES: dict[str, tuple[float, str]] = {
    "air.no2.score":     (0.30, "NO₂"),
    "air.so2.score":     (0.20, "SO₂"),
    "air.co.score":      (0.15, "CO"),
    "air.hcho.score":    (0.15, "HCHO (formaldehyde)"),
    "air.pm_or_aerosol": (0.10, "PM₂.₅ / aerosols"),
    "air.o3.score":      (0.10, "ozone (context)"),
}

# Doc §3.2 — GHG. Notional pre-M5.5b weights (the verbal summary still
# picks among all four terms because users want to know "what's driving
# the GHG signal", and ODIAC's standing-exposure contribution is part
# of that narrative even though it doesn't feed core_audit_support
# after M5.5b).
_GHG_DOMINANT_CANDIDATES: dict[str, tuple[float, str]] = {
    "ghg.co2_context":          (0.39, "fossil CO₂ context (ODIAC)"),
    "ghg.ch4_context_adjusted": (0.28, "atmospheric methane"),
    "ghg.combustion_proxy":     (0.22, "combustion proxy (NO₂ + CO)"),
    "ghg.activity_score":       (0.11, "nighttime-light activity"),
}

# Doc §3.3 — Nature exposure-side candidates only (quality-attribution
# is excluded).
_NATURE_DOMINANT_CANDIDATES: dict[str, tuple[float, str]] = {
    "nature.biodiversity_exposure":    (0.30, "proximity to Key Biodiversity Areas"),
    "nature.habitat.conversion_score": (0.30, "habitat conversion"),
    "nature.vegetation_condition":     (0.25, "vegetation condition"),
}


def _resolve_dominant(
    payload: dict,
    candidates: dict[str, tuple[float, str]],
) -> tuple[str, str] | None:
    """Pick the dominant contributor for one pillar.

    Returns (term_id, display_name) when one candidate's
    `weight × score` contribution share exceeds
    `DOMINANT_CONTRIBUTOR_SHARE_THRESHOLD` (= 0.40). Returns None when
    no clear dominant term — caller falls back to the no-dominant-driver
    template variant.

    Tie-break per doc §3.3: descending natural weight, then alphabetical
    display name.
    """
    contributions: dict[str, tuple[float, float, str]] = {}
    for term_id, (weight, display) in candidates.items():
        value = payload.get(term_id)
        if value is None:
            continue
        contributions[term_id] = (weight * value, weight, display)

    if not contributions:
        return None

    total = sum(c[0] for c in contributions.values())
    if total <= 0:
        return None

    # Max by contribution; tie-break: weight desc, then display asc.
    # The display string sorts ascending, so we negate via a tuple
    # built from its lowercase form.
    def _sort_key(term_id: str) -> tuple[float, float, tuple[int, ...]]:
        contribution, weight, display = contributions[term_id]
        # ASCII-codepoint tuple of the lowercase display string,
        # negated for ascending order under max().
        display_key = tuple(-ord(ch) for ch in display.lower())
        return (contribution, weight, display_key)

    winner_id = max(contributions, key=_sort_key)
    winner_contribution, _, winner_display = contributions[winner_id]
    if winner_contribution / total < DOMINANT_CONTRIBUTOR_SHARE_THRESHOLD:
        return None
    return winner_id, winner_display


# ---------------------------------------------------------------------------
# Per-pillar dominant-slot formatters  (M-UI-E.0; doc §4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _DominantSlots:
    """Filled-in dominant slots for one pillar's template.

    `direction` is None for terms whose `z` field already names the
    comparison (CH₄'s "X ppb above background", VIIRS's "X.Xσ above
    background"). The renderer strips the trailing
    " {dominant_direction} background" phrase when direction is None,
    so the prose reads naturally. Doc §4.2 / §8.
    """
    indicator: str
    value: str
    z: str
    direction: str | None


# Doc §2 — display units in prose form (⁻² superscript, not /m²).
_AIR_PROSE_UNITS: dict[str, str] = {
    "air.no2.score":     "µmol m⁻²",
    "air.so2.score":     "µmol m⁻²",
    "air.co.score":      "mmol m⁻²",
    "air.hcho.score":    "µmol m⁻²",
    "air.o3.score":      "DU",
    "air.pm_or_aerosol": "µg m⁻³",
}


def _air_dominant_slots(
    payload: dict, term_id: str, display: str,
) -> _DominantSlots:
    """Air slots — doc §4.1.

    Direct read from the dominant indicator's `.site`, `.z`, and the
    sign of `.anomaly`. `direction` is always "above" or "at" — never
    None. PM_or_aerosol resolves to the dominant input (PM₂.₅ if
    available, else AAI) since the composite has no .site of its own.
    """
    if term_id == "air.pm_or_aerosol":
        # Sub-aggregate has no .site — resolve to the dominant atomic input.
        pm25_score = payload.get("air.pm25.score")
        indicator = "pm25" if pm25_score is not None else "aai"
        unit_key = "air.pm_or_aerosol"
    else:
        indicator = term_id.split(".")[1]  # "air.no2.score" → "no2"
        unit_key = term_id

    site = payload.get(f"air.{indicator}.site")
    z = payload.get(f"air.{indicator}.z")
    anomaly = payload.get(f"air.{indicator}.anomaly")
    unit = _AIR_PROSE_UNITS.get(unit_key, "")

    value_str = (
        f"{site:.0f} {unit}".rstrip()
        if site is not None else "—"
    )
    z_str = f"{z:.1f}σ" if z is not None else "—"
    direction = (
        "above" if (anomaly is not None and anomaly > 0)
        else ("at" if anomaly is not None else None)
    )
    return _DominantSlots(
        indicator=display, value=value_str, z=z_str, direction=direction,
    )


def _ghg_dominant_slots(
    payload: dict, term_id: str, display: str,
) -> _DominantSlots:
    """GHG slots — doc §4.2. Heterogeneous formatters per dominant term.

    - co2_context: total t CO₂ + "× the regional median" via relative_intensity
    - ch4_context_adjusted: ppb site + "X ppb above background" + direction None
    - combustion_proxy: "score 0.XX" + canned "combined NO₂ + CO signal" + None
    - activity_score: viirs site nW + "X.Xσ above background" + None
    """
    if term_id == "ghg.co2_context":
        total = payload.get("ghg.co2.total")
        # M5.5b/c rename: relative_intensity replaces the doc's
        # `ghg.co2.background_median` ratio. It IS the ratio.
        rel_intensity = payload.get("ghg.co2.relative_intensity")
        value = (
            f"{total:,.0f} t CO₂ yr⁻¹" if total is not None else "—"
        )
        z = (
            f"{rel_intensity:.1f}× the regional median"
            if rel_intensity is not None else "—"
        )
        return _DominantSlots(
            indicator=display, value=value, z=z, direction="above",
        )
    if term_id == "ghg.ch4_context_adjusted":
        site = payload.get("ghg.ch4.site")
        anomaly = payload.get("ghg.ch4.anomaly")
        value = f"{site:.0f} ppb" if site is not None else "—"
        z = (
            f"{anomaly:.2f} ppb above background"
            if anomaly is not None else "—"
        )
        return _DominantSlots(
            indicator=display, value=value, z=z, direction=None,
        )
    if term_id == "ghg.combustion_proxy":
        score = payload.get("ghg.combustion_proxy")
        value = (
            f"score {score:.2f}" if score is not None else "—"
        )
        return _DominantSlots(
            indicator=display, value=value,
            z="combined NO₂ + CO signal", direction=None,
        )
    if term_id == "ghg.activity_score":
        viirs_site = payload.get("ghg.viirs.site")
        viirs_z = payload.get("ghg.viirs.z")
        value = (
            f"median radiance {viirs_site:.1f} nW cm⁻² sr⁻¹"
            if viirs_site is not None else "—"
        )
        # VIIRS lacks z in v1 (Schema_v2 §3.1 reduced 5-key set); fall
        # back to a generic phrase if unavailable.
        z = (
            f"{viirs_z:.1f}σ above background"
            if viirs_z is not None
            else "above the regional background"
        )
        return _DominantSlots(
            indicator=display, value=value, z=z, direction=None,
        )
    # Unknown term — return a safe placeholder.
    return _DominantSlots(
        indicator=display, value="—", z="—", direction=None,
    )


def _nature_dominant_slots(
    payload: dict, term_id: str, display: str,
) -> _DominantSlots:
    """Nature slots — doc §4.3. {dominant_z} and {dominant_direction}
    are unused for Nature (habitat / biodiversity findings are absolute
    exposures, not anomalies); pass sentinels and let the renderer drop
    the unused phrase via the direction-stripping helper.
    """
    if term_id == "nature.biodiversity_exposure":
        overlap_pct = payload.get("nature.kba.overlap_pct")
        dist_km = payload.get("nature.kba.dist_km")
        if overlap_pct is not None and overlap_pct > 0:
            value = (
                f"{overlap_pct:.0f}% of buffer overlaps a Key Biodiversity Area"
            )
        elif dist_km is not None:
            value = f"nearest Key Biodiversity Area is {dist_km:.1f} km away"
        else:
            value = "—"
        return _DominantSlots(
            indicator=display, value=value, z="", direction=None,
        )
    if term_id == "nature.habitat.conversion_score":
        loss_ha = payload.get("nature.habitat.natural_loss_ha")
        loss_pct = payload.get("nature.habitat.natural_loss_pct")
        rate = payload.get("nature.habitat.annualised_rate")
        if loss_ha is not None and loss_pct is not None and rate is not None:
            value = (
                f"{loss_ha:.1f} ha of natural cover lost — "
                f"{loss_pct:.1f}% of buffer — {rate:.1f} ha yr⁻¹"
            )
        elif loss_ha is not None:
            value = f"{loss_ha:.1f} ha of natural cover lost"
        else:
            value = "—"
        return _DominantSlots(
            indicator=display, value=value, z="", direction=None,
        )
    if term_id == "nature.vegetation_condition":
        ndvi_anomaly = payload.get("nature.ndvi.anomaly")
        low_pct = payload.get("nature.low_ndvi.pct")
        if ndvi_anomaly is not None and low_pct is not None:
            value = (
                f"NDVI {ndvi_anomaly:+.2f} relative to background, "
                f"with {low_pct:.0f}% of natural-cover pixels degraded"
            )
        elif ndvi_anomaly is not None:
            value = f"NDVI {ndvi_anomaly:+.2f} relative to background"
        else:
            value = "—"
        return _DominantSlots(
            indicator=display, value=value, z="", direction=None,
        )
    return _DominantSlots(
        indicator=display, value="—", z="", direction=None,
    )


# ---------------------------------------------------------------------------
# Limiting-factor lookups  (M-UI-E.0; doc §5)
# ---------------------------------------------------------------------------

# Doc §5.1 — Air. Display strings for each pollutant when it carries the
# lowest .confidence value among the selected pollutants. AOD is included
# as a friendly extension beyond the doc's §5.1 table since the v1 engine
# computes it; the same lowest-confidence-wins logic applies.
_AIR_LIMITING_FACTOR_PROSE: dict[str, str] = {
    "no2":  "low valid-pixel coverage for NO₂ in this buffer",
    "so2":  "weak retrieval quality for SO₂ at these concentrations",
    "co":   "low valid-pixel coverage for CO",
    "hcho": "low valid-pixel coverage for HCHO",
    "pm25": "the coarse spatial resolution of CAMS PM₂.₅ (~44 km)",
    "pm10": "the coarse spatial resolution of CAMS PM₁₀ (~44 km)",
    "o3":   "low valid-pixel coverage for O₃",
    "aai":  "low valid-pixel coverage for absorbing aerosols",
    "aod":  "weak retrieval quality for AOD at these aerosol loadings",
}

# Doc §5.2 — GHG quality sub-scores keyed by their canonical IDs.
_GHG_LIMITING_FACTOR_PROSE: dict[str, str] = {
    "ghg.temporal_coverage":              "sparse temporal coverage over the analysis window",
    "ghg.spatial_resolution_suitability": "the coarse spatial resolution of methane retrievals relative to the buffer",
    "ghg.retrieval_inventory_quality":    "weak retrieval quality flags",
    "ghg.nearby_source_isolation":        "background contamination from nearby industrial activity",
}

# Doc §5.3 — Nature quality sub-scores.
_NATURE_LIMITING_FACTOR_PROSE: dict[str, str] = {
    "nature.valid_pixel_coverage":      "low valid-pixel coverage (cloud cover or no-data)",
    "nature.cloud_observation_quality": "high cloud contamination in Sentinel-2 observations",
    "nature.dw.class_confidence":       "ambiguous land-cover classification (no dominant class)",
    "nature.seasonal_comparability":    "seasonal mismatch between the baseline and current composites",
    "nature.supplier_spatial_link":     "the observed change is not concentrated near the supplier point",
    "nature.external_driver_screening": "an external driver (fire, drought, or regional loss) appears to explain the change",
}


def _resolve_air_limiting_factor(payload: dict) -> str | None:
    """Lowest-confidence Air pollutant → its prose string. None when no
    air pollutant has a .confidence value to compare.
    """
    min_conf: float | None = None
    min_pollutant: str | None = None
    for pollutant in _AIR_LIMITING_FACTOR_PROSE:
        conf = payload.get(f"air.{pollutant}.confidence")
        if conf is None:
            continue
        if min_conf is None or conf < min_conf:
            min_conf = conf
            min_pollutant = pollutant
    if min_pollutant is None:
        return None
    return _AIR_LIMITING_FACTOR_PROSE[min_pollutant]


def _resolve_quality_limiting_factor(
    payload: dict,
    prose_map: dict[str, str],
) -> str | None:
    """Lowest-valued sub-score → prose. Shared by GHG and Nature."""
    min_score: float | None = None
    min_key: str | None = None
    for key in prose_map:
        value = payload.get(key)
        if value is None:
            continue
        if min_score is None or value < min_score:
            min_score = value
            min_key = key
    if min_key is None:
        return None
    return prose_map[min_key]


# ---------------------------------------------------------------------------
# Pillar templates  (M-UI-E.0; doc §6.1–§6.6 verbatim)
# ---------------------------------------------------------------------------

_PER_PILLAR_TEMPLATES: dict[tuple[Pillar, Bucket, Bucket, DominantPath], str] = {
    # ─── Air — 9 main (§6.1) ───────────────────────────────────────────────
    ("air", "high", "high", "main"):
        "Air pollution is elevated at this location, driven primarily by "
        "{dominant_indicator} ({dominant_value}, {dominant_z} "
        "{dominant_direction} background). Data quality is high.",
    ("air", "high", "moderate", "main"):
        "Air pollution is elevated at this location, driven primarily by "
        "{dominant_indicator} ({dominant_value}, {dominant_z} "
        "{dominant_direction} background). Confidence is moderate — "
        "interpretation is limited by {limiting_factor}.",
    ("air", "high", "low", "main"):
        "Air pollution may be elevated at this location based on "
        "{dominant_indicator} ({dominant_value}, {dominant_z} "
        "{dominant_direction} background), but data quality is poor — "
        "{limiting_factor} limits the reliability of this score. "
        "Investigate before acting.",
    ("air", "moderate", "high", "main"):
        "Air pollution shows moderate elevation at this location, with "
        "{dominant_indicator} as the main contributor ({dominant_value}, "
        "{dominant_z} {dominant_direction} background). The signal is "
        "within typical regional variability. Data quality is high.",
    ("air", "moderate", "moderate", "main"):
        "Air pollution shows moderate elevation at this location, with "
        "{dominant_indicator} contributing most ({dominant_value}, "
        "{dominant_z} {dominant_direction} background). Confidence is "
        "mixed — {limiting_factor} is a limiting factor.",
    ("air", "moderate", "low", "main"):
        "A moderate air-pollution signal is present at this location, "
        "with {dominant_indicator} ({dominant_value}, {dominant_z} "
        "{dominant_direction} background) as the largest contributor, "
        "but data quality is poor — {limiting_factor} limits the "
        "reliability of this read.",
    ("air", "low", "high", "main"):
        "Air pollution is at background levels across the monitored "
        "pollutants at this location. Data quality is high.",
    ("air", "low", "moderate", "main"):
        "Air pollution appears at background levels across the monitored "
        "pollutants at this location. Confidence is moderate — "
        "{limiting_factor} is a limiting factor.",
    ("air", "low", "low", "main"):
        "Air pollution appears at background levels across the monitored "
        "pollutants at this location, but data is sparse — "
        "{limiting_factor} limits the reliability of this conclusion. "
        "A 'low priority' read here should not be taken as a clear negative.",

    # ─── Air — 6 fallback (§6.2; low-priority cells have no fallback) ──────
    ("air", "high", "high", "fallback"):
        "Air pollution is elevated at this location across multiple gases, "
        "with no single dominant driver. Data quality is high.",
    ("air", "high", "moderate", "fallback"):
        "Air pollution is elevated at this location across multiple gases, "
        "with no single dominant driver. Confidence is moderate — "
        "interpretation is limited by {limiting_factor}.",
    ("air", "high", "low", "fallback"):
        "Air pollution may be elevated at this location across multiple "
        "gases, but data quality is poor — {limiting_factor} limits the "
        "reliability of this score. Investigate before acting.",
    ("air", "moderate", "high", "fallback"):
        "Air pollution shows moderate elevation across multiple gases at "
        "this location, with no single dominant driver. Data quality is high.",
    ("air", "moderate", "moderate", "fallback"):
        "Air pollution shows moderate elevation across multiple gases at "
        "this location. Confidence is mixed — {limiting_factor} is a "
        "limiting factor.",
    ("air", "moderate", "low", "fallback"):
        "A moderate air-pollution signal is present at this location "
        "across multiple gases, but data quality is poor — "
        "{limiting_factor} limits the reliability of this read.",

    # ─── GHG — 9 main (§6.3) ───────────────────────────────────────────────
    ("ghg", "high", "high", "main"):
        "Greenhouse gases are elevated at this location, driven primarily "
        "by {dominant_indicator} ({dominant_value}, {dominant_z} "
        "{dominant_direction} background). Data quality is high.",
    ("ghg", "high", "moderate", "main"):
        "Greenhouse gases are elevated at this location, driven primarily "
        "by {dominant_indicator} ({dominant_value}, {dominant_z} "
        "{dominant_direction} background). Confidence is moderate — "
        "interpretation is limited by {limiting_factor}.",
    ("ghg", "high", "low", "main"):
        "Greenhouse gases may be elevated at this location based on "
        "{dominant_indicator} ({dominant_value}, {dominant_z} "
        "{dominant_direction} background), but data quality is poor — "
        "{limiting_factor} limits the reliability of this score. "
        "Investigate before acting.",
    ("ghg", "moderate", "high", "main"):
        "Greenhouse gases show moderate elevation at this location, with "
        "{dominant_indicator} as the main contributor ({dominant_value}, "
        "{dominant_z} {dominant_direction} background). The signal is "
        "within typical regional variability. Data quality is high.",
    ("ghg", "moderate", "moderate", "main"):
        "Greenhouse gases show moderate elevation at this location, with "
        "{dominant_indicator} contributing most ({dominant_value}, "
        "{dominant_z} {dominant_direction} background). Confidence is "
        "mixed — {limiting_factor} is a limiting factor.",
    ("ghg", "moderate", "low", "main"):
        "A moderate GHG signal is present at this location, with "
        "{dominant_indicator} ({dominant_value}, {dominant_z} "
        "{dominant_direction} background) as the largest contributor, "
        "but data quality is poor — {limiting_factor} limits the "
        "reliability of this read.",
    ("ghg", "low", "high", "main"):
        "Greenhouse gases are at background levels across the monitored "
        "GHG indicators at this location. Data quality is high.",
    ("ghg", "low", "moderate", "main"):
        "Greenhouse gases appear at background levels across the monitored "
        "indicators at this location. Confidence is moderate — "
        "{limiting_factor} is a limiting factor.",
    ("ghg", "low", "low", "main"):
        "Greenhouse gases appear at background levels at this location, "
        "but data is sparse — {limiting_factor} limits the reliability of "
        "this conclusion. A 'low priority' read here should not be taken "
        "as a clear negative.",

    # ─── GHG — 6 fallback (§6.4) ───────────────────────────────────────────
    ("ghg", "high", "high", "fallback"):
        "Greenhouse gases are elevated at this location across multiple "
        "indicators, with no single dominant driver. Data quality is high.",
    ("ghg", "high", "moderate", "fallback"):
        "Greenhouse gases are elevated at this location across multiple "
        "indicators, with no single dominant driver. Confidence is "
        "moderate — interpretation is limited by {limiting_factor}.",
    ("ghg", "high", "low", "fallback"):
        "Greenhouse gases may be elevated at this location across multiple "
        "indicators, but data quality is poor — {limiting_factor} limits "
        "the reliability of this score. Investigate before acting.",
    ("ghg", "moderate", "high", "fallback"):
        "Greenhouse gases show moderate elevation across multiple "
        "indicators at this location, with no single dominant driver. "
        "Data quality is high.",
    ("ghg", "moderate", "moderate", "fallback"):
        "Greenhouse gases show moderate elevation across multiple "
        "indicators at this location. Confidence is mixed — "
        "{limiting_factor} is a limiting factor.",
    ("ghg", "moderate", "low", "fallback"):
        "A moderate GHG signal is present at this location across "
        "multiple indicators, but data quality is poor — "
        "{limiting_factor} limits the reliability of this read.",

    # ─── Nature/Land — 9 main (§6.5) ───────────────────────────────────────
    ("nature", "high", "high", "main"):
        "Nature/Land shows significant exposure at this location, with "
        "{dominant_indicator} as the main concern ({dominant_value}). "
        "Data quality is high.",
    ("nature", "high", "moderate", "main"):
        "Nature/Land shows significant exposure at this location, with "
        "{dominant_indicator} as the main concern ({dominant_value}). "
        "Confidence is moderate — interpretation is limited by "
        "{limiting_factor}.",
    ("nature", "high", "low", "main"):
        "Nature/Land exposure may be significant at this location based "
        "on {dominant_indicator} ({dominant_value}), but data quality is "
        "poor — {limiting_factor} limits the reliability of this score. "
        "Investigate before acting.",
    ("nature", "moderate", "high", "main"):
        "Nature/Land shows moderate exposure at this location, with "
        "{dominant_indicator} as the main contributor ({dominant_value}). "
        "Data quality is high.",
    ("nature", "moderate", "moderate", "main"):
        "Nature/Land shows moderate exposure at this location, with "
        "{dominant_indicator} contributing most ({dominant_value}). "
        "Confidence is mixed — {limiting_factor} is a limiting factor.",
    ("nature", "moderate", "low", "main"):
        "A moderate Nature/Land exposure is present at this location, "
        "with {dominant_indicator} ({dominant_value}) as the largest "
        "contributor, but data quality is poor — {limiting_factor} "
        "limits the reliability of this read.",
    ("nature", "low", "high", "main"):
        "Nature/Land is at baseline across the monitored land-cover "
        "indicators at this location. Data quality is high.",
    ("nature", "low", "moderate", "main"):
        "Nature/Land appears at baseline across the monitored land-cover "
        "indicators at this location. Confidence is moderate — "
        "{limiting_factor} is a limiting factor.",
    ("nature", "low", "low", "main"):
        "Nature/Land appears at baseline at this location, but data is "
        "sparse — {limiting_factor} limits the reliability of this "
        "conclusion. A 'low priority' read here should not be taken as a "
        "clear negative.",

    # ─── Nature/Land — 6 fallback (§6.6) ───────────────────────────────────
    ("nature", "high", "high", "fallback"):
        "Nature/Land shows significant exposure at this location across "
        "multiple aspects, with no single dominant concern. Data quality "
        "is high.",
    ("nature", "high", "moderate", "fallback"):
        "Nature/Land shows significant exposure at this location across "
        "multiple aspects, with no single dominant concern. Confidence is "
        "moderate — interpretation is limited by {limiting_factor}.",
    ("nature", "high", "low", "fallback"):
        "Nature/Land exposure may be significant at this location across "
        "multiple aspects, but data quality is poor — {limiting_factor} "
        "limits the reliability of this score. Investigate before acting.",
    ("nature", "moderate", "high", "fallback"):
        "Nature/Land shows moderate exposure across multiple aspects at "
        "this location, with no single dominant concern. Data quality is high.",
    ("nature", "moderate", "moderate", "fallback"):
        "Nature/Land shows moderate exposure across multiple aspects at "
        "this location. Confidence is mixed — {limiting_factor} is a "
        "limiting factor.",
    ("nature", "moderate", "low", "fallback"):
        "A moderate Nature/Land exposure is present across multiple "
        "aspects at this location, but data quality is poor — "
        "{limiting_factor} limits the reliability of this read.",
}


# ---------------------------------------------------------------------------
# Overview templates  (M-UI-E.0; doc §7.4 — 15 templates)
# ---------------------------------------------------------------------------

_OVERVIEW_TEMPLATES: dict[tuple[Shape, Bucket], str] = {
    # 0 — all pillars at background
    ("0", "high"):
        "All three pillars are at background levels (composite "
        "{composite_score}). Data quality is high.",
    ("0", "moderate"):
        "All three pillars appear at background levels (composite "
        "{composite_score}). Composite confidence is moderate.",
    ("0", "low"):
        "All three pillars appear at background levels (composite "
        "{composite_score}), but composite confidence is low — at least "
        "one pillar has significant data-quality limitations. Treat the "
        "'all clear' read with caution.",
    # 1 — one high pillar
    ("1", "high"):
        "Overall priority is {composite_bucket} (composite "
        "{composite_score}), driven by {high_pillar}. Data quality is high.",
    ("1", "moderate"):
        "Overall priority is {composite_bucket} (composite "
        "{composite_score}), driven by {high_pillar}. Composite confidence "
        "is moderate.",
    ("1", "low"):
        "Overall priority appears {composite_bucket} (composite "
        "{composite_score}), driven by {high_pillar}, but composite "
        "confidence is low — read the pillar detail before acting.",
    # 2 — two high pillars
    ("2", "high"):
        "Overall priority is high (composite {composite_score}), with "
        "elevated signals in {high_pillar_a} and {high_pillar_b}. Data "
        "quality is high.",
    ("2", "moderate"):
        "Overall priority is high (composite {composite_score}), with "
        "elevated signals in {high_pillar_a} and {high_pillar_b}. "
        "Composite confidence is moderate.",
    ("2", "low"):
        "Overall priority appears high (composite {composite_score}), "
        "with elevated signals in {high_pillar_a} and {high_pillar_b}, "
        "but composite confidence is low — read the pillar detail before "
        "acting.",
    # 3 — all three high
    ("3", "high"):
        "Overall priority is high across all three pillars (composite "
        "{composite_score}). Data quality is high. This is a clear flag "
        "for follow-up.",
    ("3", "moderate"):
        "Overall priority is high across all three pillars (composite "
        "{composite_score}). Composite confidence is moderate. This is a "
        "clear flag for follow-up.",
    ("3", "low"):
        "Overall priority appears high across all three pillars (composite "
        "{composite_score}), but composite confidence is low — read the "
        "pillar detail before acting.",
    # M — at least one moderate (and zero high)
    ("M", "high"):
        "Overall priority is moderate (composite {composite_score}). "
        "{moderate_pillar_list_phrase}. Data quality is high.",
    ("M", "moderate"):
        "Overall priority is moderate (composite {composite_score}). "
        "{moderate_pillar_list_phrase}. Composite confidence is moderate.",
    ("M", "low"):
        "Overall priority appears moderate (composite {composite_score}). "
        "{moderate_pillar_list_phrase}. Composite confidence is low — "
        "read the pillar detail before acting.",
}


# ---------------------------------------------------------------------------
# Overview helpers  (doc §7.1 / §7.3)
# ---------------------------------------------------------------------------

def _composite_shape(pillar_priority: dict[Pillar, Bucket | None]) -> Shape:
    """Doc §7.1 — count high/moderate pillars to pick the overview row."""
    high = sum(1 for b in pillar_priority.values() if b == "high")
    moderate = sum(1 for b in pillar_priority.values() if b == "moderate")
    if high == 3:
        return "3"
    if high == 2:
        return "2"
    if high == 1:
        return "1"
    if moderate >= 1:
        return "M"
    return "0"


def _moderate_pillar_list_phrase(moderate_pillars: list[str]) -> str:
    """Doc §7.3 — render the "Concern centres on …" phrase."""
    n = len(moderate_pillars)
    if n == 1:
        return f"Concern centres on {moderate_pillars[0]}"
    if n == 2:
        return (
            f"Concern centres on {moderate_pillars[0]} and "
            f"{moderate_pillars[1]}"
        )
    if n == 3:
        return "Concern is spread across all three pillars"
    return ""  # n == 0 → unreachable when shape == "M"


# ---------------------------------------------------------------------------
# Renderers  (doc §8)
# ---------------------------------------------------------------------------

def _strip_trailing_direction(rendered: str, slots: _DominantSlots) -> str:
    """Doc §8 — remove the orphan " {dominant_direction} background"
    phrase from a rendered template when `slots.direction is None`.

    The template literally contains "{dominant_z} {dominant_direction}
    background". When direction is None we passed it as empty string;
    str.format leaves "X  background" (double space) which this helper
    collapses to "X)" (or wherever the next character was).
    """
    if slots.direction is not None:
        return rendered
    # Drop the orphan " <space>background" inserted when direction was "".
    rendered = rendered.replace("  background", "")
    return rendered


def _render_overview(payload: dict, pillar_priority: dict[Pillar, Bucket | None]) -> tuple[str, str]:
    """Pick + render the overview template. Returns (rendered, template_id)."""
    composite = payload.get("composite.overall_screening")
    confidence = payload.get("composite.confidence")
    priority_bucket: Bucket = _bucket(composite) or "low"
    conf_bucket: Bucket = _bucket(confidence) or "low"
    shape = _composite_shape(pillar_priority)

    high_pillars = [
        _PILLAR_DISPLAY[p] for p in _PILLARS if pillar_priority.get(p) == "high"
    ]
    moderate_pillars = [
        _PILLAR_DISPLAY[p] for p in _PILLARS if pillar_priority.get(p) == "moderate"
    ]

    template = _OVERVIEW_TEMPLATES[(shape, conf_bucket)]
    kwargs: dict[str, str] = {
        "composite_score":
            f"{composite:.2f}" if composite is not None else "—",
        "composite_bucket":            priority_bucket,
        "high_pillar":                 high_pillars[0] if high_pillars else "",
        "high_pillar_a":               high_pillars[0] if len(high_pillars) >= 2 else "",
        "high_pillar_b":               high_pillars[1] if len(high_pillars) >= 2 else "",
        "moderate_pillar_list_phrase": _moderate_pillar_list_phrase(moderate_pillars),
    }
    rendered = template.format(**kwargs)
    template_id = f"overview/{shape}/{conf_bucket}"
    return rendered, template_id


def _render_pillar(pillar: Pillar, payload: dict) -> tuple[str, str, Bucket]:
    """Pick + render the per-pillar template.

    Returns (rendered, template_id, priority_bucket) — the bucket is
    surfaced so the overview renderer can feed it into shape selection
    without re-bucketing.
    """
    priority = payload.get(_PRIORITY_KEY[pillar])
    confidence = payload.get(_CONFIDENCE_KEY[pillar])
    priority_bucket: Bucket = _bucket(priority) or "low"
    conf_bucket: Bucket = _bucket(confidence) or "low"

    candidates_map = {
        "air":    _AIR_DOMINANT_CANDIDATES,
        "ghg":    _GHG_DOMINANT_CANDIDATES,
        "nature": _NATURE_DOMINANT_CANDIDATES,
    }[pillar]

    # Low-priority cells: doc §6.2 / §6.4 / §6.6 — no fallback variant.
    # The "main" template is rendered with no dominant slots (the
    # low-priority main templates don't reference them).
    if priority_bucket == "low":
        dominant_path: DominantPath = "main"
        slots: _DominantSlots | None = None
    else:
        dominant = _resolve_dominant(payload, candidates_map)
        if dominant is None:
            dominant_path = "fallback"
            slots = None
        else:
            dominant_path = "main"
            term_id, display = dominant
            slot_fn = {
                "air":    _air_dominant_slots,
                "ghg":    _ghg_dominant_slots,
                "nature": _nature_dominant_slots,
            }[pillar]
            slots = slot_fn(payload, term_id, display)

    limiting_factor = (
        _resolve_air_limiting_factor(payload) if pillar == "air"
        else _resolve_quality_limiting_factor(
            payload,
            _GHG_LIMITING_FACTOR_PROSE if pillar == "ghg"
            else _NATURE_LIMITING_FACTOR_PROSE,
        )
    ) or "data quality limitations"

    template = _PER_PILLAR_TEMPLATES[
        (pillar, priority_bucket, conf_bucket, dominant_path)
    ]
    kwargs: dict[str, str] = {"limiting_factor": limiting_factor}
    if slots is not None:
        kwargs.update({
            "dominant_indicator": slots.indicator,
            "dominant_value":     slots.value,
            "dominant_z":         slots.z,
            "dominant_direction": slots.direction or "",
        })

    rendered = template.format(**kwargs)
    if slots is not None:
        rendered = _strip_trailing_direction(rendered, slots)

    template_id = f"{pillar}/{priority_bucket}/{conf_bucket}/{dominant_path}"
    return rendered, template_id, priority_bucket


# ---------------------------------------------------------------------------
# Public entry point  (doc §8)
# ---------------------------------------------------------------------------

def generate_verbal_summary(payload: dict) -> VerbalSummary:
    """Render a four-paragraph verbal summary from a screening result.

    `payload` is a fully populated `screeningResult` dict — the same
    shape that `ScreeningRun.run()` returns. Missing pillar scores
    propagate as None through `_bucket`, which defaults to the "low"
    bucket so the low/low template variant fires gracefully.

    Returns a `VerbalSummary` with `template_ids` documenting which
    templates fired (audit support).
    """
    # Per-pillar rendering first — produces the priority buckets the
    # overview needs for its shape calculation.
    air, air_template_id, air_bucket = _render_pillar("air", payload)
    ghg, ghg_template_id, ghg_bucket = _render_pillar("ghg", payload)
    nature, nat_template_id, nature_bucket = _render_pillar("nature", payload)

    pillar_priority: dict[Pillar, Bucket | None] = {
        "air":    air_bucket,
        "ghg":    ghg_bucket,
        "nature": nature_bucket,
    }
    overview, ov_template_id = _render_overview(payload, pillar_priority)

    return VerbalSummary(
        overview=overview,
        air=air,
        ghg=ghg,
        nature=nature,
        template_ids={
            "overview": ov_template_id,
            "air":      air_template_id,
            "ghg":      ghg_template_id,
            "nature":   nat_template_id,
        },
    )
