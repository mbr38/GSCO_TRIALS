"""Diagnostic — why do `air.aod` and `ghg.ch4` report n_observations=0
over Brasilia (Distrito Federal) for 2026-02-21..2026-05-22?

Mirrors the engine's per-indicator IC build (engine/air.py, engine/ghg.py)
step by step and prints the image count after each filter. The same per-
date `reduceRegion` Mean call the engine does is replayed at the end so
we can see how many *dates with usable buffer pixels* survive — which is
what `n_observations` in the confidence_terms actually counts.

Run with the engine's EE project active:
    export EE_PROJECT_ID=<project>
    .venv/bin/python tools/diag_aod_ch4_zero_obs.py
"""

from __future__ import annotations

import os

import ee


# Brasilia / Distrito Federal AOI matching the regenerated seeded analysis.
CENTRE_LAT  = -15.7808
CENTRE_LON  = -47.7968
RADIUS_KM   = 43.1
TIME_START  = "2026-02-21"
TIME_END    = "2026-05-22"


# Engine config snapshots — keep these in lockstep with the live config so
# the diagnostic actually exercises the same band names and filters.
AOD_ASSET_ID            = "MODIS/061/MCD19A2_GRANULES"
AOD_BAND                = "Optical_Depth_055"
AOD_QA_BAND             = "AOD_QA"
AOD_QA_VALID_BIT_MASK   = 0xF00     # engine.constants.AOD_QA_VALID_BIT_MASK

CH4_ASSET_ID            = "COPERNICUS/S5P/OFFL/L3_CH4"
CH4_BAND                = "CH4_column_volume_mixing_ratio_dry_air"


def _init() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        raise SystemExit(
            "EE_PROJECT_ID not set. Run with `export EE_PROJECT_ID=<project>`."
        )
    ee.Initialize(project=project)


def _site_buffer() -> ee.Geometry:
    return (
        ee.Geometry.Point([CENTRE_LON, CENTRE_LAT])
        .buffer(distance=RADIUS_KM * 1000.0)
    )


def _count(ic: ee.ImageCollection, label: str) -> int:
    n = int(ic.size().getInfo() or 0)
    print(f"    [{label:<40}] count = {n}")
    return n


def _per_date_valid_count(
    ic: ee.ImageCollection,
    band: str,
    geom: ee.Geometry,
    scale_m: float,
    label: str,
) -> int:
    """Replays engine.core.repeatable_core._per_date_site_series semantics.

    Reduces each image to its Site_Buffer mean and counts how many dates
    return a non-null value. This is what n_observations in
    confidence_terms ultimately holds.
    """
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
        .limit(100)        # _PER_DATE_SERIES_MAX_OBSERVATIONS
        .map(reduce_to_value)
        .getInfo()
        or {}
    )
    features = fc.get("features", [])
    n_valid = sum(
        1 for f in features
        if (f.get("properties") or {}).get("value") is not None
    )
    print(
        f"    [{label:<40}] dates_with_valid_buffer_pixels = {n_valid}"
        f" / total_dates_examined = {len(features)}"
    )
    return n_valid


# ---------------------------------------------------------------------------
# AOD diagnosis
# ---------------------------------------------------------------------------

def diag_aod(geom: ee.Geometry) -> None:
    print()
    print("=" * 72)
    print(" MODIS MAIAC AOD — air.aod")
    print(f"   asset_id       = {AOD_ASSET_ID}")
    print(f"   band           = {AOD_BAND}")
    print(f"   QA band        = {AOD_QA_BAND}")
    print(f"   QA mask        = pixels where ({AOD_QA_BAND} & 0x{AOD_QA_VALID_BIT_MASK:X}) == 0")
    print("=" * 72)

    ic_raw = ee.ImageCollection(AOD_ASSET_ID)
    _count(ic_raw, "raw asset")
    ic_date = ic_raw.filterDate(TIME_START, TIME_END)
    _count(ic_date, "+ filterDate")
    ic_bounds = ic_date.filterBounds(geom)
    _count(ic_bounds, "+ filterBounds(buffer)")

    # Inspect a sample image: what bands are present? Confirms the asset
    # still exposes AOD_QA + Optical_Depth_055.
    sample = ic_bounds.first()
    sample_info = sample.getInfo()
    if sample_info:
        bands_present = [b["id"] for b in sample_info.get("bands", [])]
        print(f"    [sample image bands                       ] {bands_present[:10]}"
              f"{'...' if len(bands_present) > 10 else ''}")
        for required in (AOD_BAND, AOD_QA_BAND):
            present = required in bands_present
            print(f"    [band '{required}' present                ] {present}")
    else:
        print("    [no sample image available from filterBounds]")

    # Engine builds: ic.map(apply_aod_qa_mask) → .select(band). To count
    # how many dates survive QA, we instead apply the same mask via .map()
    # and then run the per-date reducer, which produces null for fully-
    # masked images.
    def apply_qa(img):
        qa = img.select(AOD_QA_BAND)
        valid = qa.bitwiseAnd(AOD_QA_VALID_BIT_MASK).eq(0)
        return img.updateMask(valid)

    ic_qa = ic_bounds.map(apply_qa)
    # The .map doesn't drop images — it just adds a mask. So the IC count
    # is unchanged; the relevant drop happens at reduce time.
    _count(ic_qa, "+ map(apply_aod_qa_mask)  [unchanged]")

    # Compare three reducer paths at the buffer scale (engine uses
    # scale_m=1000 for AOD):
    print()
    print("  Per-date reduceRegion mean over Site_Buffer (engine scale 1000 m):")
    _per_date_valid_count(
        ic_bounds, AOD_BAND, geom, scale_m=1000.0,
        label="NO QA mask (raw band)",
    )
    _per_date_valid_count(
        ic_qa, AOD_BAND, geom, scale_m=1000.0,
        label="WITH engine QA mask (bits 8-11 == 0)",
    )

    # Sanity: same QA mask at coarser scale — does loosening the scale
    # recover observations?
    _per_date_valid_count(
        ic_qa, AOD_BAND, geom, scale_m=5000.0,
        label="WITH QA mask, scale_m=5000",
    )

    # Also: how restrictive is "bits 8-11 == 0"? MAIAC user guide says
    # this means BEST QUALITY ONLY. Try a more permissive interpretation
    # for diagnosis purposes (NOT a fix).
    def apply_qa_permissive(img):
        # Accept anything in QA tier 0-2 (best, water, mostly cloud-free
        # ≈ bits 8-11 value <= 2).
        qa = img.select(AOD_QA_BAND)
        tier = qa.bitwiseAnd(AOD_QA_VALID_BIT_MASK).rightShift(8)
        valid = tier.lte(2)
        return img.updateMask(valid)

    ic_qa_loose = ic_bounds.map(apply_qa_permissive)
    _per_date_valid_count(
        ic_qa_loose, AOD_BAND, geom, scale_m=1000.0,
        label="WITH permissive QA (tier <= 2)",
    )


# ---------------------------------------------------------------------------
# CH4 diagnosis
# ---------------------------------------------------------------------------

def diag_ch4(geom: ee.Geometry) -> None:
    print()
    print("=" * 72)
    print(" Sentinel-5P CH4 — ghg.ch4")
    print(f"   asset_id       = {CH4_ASSET_ID}")
    print(f"   band           = {CH4_BAND}")
    print( "   QA filter      = NONE (engine applies no preprocess for CH4)")
    print("=" * 72)

    ic_raw = ee.ImageCollection(CH4_ASSET_ID)
    _count(ic_raw, "raw asset")
    ic_date = ic_raw.filterDate(TIME_START, TIME_END)
    _count(ic_date, "+ filterDate")
    ic_bounds = ic_date.filterBounds(geom)
    _count(ic_bounds, "+ filterBounds(buffer)")

    # Sample band inventory.
    sample_info = (ic_bounds.first() or ic_date.first()).getInfo()
    if sample_info:
        bands_present = [b["id"] for b in sample_info.get("bands", [])]
        print(f"    [sample image bands                       ] {bands_present}")
        print(f"    [band '{CH4_BAND}' present] "
              f"{CH4_BAND in bands_present}")
    else:
        print("    [no sample image available]")

    # Per-date reduce at the engine scale (1113.2 m grid for S5P).
    print()
    print("  Per-date reduceRegion mean over Site_Buffer (engine scale 1113 m):")
    _per_date_valid_count(
        ic_bounds, CH4_BAND, geom, scale_m=1113.2,
        label="NO QA mask (band already includes QA)",
    )

    # Compare at much coarser scale — does the L3 product just have
    # nothing in this 43 km buffer over 90 days?
    _per_date_valid_count(
        ic_bounds, CH4_BAND, geom, scale_m=10000.0,
        label="at scale_m=10000",
    )

    # Compare against `OFFL/L3_CH4_VARIANT_*` if it exists (sanity check).
    # Also surface the NRTI variant for completeness — the engine uses
    # OFFL by convention but if OFFL has zero coverage in this window,
    # NRTI may have more.
    for alt in (
        "COPERNICUS/S5P/NRTI/L3_CH4",
    ):
        try:
            alt_ic = (
                ee.ImageCollection(alt)
                .filterDate(TIME_START, TIME_END)
                .filterBounds(geom)
            )
            n = int(alt_ic.size().getInfo() or 0)
            print(f"    [variant {alt!r:<48}] count = {n}")
        except Exception as exc:                                # noqa: BLE001
            print(f"    [variant {alt!r:<48}] error: {exc}")


def main() -> None:
    _init()
    print(f"AOI: lat={CENTRE_LAT}, lon={CENTRE_LON}, radius_km={RADIUS_KM}")
    print(f"Window: {TIME_START} → {TIME_END}")
    geom = _site_buffer()
    diag_aod(geom)
    diag_ch4(geom)


if __name__ == "__main__":
    main()
