"""M-GHG-SANITY-A1 — VIIRS absolute-intensity + Air-borrow sanity check (Step C).

Pre-redesign evidence, NO engine changes (GS10). For 17 AOIs (12 M-VIIRS-DIAG-A1 +
5 production seeds) extracts absolute VIIRS radiance (mean/median/max/sum, both
floor-masked and unmasked per Step B) + the borrowed Air combustion_proxy + current
viirs_score, for three analyses (A: radiance vs expected GHG tier; B: borrow vs
radiance; C: borrow vs expected tier). Parallelized (Step B: be quick).

Run: PYTHONPATH=. EE_PROJECT_ID=supply-chain-observatory python analysis/m_ghg_sanity_a1_probe.py
"""
from __future__ import annotations
import os
os.environ.setdefault("EE_PROJECT_ID", "supply-chain-observatory")
import concurrent.futures
import ee, pandas as pd
from engine.core.buffers import site_buffer
from engine.air import compute_pollutant_snapshot, compute_industrial_combustion_proxy
from engine.ghg import compute_combustion_proxy, compute_viirs_two_output

HERE = os.path.dirname(os.path.abspath(__file__))
WINDOW = ("2025-09-01", "2025-11-30")        # GS4
RADIUS_KM = 10                               # GS5 (uniform for comparability)
NTL_ASSET, NTL_BAND = "NASA/VIIRS/002/VNP46A2", "Gap_Filled_DNB_BRDF_Corrected_NTL"
LIT_FLOOR = 1.0                              # nW/cm²/sr — Step B masked-reducer floor

# 17 AOIs: (id, lat, lon, expected_tier, note). Tiers = expected GHG intensity (Step B).
AOIS = [
    # 12 diagnostic
    ("norilsk_diag", 69.35, 88.20, "High", "Nornickel smelter (diagnostic)"),
    ("korba",        22.35, 82.68, "High", "coal power + aluminium"),
    ("jamshedpur",   22.80, 86.20, "High", "Tata steel"),
    ("yanbu",        24.09, 38.06, "High", "petrochem/refining"),
    ("ploiesti",     44.94, 26.03, "Mid",  "mid oil-refining city"),
    ("pavlodar",     52.29, 76.95, "Mid",  "refinery + aluminium"),
    ("vadodara",     22.31, 73.18, "Mid",  "petrochem secondary city"),
    ("rondonopolis",-16.47,-54.64, "Mid",  "soy agro-industrial"),
    ("patagonia_diag",-51.00,-72.90,"Low", "Patagonian steppe wilderness"),
    ("nz_south",    -45.50,170.00, "Low",  "rural South Island"),
    ("appalachia",   35.50,-82.50, "Low",  "forested rural NC"),
    ("amazon_wet",   -4.00,-63.00, "Low",  "central Amazon"),
    # 5 production seeds
    ("sapezal_seed", -13.5417,-58.7642,"Low","soy plantation frontier (seed)"),
    ("distrito_federal_seed",-15.7808,-47.7968,"Mid","Brasília urban (seed; native r=43km)"),
    ("norilsk_seed", 69.3536, 88.1864,"High","Nornickel smelter (seed)"),
    ("patagonia_seed",-45.8645,-67.4969,"Mid","Comodoro Rivadavia oil/gas region (seed)"),
    ("suape_seed",   -8.4023,-34.9614,"Mid","Suape port-industrial complex (seed)"),
]


def _radiance(site):
    ic = (ee.ImageCollection(NTL_ASSET).select(NTL_BAND)
          .filterDate(*WINDOW).filterBounds(site.bounds()))
    mean_img, max_img = ic.mean(), ic.max()
    masked = mean_img.updateMask(mean_img.gt(LIT_FLOOR))
    red_un = ee.Reducer.mean().combine(ee.Reducer.median(), sharedInputs=True)\
        .combine(ee.Reducer.sum(), sharedInputs=True).combine(ee.Reducer.count(), sharedInputs=True)
    out = ee.Dictionary({
        "un":   mean_img.reduceRegion(red_un, site, scale=464, bestEffort=True, maxPixels=int(1e9)),
        "mk":   masked.reduceRegion(red_un, site, scale=464, bestEffort=True, maxPixels=int(1e9)),
        "maxv": max_img.reduceRegion(ee.Reducer.max(), site, scale=464, bestEffort=True, maxPixels=int(1e9)),
        "ndays": ic.size(),
    }).getInfo()
    b = NTL_BAND
    un, mk = out.get("un", {}) or {}, out.get("mk", {}) or {}
    ndays = out.get("ndays") or 0
    return {
        "rad_mean_unmasked": un.get(f"{b}_mean"), "rad_median_unmasked": un.get(f"{b}_median"),
        "rad_sum_unmasked": un.get(f"{b}_sum"),
        "rad_mean_masked": mk.get(f"{b}_mean"), "rad_median_masked": mk.get(f"{b}_median"),
        "rad_sum_masked": mk.get(f"{b}_sum"),
        "rad_max": (out.get("maxv", {}) or {}).get(f"{b}_max"),
        "lit_pixel_count": mk.get(f"{b}_count"), "lit_day_count": ndays,
    }


def _combustion_proxy(aoi):
    payload = {}
    for ind in ("no2", "co"):
        try:
            payload.update(compute_pollutant_snapshot(aoi, ind, WINDOW, "screening", ee))
        except Exception:  # noqa: BLE001
            pass
    try:
        payload.update(compute_industrial_combustion_proxy(payload))
        payload.update(compute_combustion_proxy(payload))
    except Exception:  # noqa: BLE001
        pass
    return payload.get("ghg.combustion_proxy")


def _one(rec):
    rid, lat, lon, tier, note = rec
    aoi = {"centre": {"lat": lat, "lon": lon}, "radius_km": RADIUS_KM}
    site = site_buffer(aoi["centre"], RADIUS_KM)
    row = {"id": rid, "expected_tier": tier, "note": note, "lat": lat, "lon": lon}
    try:
        row.update(_radiance(site))
    except Exception as e:  # noqa: BLE001
        row["rad_err"] = type(e).__name__
    row["combustion_proxy"] = _combustion_proxy(aoi)
    try:
        v = compute_viirs_two_output(aoi, WINDOW, "screening", ee)
        row["viirs_score"] = v.get("ghg.viirs.score")
    except Exception as e:  # noqa: BLE001
        row["viirs_score"] = None
    print(f"  {rid:22} tier={tier:4} rad_mean_mk={_r(row.get('rad_mean_masked'))} "
          f"rad_sum_mk={_r(row.get('rad_sum_masked'))} cproxy={_r(row.get('combustion_proxy'))} "
          f"viirs={_r(row.get('viirs_score'))}", flush=True)
    return row


def _r(v):
    return None if v is None else round(v, 2)


def main():
    ee.Initialize(project=os.environ["EE_PROJECT_ID"])
    print(f"M-GHG-SANITY-A1 — {len(AOIS)} AOIs, window {WINDOW}, r={RADIUS_KM}km (parallel)")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(_one, AOIS))
    order = {r[0]: i for i, r in enumerate(AOIS)}
    rows.sort(key=lambda r: order[r["id"]])
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "m_ghg_sanity_a1_results.csv"), index=False)
    print("done — wrote m_ghg_sanity_a1_results.csv")


if __name__ == "__main__":
    main()
