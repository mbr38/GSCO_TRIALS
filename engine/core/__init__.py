"""engine.core — reusable building blocks for the pillar modules.

Stateless functions only. Trend (`engine/core/trend.py`) and seasonality
(`engine/core/seasonality.py`) land in later milestones and are imported
lazily by `repeatable_core` so this package works without them.
"""

from engine.core.adaptive_scale import adaptive_scale_m, method_note_fragment
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
from engine.core.normalisation import to_score
from engine.core.provenance import build_provenance
from engine.core.repeatable_core import (
    anomaly_z_hf,
    background_value,
    site_value,
    six_step,
)

__all__ = [
    "adaptive_scale_m",
    "anomaly_z_hf",
    "background_ring",
    "background_value",
    "build_provenance",
    "compute_anomaly_strength_term",
    "compute_indicator_confidence",
    "compute_n_valid_term",
    "compute_pillar_confidence",
    "compute_qa_term",
    "compute_spatial_context_term",
    "method_note_fragment",
    "pixel_size_warning",
    "site_buffer",
    "site_value",
    "six_step",
    "to_score",
]
