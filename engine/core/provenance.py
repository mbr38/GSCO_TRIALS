"""Canonical provenance schema for indicator snapshots.

Every single-value indicator across Air / GHG / Nature emits a
`_provenance.<pillar>.<indicator>` block constructed via `build_provenance`.
The schema is fixed; the only escape hatch is `extra` for genuinely
indicator-specific fields (e.g. ODIAC's `c_to_co2_factor`).

The block carries 15 canonical fields: the original M5.6 11 plus four
v1.x additions (`indicator_id`, `column_to_surface_uncertainty`,
`temporal_mode`, `sector_signal_anomaly`) introduced by M-V1x-RECONCILE
per `docs/Indicators_Audit_and_v1x_Roadmap.md` §1.5 / §9.2 / §9.3.

Why a typed schema:

1. Audit defensibility — reviewers consume a uniform shape across all
   indicators, not per-pillar variants.
2. P-05+ UI consumes provenance to render the "where this number came
   from" panel. Without a uniform schema the UI would need a switch
   statement per indicator.
3. Catches typos at construction time (strict validation on `data_type`,
   `observations.unit`, `column_to_surface_uncertainty`, `temporal_mode`)
   so a misspelled value can't silently break downstream rendering.

See docs/provenance_schema.md for the prose definitions of each field.
"""

from __future__ import annotations

from typing import Any, TypedDict


# ---------------------------------------------------------------------------
# Allowed values
# ---------------------------------------------------------------------------

# The five recognised data-type categories. A reviewer reading provenance
# should understand from this tag alone how to weight the value's
# evidentiary strength:
#   satellite_observation       — direct atmospheric / radiance retrieval
#                                 (e.g. Sentinel-5P TROPOMI, MODIS MAIAC,
#                                 VIIRS NTL). Closest to "ground truth".
#   ml_classified_satellite     — satellite imagery passed through ML
#                                 classification (e.g. Dynamic World).
#                                 Documented confusion matrices apply.
#   gridded_model_output        — atmospheric / earth-system model output,
#                                 NOT a direct measurement (e.g. CAMS PM
#                                 reanalysis). Reviewers should know they
#                                 are reading a model, not an observation.
#   emissions_inventory_allocation — statistical totals down-scaled to a
#                                 grid (e.g. ODIAC: national totals →
#                                 CARMA + nightlights → 1 km grid).
#                                 Modelled allocation, not measured.
#   reference_dataset           — curated polygons / lookup data with no
#                                 inference step (e.g. BirdLife KBA,
#                                 Hansen forest loss post-demotion).
#                                 Authoritative but static.
_ALLOWED_DATA_TYPES: frozenset[str] = frozenset({
    "satellite_observation",
    "ml_classified_satellite",
    "gridded_model_output",
    "emissions_inventory_allocation",
    "reference_dataset",
})


# Allowed units for the `observations` field. Reviewers shouldn't have to
# guess what "count=3" means.
_ALLOWED_OBSERVATION_UNITS: frozenset[str] = frozenset({
    "daily_images",
    "monthly_grids",
    "annual_rasters",
    "16day_composites",
    "static_snapshot",   # reference data (e.g. KBA polygons); count is conceptually 1
})


# v1.x — column-to-surface uncertainty per audit §1.5. Tags how strongly
# the satellite column retrieval maps to surface concentrations. Used by
# the P-11 report and P-05 confidence rendering to set reader expectations
# about what the raw number can actually claim.
_ALLOWED_COLUMN_TO_SURFACE_UNCERTAINTY: frozenset[str] = frozenset({
    "strong",
    "moderate",
    "moderate_weak",
    "weak",
    "n_a",
})


# v1.x — `live_window` indicators reflect the user's analysis window;
# `standing_exposure` indicators (ODIAC, Hansen post-demotion) reflect a
# cumulative or fixed-vintage state independent of the window.
_ALLOWED_TEMPORAL_MODES: frozenset[str] = frozenset({
    "live_window",
    "standing_exposure",
})


# ---------------------------------------------------------------------------
# Lookup tables (audit §1.5 + §9.3)
# ---------------------------------------------------------------------------

# Per-gas column-to-surface uncertainty. Indicator IDs absent from this
# table default to "n_a" — PM/AOD/ODIAC/VIIRS/Dynamic World/Hansen/KBA/NDVI
# are all either surface measurements or non-column-based and so do not
# carry this uncertainty.
_COLUMN_TO_SURFACE_UNCERTAINTY: dict[str, str] = {
    "air.no2":  "moderate",
    "air.so2":  "moderate_weak",
    "air.co":   "weak",
    "air.hcho": "moderate",
    "air.o3":   "n_a",
    "air.aai":  "n_a",
    "ghg.ch4":  "weak",
}


# Standing-exposure indicators. Everything else is `live_window`.
_TEMPORAL_MODE: dict[str, str] = {
    "ghg.co2":                       "standing_exposure",  # ODIAC: vintage lag, cumulative
    "nature.forest_loss":            "standing_exposure",  # Hansen: cumulative since 2000
    "nature.regional_loss_evidence": "standing_exposure",  # fixed 5-year Hansen window
}


class Observations(TypedDict):
    count: int
    unit:  str


class ProvenanceBlock(TypedDict, total=False):
    """The canonical 15-field provenance shape. Keys are documented in the
    order they appear in the returned dict (insertion order is stable in
    3.7+)."""

    # Identification (indicator_id added by M-V1x-RECONCILE)
    indicator_id:    str
    asset_id:        str
    band:            str | None
    # Data character
    data_type:       str
    data_source:     str
    native_scale_m:  float
    # Computation method
    method_note:     str | None
    # Request context
    time_range:      tuple[str, str]
    # Coverage / availability
    coverage_window: tuple[str, str] | None
    skipped_reason:  str | None
    # Observations actually used
    observations:    Observations | None
    # v1.x: scientific honesty tags
    column_to_surface_uncertainty: str
    temporal_mode:   str
    sector_signal_anomaly: bool | None
    # Indicator-specific extension
    extra:           dict[str, Any]


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

def build_provenance(
    *,
    indicator_id: str,
    asset_id: str,
    band: str | None,
    data_type: str,
    data_source: str,
    native_scale_m: float,
    time_range: tuple[str, str],
    method_note: str | None = None,
    coverage_window: tuple[str, str] | None = None,
    skipped_reason: str | None = None,
    observations: Observations | None = None,
    extra: dict[str, Any] | None = None,
    column_to_surface_uncertainty: str | None = None,
    temporal_mode: str | None = None,
    sector_signal_anomaly: bool | None = None,
) -> dict:
    """Construct a canonical 15-field provenance block.

    `indicator_id` is the self-describing pillar.indicator key (e.g.
    `"air.no2"`, `"nature.regional_loss_evidence"`). It also drives the
    lookup-table defaults for `column_to_surface_uncertainty` and
    `temporal_mode` — pass those kwargs only to override the default.

    `sector_signal_anomaly` stays None across v1; it lights up with the
    Tier C2 sector-plumbing milestone per audit §9.2 (and only fires
    when the supplier carries a sector tag AND the satellite signal is
    inconsistent with the tag — preserving the metadata-bias rule).

    All fields land in the returned dict in the documented order;
    downstream consumers (audit logs, P-05 / P-11 UI) can rely on
    insertion order for stable rendering.

    Raises:
        ValueError: `data_type` isn't one of the five recognised values;
                    or `observations.unit` isn't one of the five recognised
                    units; or `observations.count` is negative; or one of
                    `column_to_surface_uncertainty` / `temporal_mode` is
                    explicitly set to a value outside its enum. Validation
                    is strict by design — a typo here should fail loudly at
                    construction, not silently break downstream rendering.
    """
    if data_type not in _ALLOWED_DATA_TYPES:
        raise ValueError(
            f"unknown data_type {data_type!r}; expected one of "
            f"{sorted(_ALLOWED_DATA_TYPES)}"
        )
    if observations is not None:
        unit = observations.get("unit")
        if unit not in _ALLOWED_OBSERVATION_UNITS:
            raise ValueError(
                f"unknown observations.unit {unit!r}; expected one of "
                f"{sorted(_ALLOWED_OBSERVATION_UNITS)}"
            )
        count = observations.get("count")
        if not isinstance(count, int) or count < 0:
            raise ValueError(
                f"observations.count must be a non-negative int; got {count!r}"
            )

    if column_to_surface_uncertainty is None:
        column_to_surface_uncertainty = _COLUMN_TO_SURFACE_UNCERTAINTY.get(
            indicator_id, "n_a",
        )
    if column_to_surface_uncertainty not in _ALLOWED_COLUMN_TO_SURFACE_UNCERTAINTY:
        raise ValueError(
            f"unknown column_to_surface_uncertainty "
            f"{column_to_surface_uncertainty!r}; expected one of "
            f"{sorted(_ALLOWED_COLUMN_TO_SURFACE_UNCERTAINTY)}"
        )

    if temporal_mode is None:
        temporal_mode = _TEMPORAL_MODE.get(indicator_id, "live_window")
    if temporal_mode not in _ALLOWED_TEMPORAL_MODES:
        raise ValueError(
            f"unknown temporal_mode {temporal_mode!r}; expected one of "
            f"{sorted(_ALLOWED_TEMPORAL_MODES)}"
        )

    return {
        "indicator_id":    indicator_id,
        "asset_id":        asset_id,
        "band":            band,
        "data_type":       data_type,
        "data_source":     data_source,
        "native_scale_m":  native_scale_m,
        "method_note":     method_note,
        "time_range":      time_range,
        "coverage_window": coverage_window,
        "skipped_reason":  skipped_reason,
        "observations":    observations,
        "column_to_surface_uncertainty": column_to_surface_uncertainty,
        "temporal_mode":   temporal_mode,
        "sector_signal_anomaly": sector_signal_anomaly,
        "extra":           extra if extra is not None else {},
    }
