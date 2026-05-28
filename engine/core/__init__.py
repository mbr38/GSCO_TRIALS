"""engine.core — reusable building blocks for the pillar modules.

Stateless functions only. Trend (`engine/core/trend.py`) and seasonality
(`engine/core/seasonality.py`) land in later milestones and are imported
lazily by `repeatable_core` so this package works without them.
"""

from engine.core.adaptive_scale import adaptive_scale_m, method_note_fragment
from engine.core.attributability import (
    ATTRIBUTABILITY_STATES,
    AttributabilityState,
    compass_direction,
    compute_habitat_attributability,
    haversine_km,
)
from engine.core.buffers import (
    background_ring,
    pixel_size_warning,
    site_buffer,
)
from engine.core.confidence import (
    compute_anomaly_strength_term,
    compute_indicator_confidence,
    compute_n_valid_term,
    compute_pillar_confidence,
    compute_qa_term,
    compute_spatial_context_term,
)
from engine.core.climatology import (
    ClimatologyBaseline,
    climatology_baseline,
    country_for_centroid,
    load_climatology,
)
from engine.core.fallback import (
    FallbackContext,
    FallbackOutcome,
    FallbackPlan,
    aoi_scale_class,
    build_fallback_extra,
    resolve_fallback_plan,
    sliding_lookback_windows,
    sppy_window,
)
from engine.core.normalisation import to_score
from engine.core.provenance import build_provenance
from engine.core.repeatable_core import (
    anomaly_z_hf,
    background_value,
    site_value,
    six_step,
)
from engine.core.era5 import (
    Era5WindSample,
    compute_overpass_utc_hour,
    sample_era5_wind_at_overpass,
)
from engine.core.wind import (
    WindAnomalyDayMeasurement,
    WindAttributabilityState,
    build_wind_provenance_extra,
    circular_mean_deg,
    compute_wind_attributability_state,
    compute_wind_attribution_extra,
    half_ring_geometry,
    measure_ring_asymmetry,
    sparse_provenance_extra,
)

__all__ = [
    "adaptive_scale_m",
    "anomaly_z_hf",
    "aoi_scale_class",
    "ATTRIBUTABILITY_STATES",
    "AttributabilityState",
    "background_ring",
    "background_value",
    "build_fallback_extra",
    "build_provenance",
    "build_wind_provenance_extra",
    "circular_mean_deg",
    "ClimatologyBaseline",
    "climatology_baseline",
    "compass_direction",
    "compute_anomaly_strength_term",
    "compute_habitat_attributability",
    "compute_indicator_confidence",
    "compute_n_valid_term",
    "compute_overpass_utc_hour",
    "compute_pillar_confidence",
    "compute_qa_term",
    "compute_spatial_context_term",
    "compute_wind_attributability_state",
    "compute_wind_attribution_extra",
    "country_for_centroid",
    "Era5WindSample",
    "FallbackContext",
    "FallbackOutcome",
    "FallbackPlan",
    "half_ring_geometry",
    "haversine_km",
    "load_climatology",
    "measure_ring_asymmetry",
    "method_note_fragment",
    "pixel_size_warning",
    "resolve_fallback_plan",
    "sample_era5_wind_at_overpass",
    "site_buffer",
    "site_value",
    "six_step",
    "sliding_lookback_windows",
    "sparse_provenance_extra",
    "sppy_window",
    "to_score",
    "WindAnomalyDayMeasurement",
    "WindAttributabilityState",
]
