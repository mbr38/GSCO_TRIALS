"""Dynamic World class_confidence diagnostic (v1x followup #6).

Question being investigated: nature.dw.class_confidence lands at 0.47-0.49 at
both demo sites — meaningfully lower than other Nature sub-scores. Is this:

  (a) genuine output of underlying DW probability fields,
  (b) misinterpretation of what 'class_confidence' should represent,
  (c) clipping/scaling bug, or
  (d) something else?

Engine-side inspection (engine/nature.py L635-640) already answers this: the
field is a documented placeholder that returns the dominant class's PIXEL
FRACTION (count of dominant-class pixels / total pixels), not any DW
probability. The TODO at the same site names the intended implementation:
'mean(prob_<dominant>) over the buffer' using DW's nine probability bands.

This script quantifies what the *intended* implementation would produce so
the team can size the fix. For each AOI:

  * Mean dominant-class probability (per-pixel argmax probability, averaged
    over the buffer)                                                — what
                                                                      class_confidence
                                                                      *should*
                                                                      be.
  * Distribution histogram of per-pixel max probability
  * Mean per-class probability across the buffer (all 9 bands).

Demo sites are compared against two homogeneous controls:
  * Open Atlantic (water, ~100% pure)
  * Sahara core (bare, ~100% pure)

If homogeneous controls return mean max-prob ≈ 0.9 and demo sites return
mean max-prob ≈ 0.6-0.7, that's evidence that the proper implementation
would surface a real "landscape ambiguity" signal that the current pixel-
fraction placeholder doesn't.

Left in place per task instructions for future regression. Run:

    export EE_PROJECT_ID=<project>
    .venv/bin/python tools/diag_dw_class_confidence.py
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
DW_ASSET   = "GOOGLE/DYNAMICWORLD/V1"
DW_SCALE_M = 10.0

# The nine DW probability band names — also the per-class slug keys
# (see engine/ids.py DW_CLASS_TO_ID_SLUG; band name == class label).
DW_PROB_BANDS = (
    "water", "trees", "grass", "flooded_vegetation",
    "crops", "shrub_and_scrub", "built", "bare", "snow_and_ice",
)

# Buckets for the per-pixel max-probability distribution.
HIST_EDGES = (0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


SITES = [
    {"label": "Sapezal (demo, high-priority Amazon)",
     "centre": {"lat": -13.5417, "lon": -58.7642}, "radius_km": 5.0},
    {"label": "Brasilia (demo, low-priority)",
     "centre": {"lat": -15.7808, "lon": -47.7968}, "radius_km": 43.1},
    {"label": "Open Atlantic CONTROL (expect ~water dominant ≥0.9)",
     "centre": {"lat": -10.0, "lon": -30.0}, "radius_km": 5.0},
    {"label": "Sahara core CONTROL (expect ~bare dominant ≥0.9)",
     "centre": {"lat": 23.0, "lon": 5.0}, "radius_km": 5.0},
]


def _init() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        raise SystemExit("EE_PROJECT_ID not set.")
    ee.Initialize(project=project)


def _diag_one(site: dict) -> None:
    centre = site["centre"]
    print()
    print("=" * 78)
    print(f"  {site['label']}")
    print(f"  lat={centre['lat']}, lon={centre['lon']}, r={site['radius_km']} km")
    print(f"  window: {TIME_START}..{TIME_END}")
    print("=" * 78)

    geom = site_buffer(centre, site["radius_km"])
    ic = (
        ee.ImageCollection(DW_ASSET)
        .filterDate(TIME_START, TIME_END)
        .filterBounds(geom)
    )
    n_images = int(ic.size().getInfo() or 0)
    print(f"  DW images covering buffer in window: {n_images}")
    if n_images == 0:
        print("  No DW coverage — skipping (this is the no_dw_pixels skip path).")
        return

    # Build per-band mean composite over the 90-day window. We deliberately
    # average over time first to get a single per-pixel probability per
    # class — same temporal collapse the mode-composite uses for `label`.
    prob_img = ic.select(list(DW_PROB_BANDS)).mean()
    max_prob = prob_img.reduce(ee.Reducer.max())

    # Per-class mean probability across the buffer (informational —
    # tells us the model's average opinion about each class).
    per_class = prob_img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geom,
        scale=DW_SCALE_M,
        bestEffort=True,
        maxPixels=int(1e9),
    ).getInfo() or {}

    # Mean and median of per-pixel max probability — the proper
    # implementation of class_confidence would average this over the
    # buffer for the dominant class specifically; here we average the
    # per-pixel max regardless of which class wins (a slightly stronger
    # measure of "is this landscape unambiguous").
    mean_max = max_prob.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geom,
        scale=DW_SCALE_M,
        bestEffort=True,
        maxPixels=int(1e9),
    ).getInfo() or {}
    median_max = max_prob.reduceRegion(
        reducer=ee.Reducer.median(),
        geometry=geom,
        scale=DW_SCALE_M,
        bestEffort=True,
        maxPixels=int(1e9),
    ).getInfo() or {}

    mean_max_val   = list(mean_max.values())[0]   if mean_max   else None
    median_max_val = list(median_max.values())[0] if median_max else None

    print()
    print(f"  mean per-pixel max-prob   : "
          f"{mean_max_val:.4f}" if mean_max_val is not None else "  mean per-pixel max-prob   : None")
    print(f"  median per-pixel max-prob : "
          f"{median_max_val:.4f}" if median_max_val is not None else "  median per-pixel max-prob : None")

    # Per-class mean probability table.
    print()
    print("  per-class mean probability across buffer (sums to ~1.0):")
    total = 0.0
    rows = []
    for band in DW_PROB_BANDS:
        v = per_class.get(band)
        if v is None:
            rows.append((band, None))
        else:
            total += v
            rows.append((band, v))
    for band, v in sorted(rows, key=lambda r: -(r[1] or 0.0)):
        if v is None:
            print(f"    {band:22s} : None")
        else:
            print(f"    {band:22s} : {v:.4f}")
    print(f"    {'(sum)':22s} : {total:.4f}")

    # Histogram of per-pixel max-prob — fraction of pixels in each bucket.
    print()
    print("  per-pixel max-prob distribution (fraction of pixels per bucket):")
    edges = HIST_EDGES
    band_name = list(mean_max.keys())[0] if mean_max else None
    if band_name is None:
        print("    (no pixels to histogram)")
        return
    # fixedHistogram: bins evenly spaced; we then aggregate to our edges.
    nbins = 100
    fh = max_prob.reduceRegion(
        reducer=ee.Reducer.fixedHistogram(0.0, 1.0, nbins),
        geometry=geom,
        scale=DW_SCALE_M,
        bestEffort=True,
        maxPixels=int(1e9),
    ).getInfo() or {}
    raw = fh.get(band_name) or []
    if not raw:
        print("    (histogram returned empty)")
        return
    counts = [(edge, c) for edge, c in raw]
    total_px = sum(c for _, c in counts) or 1
    # Aggregate the 100 fine bins to our coarse edges.
    bin_size = 1.0 / nbins
    for lo, hi in zip(edges[:-1], edges[1:]):
        bucket = sum(c for edge, c in counts
                     if (lo - 1e-9) <= edge < (hi - 1e-9))
        pct = 100.0 * bucket / total_px
        print(f"    [{lo:.2f}, {hi:.2f}) : {pct:6.2f}%  ({int(bucket):>9d} px)")


def main() -> None:
    _init()
    print(f"Dynamic World class_confidence diagnostic")
    print(f"Asset: {DW_ASSET}")
    print(f"Window: {TIME_START}..{TIME_END}")
    print(f"Native pixel: {DW_SCALE_M:.0f} m")
    print()
    print("The engine's nature.dw.class_confidence is currently (engine/nature.py")
    print("L635-640) the dominant class's pixel fraction, not a DW probability.")
    print("This script reports what the *intended* implementation (mean of the")
    print("dominant-class probability across the buffer) would produce.")

    for site in SITES:
        _diag_one(site)

    print()
    print("=" * 78)
    print("Read the 'mean per-pixel max-prob' against the engine's current")
    print("class_confidence values from the saved JSONs:")
    print("  Sapezal current:  0.4733  (= crops_pct / 100)")
    print("  Brasilia current: 0.4924  (= trees_pct / 100)")
    print("If the homogeneous controls return mean max-prob ≈ 0.9 and the demo")
    print("sites return mean max-prob materially higher than the current")
    print("placeholder, the proper implementation would carry real information")
    print("about landscape ambiguity that the placeholder discards.")


if __name__ == "__main__":
    main()
