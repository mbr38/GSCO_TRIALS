"""Post-Step-8 diagnostic — exercise engine.core.repeatable_core._server_side_hf
at the same two control sites the Step 8 design discussion used.

Brasilia (Distrito Federal) and Rotterdam, NL. Both r=43.1 km buffers over
2026-02-21..2026-05-22. For each (site, indicator), report:

  * n_valid from _server_side_hf            ← THE post-Step-8 count
  * elapsed time for one server-side call
  * n_valid from the OLD .limit(100) helper  ← legacy, for comparison

Run:
    export EE_PROJECT_ID=<project>
    .venv/bin/python tools/diag_aod_ch4_step8.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ee

from engine.core.repeatable_core import (
    _per_date_site_series,
    _server_side_hf,
    background_value,
    site_buffer,
    site_value,
)


TIME_START = "2026-02-21"
TIME_END   = "2026-05-22"
Z_THRESHOLD = 2.0

ROTTERDAM = {"centre": {"lat": 51.9244, "lon":   4.4777}, "radius_km": 43.1}
BRASILIA  = {"centre": {"lat": -15.7808, "lon": -47.7968}, "radius_km": 43.1}

AOD_ASSET    = "MODIS/061/MCD19A2_GRANULES"
AOD_BAND     = "Optical_Depth_055"
AOD_QA_BAND  = "AOD_QA"
AOD_QA_MASK  = 0xF00
AOD_SCALE    = 1000.0

CH4_ASSET   = "COPERNICUS/S5P/OFFL/L3_CH4"
CH4_BAND    = "CH4_column_volume_mixing_ratio_dry_air"
CH4_SCALE   = 1113.2


def _init() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        raise SystemExit("EE_PROJECT_ID not set.")
    ee.Initialize(project=project)


def _apply_aod_qa(img):
    qa = img.select(AOD_QA_BAND)
    valid = qa.bitwiseAnd(AOD_QA_MASK).eq(0)
    return img.updateMask(valid)


def _diag_one(label: str, aoi: dict, asset: str, band: str,
              scale: float, preprocess=None) -> None:
    print()
    print("-" * 72)
    print(f"  {label}")
    print(f"  asset: {asset}")
    print(f"  band:  {band}")
    print(f"  AOI:   lat={aoi['centre']['lat']}, lon={aoi['centre']['lon']}, "
          f"r={aoi['radius_km']} km")
    print("-" * 72)

    ic = ee.ImageCollection(asset)
    if preprocess is not None:
        ic = ic.map(preprocess)
    geom = site_buffer(aoi["centre"], aoi["radius_km"])
    ic_window = (
        ic.filterDate(TIME_START, TIME_END).filterBounds(geom)
    )
    n_images = int(ic_window.size().getInfo() or 0)
    print(f"  images_after_filter_bounds = {n_images}")

    # Compute steady-state site + background (needed for HF arithmetic).
    try:
        site = site_value(aoi, ic_window, band, scale=scale)
        bg_median, bg_std = background_value(
            aoi, ic_window, band, seasonal=False, scale=scale,
        )
        print(f"  site_mean              = {site:.4g}")
        print(f"  bg_median              = {bg_median:.4g}")
        print(f"  bg_std                 = {bg_std:.4g}")
    except Exception as exc:                                # noqa: BLE001
        print(f"  site / background failed → {exc}")
        print(f"  Skipping server-side HF / legacy comparison.")
        return

    # NEW post-Step-8 path — no cap, server-side.
    t0 = time.perf_counter()
    n_valid_new, hf_new = _server_side_hf(
        aoi=aoi,
        image_collection=ic_window,
        band=band,
        bg_median=bg_median,
        bg_std=bg_std,
        z_threshold=Z_THRESHOLD,
        scale=scale,
    )
    dt_new = time.perf_counter() - t0

    # OLD .limit(100) path — for comparison only.
    t0 = time.perf_counter()
    series_old = _per_date_site_series(aoi, ic_window, band, scale=scale)
    dt_old = time.perf_counter() - t0
    n_valid_old = len(series_old)

    print(f"  ─ server-side _server_side_hf (POST-STEP-8):")
    print(f"      n_valid              = {n_valid_new}")
    print(f"      hf                   = {hf_new!r}")
    print(f"      elapsed              = {dt_new:.2f} s")
    print(f"  ─ legacy _per_date_site_series (.limit(100)):")
    print(f"      n_valid              = {n_valid_old}")
    print(f"      elapsed              = {dt_old:.2f} s")


def main() -> None:
    _init()
    print(f"Window: {TIME_START} → {TIME_END}")
    print(f"Z_THRESHOLD: {Z_THRESHOLD}")

    print()
    print("=" * 72)
    print(" BRASILIA")
    print("=" * 72)
    _diag_one(
        "AOD — Brasilia",
        BRASILIA, AOD_ASSET, AOD_BAND, AOD_SCALE,
        preprocess=_apply_aod_qa,
    )
    _diag_one(
        "CH4 — Brasilia",
        BRASILIA, CH4_ASSET, CH4_BAND, CH4_SCALE,
        preprocess=None,
    )

    print()
    print("=" * 72)
    print(" ROTTERDAM")
    print("=" * 72)
    _diag_one(
        "AOD — Rotterdam",
        ROTTERDAM, AOD_ASSET, AOD_BAND, AOD_SCALE,
        preprocess=_apply_aod_qa,
    )
    _diag_one(
        "CH4 — Rotterdam",
        ROTTERDAM, CH4_ASSET, CH4_BAND, CH4_SCALE,
        preprocess=None,
    )


if __name__ == "__main__":
    main()
