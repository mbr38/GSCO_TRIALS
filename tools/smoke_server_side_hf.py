"""Pre-flight smoke test for engine.core.repeatable_core._server_side_hf.

Two checks before running the real Brasilia + Rotterdam diagnostic:

  1. Pure import check — _server_side_hf is reachable; no Python errors.
  2. EE compile check — call it against a tiny collection (one S5P NO2
     image-day over Rotterdam) and confirm:
       - reduceColumns(ee.Reducer.sum().repeat(2), ...) compiles
       - .getInfo() returns the expected shape
       - server-side If / Number arithmetic doesn't crash
       - the (n_valid, hf) tuple has sane types

If anything here fails, STOP — there's a real bug in the EE arithmetic
that the test suite doesn't surface.

Run:
    export EE_PROJECT_ID=<project>
    .venv/bin/python tools/smoke_server_side_hf.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Make `engine` importable when running from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ee


def _init() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        raise SystemExit("EE_PROJECT_ID not set.")
    ee.Initialize(project=project)


def main() -> None:
    # Check 1 — import path.
    print("[1] Import check ... ", end="", flush=True)
    from engine.core.repeatable_core import _server_side_hf  # noqa: F401
    from engine.core import six_step  # noqa: F401
    print("OK")

    _init()

    # Check 2 — EE compile + getInfo against a tiny collection.
    print("[2] EE compile check (tiny collection) ... ", end="", flush=True)
    aoi = {
        "centre":    {"lat": 51.9244, "lon": 4.4777},
        "radius_km": 10.0,   # small buffer — bounded compute cost
    }
    # NO2 over Rotterdam for 2 days — well-populated, short window.
    ic = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_NO2")
        .filterDate("2026-03-01", "2026-03-03")
        .filterBounds(
            ee.Geometry.Point([aoi["centre"]["lon"], aoi["centre"]["lat"]])
            .buffer(aoi["radius_km"] * 1000.0)
        )
    )
    n_images = int(ic.size().getInfo() or 0)

    # Plausible-baseline NO2 column for Western Europe (mol/m²): ~5e-5.
    # bg_std arbitrary but > 0 so the bg_std_degenerate branch is exercised
    # under "happy path".
    t0 = time.perf_counter()
    n_valid, hf = _server_side_hf(
        aoi=aoi,
        image_collection=ic,
        band="NO2_column_number_density",
        bg_median=5e-5,
        bg_std=1e-5,
        z_threshold=2.0,
        scale=1113.2,
    )
    dt = time.perf_counter() - t0

    print("OK")
    print(f"    images_in_collection = {n_images}")
    print(f"    n_valid              = {n_valid!r}  (type: {type(n_valid).__name__})")
    print(f"    hf                   = {hf!r}  (type: {type(hf).__name__})")
    print(f"    elapsed              = {dt:.2f} s")

    assert isinstance(n_valid, int), f"n_valid should be int, got {type(n_valid)}"
    assert hf is None or isinstance(hf, float), (
        f"hf should be float|None, got {type(hf)}"
    )
    if hf is not None:
        assert 0.0 <= hf <= 1.0, f"hf out of [0,1]: {hf}"

    # Check 3 — degenerate bg_std path.
    print("[3] EE compile check (bg_std=0 degenerate path) ... ", end="", flush=True)
    t0 = time.perf_counter()
    n_valid_deg, hf_deg = _server_side_hf(
        aoi=aoi,
        image_collection=ic,
        band="NO2_column_number_density",
        bg_median=5e-5,
        bg_std=0.0,                   # degenerate
        z_threshold=2.0,
        scale=1113.2,
    )
    dt_deg = time.perf_counter() - t0
    print("OK")
    print(f"    n_valid (bg_std=0)   = {n_valid_deg!r}")
    print(f"    hf      (bg_std=0)   = {hf_deg!r}  (expected None)")
    print(f"    elapsed              = {dt_deg:.2f} s")
    assert hf_deg is None, "hf must be None on degenerate background"

    print()
    print("Pre-flight ALL OK.")


if __name__ == "__main__":
    main()
