"""PM₂.₅ / PM₁₀ coverage diagnostic (v1x followup #4).

Question being investigated: PM2.5 and PM10 return None at both demo sites
(Sapezal r=5 km, Brasilia r=43.1 km) across multiple screenings. Is this:

  (a) honest "no data in window" at those lat/lons,
  (b) a band/QA filter issue,
  (c) a CAMS coverage gap at Brazilian latitudes, or
  (d) something else?

Engine-side inspection (engine/air.py L173-197, L246-261) plus the saved
JSONs in demo/saved_analyses/ already point to (d): the engine raises
IndicatorComputeError BEFORE any EE call because the demo buffers
(5 km / 43.1 km) are smaller than CAMS NRT's native pixel (44.5 km).

This script confirms that diagnosis from the EE side: it shows that CAMS
DOES return values at those latitudes once you reduce over the buffer
with bestEffort=True. We report counts + mean for two windows:

  * "demo buffer"   — exact buffer the demo uses (sub-pixel for Sapezal)
  * "oversized 100 km" — comfortably exceeds CAMS pixel, guarantees real coverage

This file is intentionally kept after the investigation — re-run it any
time someone suspects the CAMS PM bands have moved / been renamed / lost
coverage. Run:

    export EE_PROJECT_ID=<project>
    .venv/bin/python tools/diag_pm_coverage.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ee

from engine.core.repeatable_core import site_buffer


TIME_START = "2026-02-22"
TIME_END   = "2026-05-23"

# Demo sites (lat/lon copied from demo/saved_analyses/*.json).
SAPEZAL   = {"label": "Sapezal (demo, high-priority Amazon)",
             "centre": {"lat": -13.5417, "lon": -58.7642},
             "demo_radius_km": 5.0}
BRASILIA  = {"label": "Brasilia (demo, low-priority)",
             "centre": {"lat": -15.7808, "lon": -47.7968},
             "demo_radius_km": 43.1}
ROTTERDAM = {"label": "Rotterdam, NL (control)",
             "centre": {"lat": 51.9244, "lon":   4.4777},
             "demo_radius_km": 43.1}

CAMS_ASSET = "ECMWF/CAMS/NRT"
PM25_BAND  = "particulate_matter_d_less_than_25_um_surface"
PM10_BAND  = "particulate_matter_d_less_than_10_um_surface"
CAMS_SCALE_M = 44544.0          # CAMS NRT global grid (≈0.4°)
KG_M3_TO_UG_M3 = 1e9            # scale factor applied in engine/air.py


def _init() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        raise SystemExit("EE_PROJECT_ID not set.")
    ee.Initialize(project=project)


def _diag_one(site: dict, band: str) -> None:
    centre = site["centre"]
    print()
    print("-" * 76)
    print(f"  {site['label']}  —  band={band}")
    print(f"  lat={centre['lat']}, lon={centre['lon']}")
    print("-" * 76)

    ic_full = ee.ImageCollection(CAMS_ASSET).select(band)
    ic_window = ic_full.filterDate(TIME_START, TIME_END)
    n_window = int(ic_window.size().getInfo() or 0)
    print(f"  total images in {TIME_START}..{TIME_END}: {n_window}")

    for label_radius, radius_km in (
        ("demo buffer", site["demo_radius_km"]),
        ("oversized 100 km", 100.0),
    ):
        geom = site_buffer(centre, radius_km)
        ic_bounds = ic_window.filterBounds(geom)
        n_bounds = int(ic_bounds.size().getInfo() or 0)

        try:
            mean_img = ic_bounds.mean()
            info = mean_img.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geom,
                scale=CAMS_SCALE_M,
                bestEffort=True,
                maxPixels=int(1e9),
            ).getInfo()
            raw = info.get(band) if info else None
        except Exception as exc:
            raw = None
            print(f"    [{label_radius:18s}] reduceRegion raised: {exc!r}")
            continue

        if raw is None:
            value_str = "None (no pixels under buffer)"
        else:
            value_str = f"{raw * KG_M3_TO_UG_M3:.3f} µg/m³ (raw {raw:.3e} kg/m³)"
        print(f"    [{label_radius:18s}] r={radius_km:>5.1f} km  "
              f"n_bounds={n_bounds:>3d}  mean = {value_str}")


def main() -> None:
    _init()
    print(f"CAMS PM coverage diagnostic")
    print(f"Asset:   {CAMS_ASSET}")
    print(f"Bands:   {PM25_BAND}")
    print(f"         {PM10_BAND}")
    print(f"Window:  {TIME_START} .. {TIME_END}")
    print(f"CAMS native pixel: {CAMS_SCALE_M / 1000:.1f} km")

    for site in (SAPEZAL, BRASILIA, ROTTERDAM):
        for band in (PM25_BAND, PM10_BAND):
            _diag_one(site, band)
    print()
    print("=" * 76)
    print("If 'oversized 100 km' returns a real µg/m³ value at all three sites,")
    print("CAMS has coverage and the demo-site None values are caused by the")
    print("engine's buffer-vs-native-pixel guardrail (engine/air.py L251-261),")
    print("not by missing data or QA over-filtering.")


if __name__ == "__main__":
    main()
