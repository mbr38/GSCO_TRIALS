"""Adaptive reduction-scale helper (M-ADAPTIVE-SCALE).

Nature pillar reducers operate at the asset's native scale by default
(10 m for Dynamic World, 30 m for Hansen). At region-scale AOIs this
produces hundreds of millions of pixels per reduction, which stalls
the EE planner. This helper picks a coarsened scale based on AOI area,
keeping the pixel count bounded at ~1M regardless of AOI size.

Behaviour:
  - For small AOIs (e.g. MNC 5 km buffers), the formula yields a scale
    well below the asset's native scale. The helper clamps to native,
    so high-fidelity reductions are preserved for small AOIs.
  - For region-scale AOIs (Brazilian states, 100-400 km radii), the
    formula yields a coarsened scale that bounds pixel count.

Formula:
    target_scale_m = max(native_scale_m, sqrt(area_m2 / target_pixels))

target_pixels defaults to 1_000_000 — well within EE's 10M ceiling
for ``reduceRegion`` default tile sizes, with safety margin for the
heaviest Nature reductions (DW class histogram, habitat conversion
double composites).

Provenance contract:
  Callers should record the effective scale via ``method_note`` in
  their canonical 11-field provenance block. Helper exposes
  ``method_note_fragment`` to build a consistent string.
"""

# M-ADAPTIVE-SCALE
from __future__ import annotations

import math
from typing import Final

import ee


_DEFAULT_TARGET_PIXELS: Final[float] = 1_000_000.0


def adaptive_scale_m(
    geometry: ee.Geometry,
    native_scale_m: float,
    target_pixels: float = _DEFAULT_TARGET_PIXELS,
) -> float:
    """Pick a reduction scale (in metres) bounded by the pixel target.

    Args:
        geometry: the AOI being reduced over.
        native_scale_m: the asset's native pixel size in metres.
        target_pixels: max pixels for the reduction.
            Default ~1M, well within EE's 10M ceiling.

    Returns:
        A scale in metres at least as coarse as ``native_scale_m``.
        For small AOIs returns ``native_scale_m`` (no coarsening).
        For large AOIs returns a scale that bounds pixel count.

    One EE round-trip (geometry.area().getInfo()) per call.
    """
    area_m2 = geometry.area(maxError=100).getInfo()
    ideal_scale = math.sqrt(area_m2 / target_pixels)
    return max(native_scale_m, ideal_scale)


def method_note_fragment(
    effective_scale_m: float,
    native_scale_m: float,
    target_pixels: float = _DEFAULT_TARGET_PIXELS,
) -> str:
    """Build a consistent method_note fragment documenting the scale.

    Two shapes depending on whether the adaptive scale kicked in:
    - No coarsening (small AOI): "scale=<n>m (native)"
    - Coarsened (large AOI):     "scale=<m>m (adaptive; native <n>m; target ~1M px)"

    Caller appends to existing method_note text, separated by '; '.
    """
    if effective_scale_m <= native_scale_m * 1.01:  # small float fuzz.
        return f"scale={native_scale_m:.0f}m (native)"
    return (
        f"scale={effective_scale_m:.0f}m (adaptive; "
        f"native {native_scale_m:.0f}m; target ~{target_pixels/1_000_000:.1f}M px)"
    )
