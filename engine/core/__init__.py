"""engine.core — reusable building blocks for the pillar modules.

Stateless functions only. Trend (`engine/core/trend.py`) and seasonality
(`engine/core/seasonality.py`) land in later milestones and are imported
lazily by `repeatable_core` so this package works without them.
"""

from engine.core.buffers import (
    background_ring,
    pixel_size_warning,
    site_buffer,
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
    "anomaly_z_hf",
    "background_ring",
    "background_value",
    "build_provenance",
    "pixel_size_warning",
    "site_buffer",
    "site_value",
    "six_step",
    "to_score",
]
