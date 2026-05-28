"""Real-EE smoke test for engine.core.wind (M-WIND-A1 v2.0).

The pytest suite covers wind's pure-math and sparse-gate logic without
hitting Earth Engine. This script is the EE counterpart: it exercises the
parts that ONLY break against a real EE backend — geometry constructor
parameter routing, per-day reduction batching, and ERA5 sampling.

History — what this would have caught
--------------------------------------

The M-WIND-A1 v2.0 demo regen (28 May 2026) revealed a silent-degrade bug:

    ee.ee_exception.EEException: Projection: Argument 'crs': Invalid type.
    Expected type: String. Actual type: Boolean. Actual value: true

caused by ``ee.Geometry.Polygon(coords, geodesic=True, evenOdd=False)`` —
the EE Python SDK version pinned in requirements.txt routes the
``geodesic`` keyword to ``proj`` (the second positional arg), which
expects a CRS string. The constructor never raised at construction
time (EE is lazy); the exception surfaced only when
``measure_ring_asymmetry`` called ``.getInfo()`` on the batched
ee.List. Because six_step wraps the wind invocation in a
``try/except → sparse`` for graceful degradation (WA1: wind never
crashes the indicator), the bug presented as "every wind invocation
returns sparse" rather than as an exception.

The fix uses ``ee.Geometry({"type": "Polygon", ..., "geodesic": True})``
which has no positional/keyword ambiguity. This smoke script forces
``.getInfo()`` on the geometry so any future positional/keyword
regression fails loudly here instead of silently degrading the demo.

Run via:

    EE_PROJECT_ID=supply-chain-observatory .venv/bin/python \\
        tools/smoke_wind_module.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ee

from engine.air import AIR_POLLUTANT_CONFIG, _build_image_collection
from engine.core.era5 import (
    compute_overpass_utc_hour,
    sample_era5_wind_at_overpass,
)
from engine.core.wind import (
    compute_wind_attribution_extra,
    half_ring_geometry,
)


_SAPEZAL_CENTRE = {"lat": -13.5417, "lon": -58.7642}
_SAPEZAL_TIME_RANGE = ("2026-02-22", "2026-05-23")


def _init_ee() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        sys.exit("EE_PROJECT_ID not set; aborting.")
    ee.Initialize(project=project)


def smoke_overpass() -> None:
    print("=== compute_overpass_utc_hour (pure) ===")
    for lon, expected in [(0.0, 14), (-60.0, 18), (120.0, 6), (-58.7642, 17)]:
        got = compute_overpass_utc_hour(lon)
        ok = "✓" if got == expected else "✗"
        print(f"  {ok} lon={lon:>8.2f} → {got} (expected {expected})")


def smoke_half_ring_geometry() -> None:
    """The regression test for the geodesic-kwarg bug.

    Builds a half-ring and forces ``.bounds().getInfo()`` to materialise
    it on the EE side. Pre-fix this raised the "Argument 'crs'" EEException.
    """
    print("\n=== half_ring_geometry — getInfo round-trip ===")
    for direction in (0.0, 90.0, 180.0, 270.0):
        geom = half_ring_geometry(
            centre=_SAPEZAL_CENTRE,
            r_site_km=5.0,
            r_background_km=25.0,
            direction_deg=direction,
        )
        bounds = geom.bounds().getInfo()
        # Bounds is a GeoJSON polygon; just confirm it materialised.
        coords = bounds.get("coordinates", [])
        n_vertices = len(coords[0]) if coords else 0
        print(
            f"  direction={direction:>6.1f}°  bounds has {n_vertices} bbox vertices  ✓"
        )


def smoke_era5_sampler() -> None:
    print("\n=== sample_era5_wind_at_overpass — batched fetch ===")
    samples = sample_era5_wind_at_overpass(
        centre=_SAPEZAL_CENTRE,
        anomaly_dates_utc=[
            "2026-04-01", "2026-04-02", "2026-04-03",
            "2026-04-04", "2026-04-05", "2026-04-06",
        ],
    )
    for s in samples:
        print(
            f"  {s.date_utc}  speed={s.speed_ms:.2f} m/s  "
            f"dir={s.direction_deg:>6.1f}°  ok={s.coverage_ok}"
        )


def smoke_full_attribution() -> None:
    """End-to-end: AAI at Sapezal, 6 anomaly days.

    Pre-fix this returned ``sparse`` (exception swallowed in six_step's
    try/except). Post-fix it returns a real state (high / moderate / low).
    """
    print("\n=== compute_wind_attribution_extra — AAI@Sapezal, 6 days ===")
    cfg = AIR_POLLUTANT_CONFIG["aai"]
    ic_window = _build_image_collection(cfg).filterDate(*_SAPEZAL_TIME_RANGE)
    extra = compute_wind_attribution_extra(
        centre=_SAPEZAL_CENTRE,
        r_site_km=5.0,
        r_background_km=25.0,
        image_collection=ic_window,
        band=cfg.band,
        scale=cfg.scale_m,
        anomaly_dates_utc=[
            "2026-04-01", "2026-04-02", "2026-04-03",
            "2026-04-04", "2026-04-05", "2026-04-06",
        ],
        wind_data_window=_SAPEZAL_TIME_RANGE,
        ring_land_fraction=1.0,
    )
    for k, v in extra.items():
        print(f"  {k:32s} = {v}")
    state = extra["wind_attributability_state"]
    if state == "sparse":
        sys.exit(
            "\n  ✗ FAIL: end-to-end returned sparse — the silent-degrade "
            "regression has re-fired. Check for new positional/keyword "
            "ambiguity in ee.Geometry construction or new EE-side errors."
        )
    print(f"\n  ✓ end-to-end state = {state!r} — wind module operational.")


def main() -> None:
    _init_ee()
    smoke_overpass()
    smoke_half_ring_geometry()
    smoke_era5_sampler()
    smoke_full_attribution()
    print("\nAll wind-module smoke checks passed.")


if __name__ == "__main__":
    main()
