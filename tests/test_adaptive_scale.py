"""Pure-Python tests for engine.core.adaptive_scale (M-ADAPTIVE-SCALE).

No real Earth Engine — every test stubs the `geometry.area().getInfo()`
chain with a synthetic value, so the math is exercised in isolation. The
EE-touching path (Nature pillar reducers passing the adaptive scale to
reduceRegion / frequencyHistogram) is covered by tests/test_nature.py.
"""

# M-ADAPTIVE-SCALE
from __future__ import annotations

import math

import pytest

from engine.core.adaptive_scale import (
    _DEFAULT_TARGET_PIXELS,
    adaptive_scale_m,
    method_note_fragment,
)


class _FakeGeometry:
    """Minimal stand-in for ``ee.Geometry`` that satisfies the helper.

    Reproduces only the chain the helper consumes:
    ``geometry.area(maxError=100).getInfo() -> float``.
    """

    def __init__(self, area_m2: float):
        self._area = area_m2

    def area(self, maxError: float = 100):  # noqa: N803 — match EE camelCase.
        outer = self

        class _AreaResult:
            def getInfo(self_inner):  # noqa: N802 — match EE camelCase.
                return outer._area

        return _AreaResult()


# ---------------------------------------------------------------------------
# adaptive_scale_m — math
# ---------------------------------------------------------------------------

def test_small_aoi_returns_native_scale():
    """5 km buffer (area ≈ 78.5 km²) with 10 m native → ideal_scale ≈ 8.9 m,
    so the helper clamps up to the 10 m native. Small-AOI behaviour is
    unchanged from the pre-milestone state.
    """
    area_m2 = math.pi * (5_000.0 ** 2)  # π·r² with r in metres.
    geom = _FakeGeometry(area_m2)

    scale = adaptive_scale_m(geom, native_scale_m=10.0)

    assert scale == 10.0


def test_region_aoi_returns_adaptive_scale():
    """150 km buffer (area ≈ 70 686 km²) with 10 m native → adaptive scale
    coarsens to ~265 m. The formula yields sqrt(7.07e10 / 1e6) ≈ 265.9.
    """
    area_m2 = math.pi * (150_000.0 ** 2)
    geom = _FakeGeometry(area_m2)

    scale = adaptive_scale_m(geom, native_scale_m=10.0)

    assert scale > 10.0
    # Allow a small numerical tolerance — exact = sqrt(area / target).
    expected = math.sqrt(area_m2 / _DEFAULT_TARGET_PIXELS)
    assert scale == pytest.approx(expected, rel=1e-9)
    assert 260.0 < scale < 270.0


def test_capped_aoi_returns_largest_adaptive_scale():
    """400 km buffer (area ≈ 502 655 km²) with 10 m native → ≈ 709 m. The
    400 km radius is the cap demo/regions.py applies to the largest
    Brazilian states, so this is the worst-case the engine sees in v1.
    """
    area_m2 = math.pi * (400_000.0 ** 2)
    geom = _FakeGeometry(area_m2)

    scale = adaptive_scale_m(geom, native_scale_m=10.0)

    expected = math.sqrt(area_m2 / _DEFAULT_TARGET_PIXELS)
    assert scale == pytest.approx(expected, rel=1e-9)
    assert 700.0 < scale < 720.0


def test_native_scale_floor_respected_for_coarse_asset_small_aoi():
    """1 km buffer (area ≈ 3.14 km²) with 250 m native → ideal_scale ≈ 1.8 m,
    well under the asset's native pixel. The helper must clamp to 250 m,
    not silently *upsample* the asset.
    """
    area_m2 = math.pi * (1_000.0 ** 2)
    geom = _FakeGeometry(area_m2)

    scale = adaptive_scale_m(geom, native_scale_m=250.0)

    assert scale == 250.0


def test_custom_target_pixels_shifts_scale_predictably():
    """Passing target_pixels=2_000_000 doubles the pixel budget → ideal
    scale halves by sqrt(2). At a region-scale AOI where adaptive kicks in,
    the returned scale must drop accordingly (still ≥ native).
    """
    area_m2 = math.pi * (150_000.0 ** 2)
    geom = _FakeGeometry(area_m2)

    default = adaptive_scale_m(geom, native_scale_m=10.0)
    doubled = adaptive_scale_m(geom, native_scale_m=10.0, target_pixels=2_000_000)

    # doubled-budget scale should be default / sqrt(2).
    assert doubled == pytest.approx(default / math.sqrt(2.0), rel=1e-9)


def test_hansen_native_scale_kicks_in_at_intermediate_aoi():
    """At a 30 km buffer (area ≈ 2 827 km²) with Hansen's 30 m native, the
    ideal scale is sqrt(2.8e9 / 1e6) ≈ 53 m — above native, so Hansen does
    coarsen even at MNC-ish scales. Pinning this so the behaviour is
    visible (it's why every Nature reducer threads the helper, not just
    the DW ones).
    """
    area_m2 = math.pi * (30_000.0 ** 2)
    geom = _FakeGeometry(area_m2)

    scale = adaptive_scale_m(geom, native_scale_m=30.0)

    expected = math.sqrt(area_m2 / _DEFAULT_TARGET_PIXELS)
    assert scale == pytest.approx(expected, rel=1e-9)
    assert scale > 30.0


# ---------------------------------------------------------------------------
# method_note_fragment — wording
# ---------------------------------------------------------------------------

def test_method_note_fragment_no_coarsening_reports_native():
    """When the effective scale equals native, the fragment surfaces
    "scale=<n>m (native)" — small AOIs hit this branch and the provenance
    UI shows reviewers that no coarsening happened.
    """
    fragment = method_note_fragment(effective_scale_m=10.0, native_scale_m=10.0)
    assert fragment == "scale=10m (native)"


def test_method_note_fragment_coarsened_reports_adaptive_with_target():
    """When the effective scale exceeds native, the fragment carries the
    adaptive scale, the native scale, and the target-pixel budget. The
    Rio de Janeiro screening should land roughly in this shape.
    """
    fragment = method_note_fragment(effective_scale_m=265.0, native_scale_m=10.0)
    assert fragment == "scale=265m (adaptive; native 10m; target ~1.0M px)"


def test_method_note_fragment_treats_tiny_float_fuzz_as_native():
    """Float arithmetic can produce ``scale=10.0000001`` instead of exact
    10.0 — the fragment must still report "native". Pin the 1 % tolerance.
    """
    fragment = method_note_fragment(
        effective_scale_m=10.0 * 1.005,  # within the 1.01 tolerance.
        native_scale_m=10.0,
    )
    assert fragment == "scale=10m (native)"


def test_method_note_fragment_custom_target_pixels_surfaced():
    """Passing a non-default target_pixels surfaces a non-default
    "target ~X.XM px" suffix so reviewers see the budget that was used.
    """
    fragment = method_note_fragment(
        effective_scale_m=500.0,
        native_scale_m=10.0,
        target_pixels=4_000_000,
    )
    assert fragment == "scale=500m (adaptive; native 10m; target ~4.0M px)"
