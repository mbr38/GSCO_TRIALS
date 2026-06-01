"""M-VIIRS-REDESIGN-A1 — absolute-intensity probe (VR3 refinement evidence).

Self-relative flaring (median+3σ) can't separate intense sources from rural lights
(it discards absolute brightness). Operator (1 Jun 2026): severity = "intense emissions
source"; tool is directional. This probe tests whether an ABSOLUTE brightness anchor
separates intense sources (flares/heavy industry) from dim rural lights across the 17
AOIs, to set a coarse directional threshold. No engine change. Parallelized.

Run: PYTHONPATH=. EE_PROJECT_ID=supply-chain-observatory python analysis/m_viirs_redesign_a1_abscheck.py
"""
from __future__ import annotations
import os
os.environ.setdefault("EE_PROJECT_ID", "supply-chain-observatory")
import concurrent.futures
import ee, pandas as pd
from engine.core.buffers import site_buffer
from analysis.m_ghg_sanity_a1_probe import AOIS, WINDOW, RADIUS_KM, NTL_ASSET, NTL_BAND

HERE = os.path.dirname(os.path.abspath(__file__))
ABS_THRESHOLDS = [10, 30, 60, 100, 200]   # nW/cm²/sr — candidate "intense source" anchors


def _one(rec):
    rid, lat, lon, tier, note = rec
    site = site_buffer({"lat": lat, "lon": lon}, RADIUS_KM)
    ic = (ee.ImageCollection(NTL_ASSET).select(NTL_BAND)
          .filterDate(*WINDOW).filterBounds(site.bounds()))
    mean_img = ic.mean()
    b = NTL_BAND
    stats = mean_img.reduceRegion(
        ee.Reducer.max().combine(ee.Reducer.percentile([95, 99]), sharedInputs=True)
          .combine(ee.Reducer.mean(), sharedInputs=True).combine(ee.Reducer.count(), sharedInputs=True),
        site, scale=464, bestEffort=True, maxPixels=int(1e9))
    fracs = {f"frac_gt_{t}": mean_img.gt(t).rename("m").reduceRegion(
        ee.Reducer.mean(), site, scale=464, bestEffort=True, maxPixels=int(1e9)).get("m")
        for t in ABS_THRESHOLDS}
    out = ee.Dictionary({**{"max": stats.get(f"{b}_max"), "p95": stats.get(f"{b}_p95"),
                            "p99": stats.get(f"{b}_p99"), "mean": stats.get(f"{b}_mean"),
                            "n": stats.get(f"{b}_count")}, **fracs}).getInfo()
    row = dict(id=rid, tier=tier,
               rad_max=round(out.get("max") or 0, 1), rad_p99=round(out.get("p99") or 0, 1),
               rad_p95=round(out.get("p95") or 0, 1), rad_mean=round(out.get("mean") or 0, 1))
    for t in ABS_THRESHOLDS:
        v = out.get(f"frac_gt_{t}")
        row[f"frac>{t}"] = None if v is None else round(v, 4)
    print(f"  {rid:22} {tier:4} max={row['rad_max']:8} p99={row['rad_p99']:7} "
          f"f>30={row['frac>30']} f>60={row['frac>60']} f>100={row['frac>100']}", flush=True)
    return row


def main():
    ee.Initialize(project=os.environ["EE_PROJECT_ID"])
    print(f"abs-intensity probe — {len(AOIS)} AOIs, window {WINDOW}")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(_one, AOIS))
    order = {r[0]: i for i, r in enumerate(AOIS)}
    rows.sort(key=lambda r: order[r["id"]])
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "m_viirs_redesign_a1_abscheck.csv"), index=False)
    print("\n=== tier means ===")
    print(df.groupby("tier")[["rad_max","rad_p99","frac>30","frac>60","frac>100"]].mean().round(3).to_string())
    print("\n=== sorted by rad_p99 (intense-source ranking) ===")
    print(df.sort_values("rad_p99", ascending=False)[["id","tier","rad_p99","rad_max","frac>60"]].to_string(index=False))
    print("done")


if __name__ == "__main__":
    main()
