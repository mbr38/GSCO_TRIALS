"""ERA5 BLH diagnostic — Tier C2 (BLH ingestion) pre-spec investigation.

This script preserves the empirical findings from the 24 May 2026
investigation that informed the [DEFERRED] decision on Tier C2 / C1b.
It does two things:

  1. Inventory the BLH-carrying ERA5 asset (band name, scale, cadence,
     coverage). The audit-doc draft pointed at `ECMWF/ERA5_LAND/HOURLY`
     which does NOT carry boundary_layer_height (ERA5-Land's 150-band
     catalogue is surface/soil/snow/lake only). The correct asset is
     `ECMWF/ERA5/HOURLY`. Doc corrected 24 May 2026.

  2. Compute three BLH statistics over the demo window at three sites
     (Sapezal, Brasilia, Rotterdam):
       * overpass-hour mean (S5P passes at ~13:30 local solar time)
       * daily mean (averaged over 24 hourly samples then over days)
       * daily-max mean (max per day, then averaged over days)

The methodologically important finding: at tropical sites the overpass-
hour BLH is ~2.5× the daily-mean BLH (Sapezal 2.67×, Brasilia 2.53×;
Rotterdam 1.75×). Any future BLH-aware confidence adjustment must
sample BLH at satellite-overpass time, not as a daily mean — the choice
swings the inferred BL depth by a factor of 2-3 in the tropics.

Re-run any time someone re-opens Tier C2:
    export EE_PROJECT_ID=<project>
    .venv/bin/python tools/diag_blh_demo_sites.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ee


TIME_START = "2026-02-22"
TIME_END   = "2026-05-23"
BLH_ASSET  = "ECMWF/ERA5/HOURLY"
BLH_BAND   = "boundary_layer_height"
BLH_SCALE_M = 27_830.0


SITES = [
    {"label": "Sapezal (demo, tropical, lat -13.5)",
     "lat": -13.5417, "lon": -58.7642},
    {"label": "Brasilia (demo, tropical, lat -15.8)",
     "lat": -15.7808, "lon": -47.7968},
    {"label": "Rotterdam (control, temperate, lat +51.9)",
     "lat":  51.9244, "lon":   4.4777},
]


def _init() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        raise SystemExit("EE_PROJECT_ID not set.")
    ee.Initialize(project=project)


def _inventory() -> None:
    print(f"BLH ERA5 asset inventory")
    print(f"  asset:    {BLH_ASSET}")
    print(f"  band:     {BLH_BAND}")
    print(f"  scale_m:  {BLH_SCALE_M:.0f}  (~{BLH_SCALE_M/1000:.0f} km)")
    ic = ee.ImageCollection(BLH_ASSET).select(BLH_BAND)
    n = int(ic.size().getInfo() or 0)
    first = ee.Date(ic.first().get("system:time_start")).format("YYYY-MM-dd").getInfo()
    last  = ee.Date(ic.sort("system:time_start", False).first().get("system:time_start")).format("YYYY-MM-dd").getInfo()
    print(f"  n_images: {n:,d}  (hourly cadence)")
    print(f"  coverage: {first} → {last}")


def _diag_site(site: dict) -> None:
    print()
    print("-" * 76)
    print(f"  {site['label']}")
    print(f"  lat={site['lat']}, lon={site['lon']}")
    print(f"  window: {TIME_START}..{TIME_END}")
    print("-" * 76)

    pt = ee.Geometry.Point([site["lon"], site["lat"]])

    # S5P overpass time: 13:30 local solar time. UTC hour ≈ 13.5 - lon/15.
    overpass_utc_hour = round(13.5 - site["lon"] / 15.0) % 24
    print(f"  S5P overpass hour (UTC, rounded): {overpass_utc_hour:02d}:00")

    ic_full = (
        ee.ImageCollection(BLH_ASSET)
        .select(BLH_BAND)
        .filterDate(TIME_START, TIME_END)
    )

    # 1) Overpass-hour mean: filter to single UTC hour, then time-mean.
    ic_overpass = ic_full.filter(
        ee.Filter.calendarRange(overpass_utc_hour, overpass_utc_hour, "HOUR")
    )
    blh_overpass = (
        ic_overpass.mean()
        .sample(pt, BLH_SCALE_M).first()
        .get(BLH_BAND)
    )

    # 2) Daily mean (= mean of all 24 hourly samples across all days).
    blh_daily_mean = (
        ic_full.mean()
        .sample(pt, BLH_SCALE_M).first()
        .get(BLH_BAND)
    )

    # 3) Daily-max mean: per-day max across 24 hours, then mean over days.
    days_total = int(
        (ee.Date(TIME_END).millis().subtract(ee.Date(TIME_START).millis()))
        .divide(86_400_000).int().getInfo()
    )

    def _daily_max(day_offset):
        start = ee.Date(TIME_START).advance(ee.Number(day_offset), "day")
        end = start.advance(1, "day")
        return (
            ee.Image(ic_full.filterDate(start, end).max())
            .set("system:time_start", start.millis())
        )

    day_offsets = ee.List.sequence(0, days_total - 1)
    daily_max_ic = ee.ImageCollection.fromImages(day_offsets.map(_daily_max))
    blh_daily_max = (
        daily_max_ic.mean()
        .sample(pt, BLH_SCALE_M).first()
        .get(BLH_BAND)
    )

    # Single getInfo for all three.
    t0 = time.time()
    out = ee.Dictionary({
        "overpass":  ee.Number(blh_overpass),
        "daily":     ee.Number(blh_daily_mean),
        "daily_max": ee.Number(blh_daily_max),
    }).getInfo()
    elapsed = time.time() - t0

    overpass = out["overpass"]
    daily    = out["daily"]
    dmax     = out["daily_max"]
    print(f"  overpass-hour BLH mean   = {overpass:7.1f} m")
    print(f"  daily BLH mean           = {daily:7.1f} m")
    print(f"  daily-max BLH mean       = {dmax:7.1f} m")
    print(f"  ratios: overpass/daily = {overpass/daily:.2f}    "
          f"overpass/daily_max = {overpass/dmax:.2f}    "
          f"({elapsed:.1f}s)")


def main() -> None:
    _init()
    _inventory()
    for site in SITES:
        _diag_site(site)
    print()
    print("=" * 76)
    print("Headline findings (24 May 2026 investigation):")
    print("  * overpass-hour ≈ 90% of daily-max at all three sites (0.91-0.92)")
    print("  * overpass-hour 2-3× the daily-mean at tropical sites; 1.75× at temperate")
    print("  * any future BLH-aware confidence adjustment must use overpass-hour")
    print("    sampling, not daily-mean, or the inferred BL depth is biased by 2-3×")
    print()
    print("Tier C2 (BLH ingestion) currently DEFERRED — see docs/v1x_followups.md.")


if __name__ == "__main__":
    main()
