"""M-VIIRS-REDESIGN-A1 — Step A→B distribution-check probe (no engine change).

Implements the two locked grammars as a PROBE so Step B can lock thresholds/weights
against real numbers:
  * flaring  = spatial-pixel outlier: fraction of site-buffer pixels whose window-mean
               radiance exceeds (site spatial median + k·σ). Computed at k=3 and k=2.
  * lit_contrast = percentile of site median brightness within the ring's ALL-pixel
                   (lit+dark, land-masked) distribution = fraction of ring pixels dimmer.
All server-side (~1 getInfo/AOI), parallelized across the 17 AOIs.

Run: PYTHONPATH=. EE_PROJECT_ID=supply-chain-observatory python analysis/m_viirs_redesign_a1_distcheck.py
"""
from __future__ import annotations
import os
os.environ.setdefault("EE_PROJECT_ID", "supply-chain-observatory")
import concurrent.futures
import ee, pandas as pd
from engine.core.buffers import site_buffer, background_ring
from analysis.m_ghg_sanity_a1_probe import AOIS, WINDOW, RADIUS_KM, NTL_ASSET, NTL_BAND

HERE = os.path.dirname(os.path.abspath(__file__))
MIN_STD = 0.5            # nW/cm²/sr — below this the site is too uniform for outlier logic
MIN_PIX = 10


def _one(rec):
    rid, lat, lon, tier, note = rec
    centre = {"lat": lat, "lon": lon}
    site = site_buffer(centre, RADIUS_KM)
    ring = background_ring(centre, RADIUS_KM)
    rg, rmask = ring["geometry"], ring["mask"]
    ic = (ee.ImageCollection(NTL_ASSET).select(NTL_BAND)
          .filterDate(*WINDOW).filterBounds(site.bounds()))
    mean_img = ic.mean()
    b = NTL_BAND
    st = mean_img.reduceRegion(
        ee.Reducer.median().combine(ee.Reducer.stdDev(), sharedInputs=True)
          .combine(ee.Reducer.count(), sharedInputs=True),
        site, scale=464, bestEffort=True, maxPixels=int(1e9))
    median = ee.Number(ee.Algorithms.If(st.get(f"{b}_median"), st.get(f"{b}_median"), 0))
    std = ee.Number(ee.Algorithms.If(st.get(f"{b}_stdDev"), st.get(f"{b}_stdDev"), 0))
    n = ee.Number(ee.Algorithms.If(st.get(f"{b}_count"), st.get(f"{b}_count"), 0))
    thr3, thr2 = median.add(std.multiply(3)), median.add(std.multiply(2))
    n_above3 = mean_img.gt(thr3).rename("m").reduceRegion(ee.Reducer.sum(), site, scale=464, bestEffort=True, maxPixels=int(1e9)).get("m")
    n_above2 = mean_img.gt(thr2).rename("m").reduceRegion(ee.Reducer.sum(), site, scale=464, bestEffort=True, maxPixels=int(1e9)).get("m")
    # lit-contrast: percentile = fraction of ring (all-pixel, land-masked) dimmer than site median
    ring_img = mean_img.updateMask(rmask) if rmask is not None else mean_img
    below = ring_img.lt(median).rename("b").reduceRegion(ee.Reducer.mean(), rg, scale=464, bestEffort=True, maxPixels=int(1e9)).get("b")
    n_ring = ring_img.rename("b").reduceRegion(ee.Reducer.count(), rg, scale=464, bestEffort=True, maxPixels=int(1e9)).get("b")
    out = ee.Dictionary({"median": median, "std": std, "n": n,
                         "n_above3": n_above3, "n_above2": n_above2,
                         "pct": below, "n_ring": n_ring}).getInfo()
    n_ = out.get("n") or 0
    std_ = out.get("std") or 0
    valid = n_ >= MIN_PIX and std_ >= MIN_STD
    fl3 = (out.get("n_above3") or 0) / n_ if (valid and n_) else (0.0 if n_ else None)
    fl2 = (out.get("n_above2") or 0) / n_ if (valid and n_) else (0.0 if n_ else None)
    row = dict(id=rid, tier=tier, note=note, site_median=round(out.get("median") or 0, 2),
               site_std=round(std_, 2), n_site_pix=int(n_),
               flaring_3sig=None if fl3 is None else round(fl3, 4),
               flaring_2sig=None if fl2 is None else round(fl2, 4),
               lit_contrast_pct=None if out.get("pct") is None else round(out["pct"], 3),
               n_ring_pix=int(out.get("n_ring") or 0))
    print(f"  {rid:22} tier={tier:4} fl3={row['flaring_3sig']} fl2={row['flaring_2sig']} "
          f"litpct={row['lit_contrast_pct']} nsite={row['n_site_pix']}", flush=True)
    return row


def main():
    ee.Initialize(project=os.environ["EE_PROJECT_ID"])
    print(f"VIIRS-REDESIGN dist-check — {len(AOIS)} AOIs, window {WINDOW}, r={RADIUS_KM}km")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(_one, AOIS))
    order = {r[0]: i for i, r in enumerate(AOIS)}
    rows.sort(key=lambda r: order[r["id"]])
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "m_viirs_redesign_a1_distcheck.csv"), index=False)
    print("\n=== tier separation (mean) ===")
    print(df.groupby("tier")[["flaring_3sig","flaring_2sig","lit_contrast_pct"]].mean().round(4).to_string())
    print("\nComodoro (patagonia_seed):", df[df.id=="patagonia_seed"][["flaring_3sig","flaring_2sig","lit_contrast_pct"]].to_dict("records"))
    print("done")


if __name__ == "__main__":
    main()
