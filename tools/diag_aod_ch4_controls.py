"""Control diagnostics — disambiguate why air.aod and ghg.ch4 returned
n_observations=0 over Brasilia for 2026-02-21..2026-05-22.

Two control tests:

1. Rotterdam, NL (51.9244, 4.4777) at the same buffer/window/scale as the
   Brasilia run. Northern-hemisphere temperate site — if AOD and CH4 are
   well-populated here but not at Brasilia, the wet-season-masking
   hypothesis (cause 2) holds.

2. Brasilia centre point-sample. Skip the buffer reduce; just sample the
   raw band at the centre point of the FIRST image in each filtered
   collection. If the point-sample returns a value but the buffer mean
   returned None, the bug is in the buffer reducer (geometry/scale/CRS).
   If the point-sample also returns None, the band is masked at that
   pixel — confirming the asset-level masking hypothesis.

Run:
    export EE_PROJECT_ID=<project>
    .venv/bin/python tools/diag_aod_ch4_controls.py
"""

from __future__ import annotations

import os

import ee


TIME_START  = "2026-02-21"
TIME_END    = "2026-05-22"

# Rotterdam, NL — match Brasilia buffer size for apples-to-apples comparison.
ROTTERDAM_LAT  = 51.9244
ROTTERDAM_LON  = 4.4777
ROTTERDAM_RAD  = 43.1

# Brasilia centre (for the point-sample test).
BRASILIA_LAT   = -15.7808
BRASILIA_LON   = -47.7968
BRASILIA_RAD   = 43.1

AOD_ASSET_ID            = "MODIS/061/MCD19A2_GRANULES"
AOD_BAND                = "Optical_Depth_055"
AOD_QA_BAND             = "AOD_QA"
AOD_QA_VALID_BIT_MASK   = 0xF00
AOD_SCALE_M             = 1000.0

CH4_ASSET_ID            = "COPERNICUS/S5P/OFFL/L3_CH4"
CH4_BAND                = "CH4_column_volume_mixing_ratio_dry_air"
CH4_SCALE_M             = 1113.2


def _init() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        raise SystemExit("EE_PROJECT_ID not set.")
    ee.Initialize(project=project)


def _buffer(lat: float, lon: float, radius_km: float) -> ee.Geometry:
    return ee.Geometry.Point([lon, lat]).buffer(distance=radius_km * 1000.0)


def _apply_aod_qa(img: ee.Image) -> ee.Image:
    qa = img.select(AOD_QA_BAND)
    valid = qa.bitwiseAnd(AOD_QA_VALID_BIT_MASK).eq(0)
    return img.updateMask(valid)


def _per_date_valid_count(
    ic: ee.ImageCollection,
    band: str,
    geom: ee.Geometry,
    scale_m: float,
    limit: int = 100,
) -> tuple[int, int]:
    """Returns (dates_with_valid_buffer_pixels, total_dates_examined)."""
    def reduce_to_value(image):
        v = image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=scale_m,
            bestEffort=True,
            maxPixels=int(1e9),
        ).get(band)
        return ee.Feature(None, {"value": v})

    fc = (
        ic.select(band)
        .limit(limit)
        .map(reduce_to_value)
        .getInfo()
        or {}
    )
    features = fc.get("features", [])
    n_valid = sum(
        1 for f in features
        if (f.get("properties") or {}).get("value") is not None
    )
    return n_valid, len(features)


# ---------------------------------------------------------------------------
# Control 1 — Rotterdam (Northern-hemisphere temperate)
# ---------------------------------------------------------------------------

def control_rotterdam() -> None:
    print()
    print("=" * 72)
    print(f" CONTROL 1 — Rotterdam, NL ({ROTTERDAM_LAT}, {ROTTERDAM_LON})  r={ROTTERDAM_RAD} km")
    print(f"   window: {TIME_START} → {TIME_END}")
    print("=" * 72)

    geom = _buffer(ROTTERDAM_LAT, ROTTERDAM_LON, ROTTERDAM_RAD)

    # AOD — match engine: filter → map(QA mask) → reduce, plus a "no QA"
    # control to separate the two effects.
    aod_ic = (
        ee.ImageCollection(AOD_ASSET_ID)
        .filterDate(TIME_START, TIME_END)
        .filterBounds(geom)
    )
    aod_n = int(aod_ic.size().getInfo() or 0)
    print(f"  AOD images after filterBounds: {aod_n}")

    aod_raw_valid, aod_raw_total = _per_date_valid_count(
        aod_ic, AOD_BAND, geom, AOD_SCALE_M,
    )
    print(f"  AOD  WITHOUT engine QA mask:  "
          f"dates_with_valid_pixels = {aod_raw_valid} / {aod_raw_total}")

    aod_qa_valid, aod_qa_total = _per_date_valid_count(
        aod_ic.map(_apply_aod_qa), AOD_BAND, geom, AOD_SCALE_M,
    )
    print(f"  AOD  WITH    engine QA mask:  "
          f"dates_with_valid_pixels = {aod_qa_valid} / {aod_qa_total}")

    # CH4 — engine applies no preprocess.
    ch4_ic = (
        ee.ImageCollection(CH4_ASSET_ID)
        .filterDate(TIME_START, TIME_END)
        .filterBounds(geom)
    )
    ch4_n = int(ch4_ic.size().getInfo() or 0)
    print(f"  CH4 images after filterBounds: {ch4_n}")

    ch4_valid, ch4_total = _per_date_valid_count(
        ch4_ic, CH4_BAND, geom, CH4_SCALE_M,
    )
    print(f"  CH4  (engine applies no QA):  "
          f"dates_with_valid_pixels = {ch4_valid} / {ch4_total}")


# ---------------------------------------------------------------------------
# Control 2 — Brasilia centre point-sample
# ---------------------------------------------------------------------------

def control_brasilia_point_sample() -> None:
    print()
    print("=" * 72)
    print(f" CONTROL 2 — Brasilia centre point-sample"
          f" ({BRASILIA_LAT}, {BRASILIA_LON})")
    print(f"   window: {TIME_START} → {TIME_END}")
    print("=" * 72)

    centre_point = ee.Geometry.Point([BRASILIA_LON, BRASILIA_LAT])
    centre_buffer = _buffer(BRASILIA_LAT, BRASILIA_LON, BRASILIA_RAD)

    # ----- AOD point-sample -----
    aod_ic = (
        ee.ImageCollection(AOD_ASSET_ID)
        .filterDate(TIME_START, TIME_END)
        .filterBounds(centre_buffer)
    )
    aod_first = aod_ic.first()
    aod_first_info = aod_first.getInfo()
    if not aod_first_info:
        print("  AOD: no first image — empty collection.")
    else:
        ts = aod_first_info.get("properties", {}).get("system:time_start")
        print(f"  AOD first image system:time_start = {ts}")

        sampled = aod_first.sample(
            region=centre_point, scale=AOD_SCALE_M,
        ).getInfo()
        features = sampled.get("features", [])
        print(f"  AOD point-sample feature count = {len(features)}")
        if features:
            value = features[0]["properties"].get(AOD_BAND)
            print(f"  AOD  Optical_Depth_055 at centre = {value}")
            # Also surface the AOD_QA byte at the same pixel for context.
            qa = features[0]["properties"].get(AOD_QA_BAND)
            if qa is not None:
                bits_8_11 = (qa >> 8) & 0xF
                print(f"  AOD  AOD_QA at centre = {qa} "
                      f"(bits 8-11 = {bits_8_11}; engine requires 0)")
        else:
            print("  AOD  no feature returned — band masked at this pixel.")

    # ----- CH4 point-sample -----
    ch4_ic = (
        ee.ImageCollection(CH4_ASSET_ID)
        .filterDate(TIME_START, TIME_END)
        .filterBounds(centre_buffer)
    )
    ch4_first = ch4_ic.first()
    ch4_first_info = ch4_first.getInfo()
    if not ch4_first_info:
        print("  CH4: no first image — empty collection.")
    else:
        ts = ch4_first_info.get("properties", {}).get("system:time_start")
        print(f"  CH4 first image system:time_start = {ts}")

        sampled = ch4_first.sample(
            region=centre_point, scale=CH4_SCALE_M,
        ).getInfo()
        features = sampled.get("features", [])
        print(f"  CH4 point-sample feature count = {len(features)}")
        if features:
            value = features[0]["properties"].get(CH4_BAND)
            print(f"  CH4 mixing_ratio at centre = {value}")
        else:
            print("  CH4  no feature returned — band masked at this pixel.")


def main() -> None:
    _init()
    print(f"Window: {TIME_START} → {TIME_END}")
    control_rotterdam()
    control_brasilia_point_sample()


if __name__ == "__main__":
    main()
