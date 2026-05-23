"""v1x followup #1 — real-EE smoke test for the per-indicator chunk-size
lookup added to `engine.core.repeatable_core._server_side_hf`.

Three checks at Brasilia (Distrito Federal, 43.1 km buffer, 90-day window):

  1. `air.no2` with chunk_days=90 (single-chunk fast path) — measure time.
  2. `air.no2` with chunk_days=10 (legacy chunked path) — measure time.
     Compare n_valid + n_hot between the two: they MUST match (regression
     check that the fast path produces the same answer as chunking would).
  3. `air.aod` with chunk_days=10 (unchanged from pre-fix) — measure time.
     Should be ~10–15s (matches Step 8 Option-A diagnostic baseline).

The chunk_days value is swapped at runtime via direct mutation of
`engine.constants.SERVER_SIDE_HF_CHUNK_DAYS_PER_INDICATOR`. Both runs
read from the same module-level dict, so swapping the value between
runs is faithful to how the production lookup would dispatch.

Run:
    export EE_PROJECT_ID=<project>
    .venv/bin/python tools/smoke_chunk_size_lookup.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ee

from engine import constants
from engine.core.repeatable_core import (
    _server_side_hf,
    background_value,
    site_buffer,
    site_value,
)


BRASILIA  = {"centre": {"lat": -15.7808, "lon": -47.7968}, "radius_km": 43.1}
WINDOW    = ("2026-02-22", "2026-05-23")
Z_THRESHOLD = 2.0


def _init() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        raise SystemExit("EE_PROJECT_ID not set.")
    ee.Initialize(project=project)


def _run_one(label: str, asset: str, band: str, scale: float,
             indicator_id: str) -> tuple[int, float | None, float]:
    """Run `_server_side_hf` once and return (n_valid, hf, elapsed_seconds)."""
    geom = site_buffer(BRASILIA["centre"], BRASILIA["radius_km"])
    ic_window = (
        ee.ImageCollection(asset)
        .filterDate(WINDOW[0], WINDOW[1])
        .filterBounds(geom)
    )
    n_images = int(ic_window.size().getInfo() or 0)

    site = site_value(BRASILIA, ic_window, band, scale=scale)
    bg_median, bg_std = background_value(
        BRASILIA, ic_window, band, seasonal=False, scale=scale,
    )

    t0 = time.perf_counter()
    n_valid, hf = _server_side_hf(
        aoi=BRASILIA,
        image_collection=ic_window,
        band=band,
        bg_median=bg_median,
        bg_std=bg_std,
        z_threshold=Z_THRESHOLD,
        scale=scale,
        time_range=WINDOW,
        indicator_id=indicator_id,
    )
    dt = time.perf_counter() - t0

    chunk_days = constants.SERVER_SIDE_HF_CHUNK_DAYS_PER_INDICATOR.get(
        indicator_id, constants.SERVER_SIDE_HF_CHUNK_DAYS_DEFAULT,
    )
    print(
        f"  {label:<30}  chunk_days={chunk_days:>3}  "
        f"images={n_images:>5}  n_valid={n_valid:>4}  "
        f"hf={hf!s:>6}  elapsed={dt:6.2f}s"
    )
    return n_valid, hf, dt


def main() -> None:
    _init()
    print(f"Brasilia 43.1 km, window {WINDOW[0]} → {WINDOW[1]}")
    print("=" * 80)

    print()
    print("1. air.no2 with chunk_days=90 (post-fix single-chunk fast path)")
    print("-" * 80)
    n_valid_fast, hf_fast, dt_fast = _run_one(
        "air.no2 (fast, single-chunk)",
        "COPERNICUS/S5P/OFFL/L3_NO2", "NO2_column_number_density",
        1113.2, "air.no2",
    )

    print()
    print("2. air.no2 with chunk_days=10 (pre-fix chunked path, for regression check)")
    print("-" * 80)
    # Temporarily override the lookup to force the chunked path.
    saved = constants.SERVER_SIDE_HF_CHUNK_DAYS_PER_INDICATOR.get("air.no2")
    constants.SERVER_SIDE_HF_CHUNK_DAYS_PER_INDICATOR["air.no2"] = 10
    try:
        n_valid_slow, hf_slow, dt_slow = _run_one(
            "air.no2 (chunked, legacy)",
            "COPERNICUS/S5P/OFFL/L3_NO2", "NO2_column_number_density",
            1113.2, "air.no2",
        )
    finally:
        if saved is None:
            del constants.SERVER_SIDE_HF_CHUNK_DAYS_PER_INDICATOR["air.no2"]
        else:
            constants.SERVER_SIDE_HF_CHUNK_DAYS_PER_INDICATOR["air.no2"] = saved

    print()
    print("3. air.aod with chunk_days=10 (unchanged, baseline)")
    print("-" * 80)
    n_valid_aod, hf_aod, dt_aod = _run_one(
        "air.aod (chunked, unchanged)",
        "MODIS/061/MCD19A2_GRANULES", "Optical_Depth_055",
        1000.0, "air.aod",
    )

    print()
    print("=" * 80)
    print(" Regression check + verdict")
    print("=" * 80)
    print(f"  air.no2 fast n_valid: {n_valid_fast}")
    print(f"  air.no2 slow n_valid: {n_valid_slow}")
    if n_valid_fast == n_valid_slow:
        print(f"  ✓ n_valid matches between fast and slow paths")
    else:
        print(f"  ✗ MISMATCH — regression detected")

    print(f"  air.no2 fast hf:      {hf_fast}")
    print(f"  air.no2 slow hf:      {hf_slow}")
    print()
    print(f"  Timing (lower is better for fast path):")
    print(f"    air.no2 fast:  {dt_fast:6.2f}s")
    print(f"    air.no2 slow:  {dt_slow:6.2f}s")
    print(f"    speedup:       {dt_slow / dt_fast:.2f}×" if dt_fast > 0 else "    speedup: n/a")
    print(f"    air.aod:       {dt_aod:6.2f}s  (chunked baseline; should be ~10-15s)")


if __name__ == "__main__":
    main()
