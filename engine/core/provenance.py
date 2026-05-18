"""Canonical provenance schema for indicator snapshots (M5.6).

Every single-value indicator across Air / GHG / Nature emits a
`_provenance.<pillar>.<indicator>` block constructed via `build_provenance`.
The schema is fixed; the only escape hatch is `extra` for genuinely
indicator-specific fields (e.g. ODIAC's `c_to_co2_factor`).

Why a typed schema:

1. Audit defensibility — reviewers consume a uniform shape across all
   indicators, not per-pillar variants.
2. P-05+ UI consumes provenance to render the "where this number came
   from" panel. Without a uniform schema the UI would need a switch
   statement per indicator.
3. Catches typos at construction time (strict validation on `data_type`
   and `observations.unit`) so a misspelled value can't silently break
   downstream rendering.

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
#                                 classification (e.g. Dynamic World,
#                                 Hansen forest loss). Documented
#                                 confusion matrices apply.
#   gridded_model_output        — atmospheric / earth-system model output,
#                                 NOT a direct measurement (e.g. CAMS PM
#                                 reanalysis). Reviewers should know they
#                                 are reading a model, not an observation.
#   emissions_inventory_allocation — statistical totals down-scaled to a
#                                 grid (e.g. ODIAC: national totals →
#                                 CARMA + nightlights → 1 km grid).
#                                 Modelled allocation, not measured.
#   reference_dataset           — curated polygons / lookup data with no
#                                 inference step (e.g. BirdLife KBA, JRC
#                                 GSW once wired). Authoritative but
#                                 static.
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


class Observations(TypedDict):
    count: int
    unit:  str


class ProvenanceBlock(TypedDict, total=False):
    """The canonical provenance shape. Keys are documented in the order
    they appear in the returned dict (insertion order is stable in 3.7+)."""

    # Identification
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
    # Indicator-specific extension
    extra:           dict[str, Any]


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

def build_provenance(
    *,
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
) -> dict:
    """Construct a canonical provenance block.

    All fields land in the returned dict in the documented order; downstream
    consumers (audit logs, P-05 UI) can rely on insertion order for stable
    rendering.

    Raises:
        ValueError: `data_type` isn't one of the five recognised values,
                    or `observations.unit` isn't one of the five recognised
                    units, or `observations.count` is negative. Validation
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

    return {
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
        "extra":           extra if extra is not None else {},
    }
