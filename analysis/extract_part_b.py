"""Step E — Part B extraction (concentration validation): GHG inputs vs XCO2.

For each of the 25 locked locations, over the 2025-06-01 → 2025-12-01 window,
scans EVERY OCO-2 (v11.2r) and OCO-3 (v11r) L2 Lite FP daily-global granule,
pools good-quality (xco2_quality_flag == 0) soundings, and computes:
  - xco2_mean        AOI-box (±0.25° ≈ 25 km) pooled mean XCO2 [ppm]
  - xco2_std         AOI-box pooled std [ppm]
  - xco2_count       n good AOI soundings (OCO-2 + OCO-3 combined)
  - xco2_n_oco2 / xco2_n_oco3   per-instrument good AOI counts
  - xco2_n_granules  n granules contributing ≥1 AOI sounding
  - xco2_bg_mean     local background: pooled mean over the 0.25°–1.0° annulus
  - xco2_bg_count    n good background soundings
  - xco2_delta       xco2_mean − xco2_bg_mean (AOI vs local background) [ppm]
                     None unless aoi_count ≥ MIN_AOI and bg_count ≥ MIN_BG.

Because both AOI and ring soundings are observed on the same overpasses, the
seasonal/latitudinal XCO2 gradient largely cancels in the *delta* even though
each is pooled over the window. Sparse-evidence locations are flagged.

OCO data is NOT in Earth Engine — sourced via earthaccess from NASA GES DISC.
Adds columns to analysis/ghg_odiac_validation.csv (run extract_part_a.py first).

Run: python analysis/extract_part_b.py
"""
import sys, os, time
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

import numpy as np
import pandas as pd
import earthaccess
import h5py

from analysis.locations import (
    LOCATIONS, WINDOW_NOW, OCO_BBOX_HALFWIDTH_DEG, CSV_PATH,
    OCO2_CONCEPT_ID, OCO3_CONCEPT_ID,
)

HW = OCO_BBOX_HALFWIDTH_DEG       # AOI half-width (deg)
RING_OUTER = 1.0                  # local-background annulus outer edge (deg)
MIN_AOI = 5                       # min AOI soundings to report a mean/delta
MIN_BG = 20                       # min background soundings to report a delta
BATCH = 12                        # parallel-download batch size
TMP = "/tmp/oco_partb"


def _accum_init():
    return {name: {"aoi": [], "ring": [], "n_oco2": 0, "n_oco3": 0,
                   "granules": set()}
            for _, name, _, _ in LOCATIONS}


def process_granule(path: str, acc: dict, instrument: str, gidx: int) -> None:
    with h5py.File(path, "r") as hf:
        lat = hf["latitude"][:]
        lon = hf["longitude"][:]
        xco2 = hf["xco2"][:]
        good = hf["xco2_quality_flag"][:] == 0
    for _, name, clat, clon in LOCATIONS:
        dlat = np.abs(lat - clat)
        dlon = np.abs(lon - clon)
        cheb = np.maximum(dlat, dlon)
        in_aoi = good & (cheb <= HW)
        in_ring = good & (cheb > HW) & (cheb <= RING_OUTER)
        n_aoi = int(in_aoi.sum())
        if n_aoi:
            acc[name]["aoi"].append(xco2[in_aoi])
            acc[name]["granules"].add(gidx)
            if instrument == "oco2":
                acc[name]["n_oco2"] += n_aoi
            else:
                acc[name]["n_oco3"] += n_aoi
        if in_ring.any():
            acc[name]["ring"].append(xco2[in_ring])


def scan_product(concept_id: str, instrument: str, acc: dict) -> int:
    earthaccess.login(strategy="netrc")
    granules = earthaccess.search_data(
        concept_id=concept_id, temporal=WINDOW_NOW, count=2000)
    print(f"{instrument}: {len(granules)} granules in window", flush=True)
    gidx = 0
    for b0 in range(0, len(granules), BATCH):
        batch = granules[b0:b0 + BATCH]
        t0 = time.time()
        files = earthaccess.download(batch, local_path=TMP, threads=BATCH)
        for f in files:
            try:
                process_granule(f, acc, instrument, gidx)
            except Exception as e:
                print(f"  read fail {os.path.basename(f)}: {e!r:.80}", flush=True)
            finally:
                gidx += 1
                try:
                    os.remove(f)
                except OSError:
                    pass
        print(f"  {instrument} {b0 + len(batch)}/{len(granules)} "
              f"({time.time() - t0:.0f}s/batch)", flush=True)
    return len(granules)


def summarise(acc: dict) -> dict:
    out = {}
    for _, name, _, _ in LOCATIONS:
        a = acc[name]
        aoi = np.concatenate(a["aoi"]) if a["aoi"] else np.array([])
        ring = np.concatenate(a["ring"]) if a["ring"] else np.array([])
        n_aoi, n_bg = aoi.size, ring.size
        mean = float(aoi.mean()) if n_aoi >= MIN_AOI else None
        std = float(aoi.std(ddof=1)) if n_aoi >= 2 else None
        bg_mean = float(ring.mean()) if n_bg >= MIN_BG else None
        delta = (mean - bg_mean) if (mean is not None and bg_mean is not None) else None
        flags = []
        if n_aoi < MIN_AOI:
            flags.append("sparse_aoi")
        if n_bg < MIN_BG:
            flags.append("sparse_bg")
        out[name] = {
            "xco2_mean": mean, "xco2_std": std, "xco2_count": int(n_aoi),
            "xco2_n_oco2": a["n_oco2"], "xco2_n_oco3": a["n_oco3"],
            "xco2_n_granules": len(a["granules"]),
            "xco2_bg_mean": bg_mean, "xco2_bg_count": int(n_bg),
            "xco2_delta": delta,
            "partB_flags": ";".join(flags),
        }
    return out


def main() -> None:
    os.makedirs(TMP, exist_ok=True)
    acc = _accum_init()
    n2 = scan_product(OCO2_CONCEPT_ID, "oco2", acc)
    n3 = scan_product(OCO3_CONCEPT_ID, "oco3", acc)
    summ = summarise(acc)

    df = pd.read_csv(CSV_PATH)
    cols = ["xco2_mean", "xco2_std", "xco2_count", "xco2_n_oco2", "xco2_n_oco3",
            "xco2_n_granules", "xco2_bg_mean", "xco2_bg_count", "xco2_delta",
            "partB_flags"]
    for c in cols:
        df[c] = df["location"].map(lambda nm: summ[nm][c])
    df.to_csv(CSV_PATH, index=False)

    print(f"\nScanned OCO-2={n2} + OCO-3={n3} granules.")
    print(f"{'location':16} {'n_aoi':>6} {'mean':>7} {'delta':>7} {'flags'}")
    for _, name, _, _ in LOCATIONS:
        s = summ[name]
        m = f"{s['xco2_mean']:.1f}" if s['xco2_mean'] is not None else "   -"
        d = f"{s['xco2_delta']:+.2f}" if s['xco2_delta'] is not None else "   -"
        print(f"{name:16} {s['xco2_count']:6d} {m:>7} {d:>7} {s['partB_flags']}")
    print(f"\nUpdated {CSV_PATH} with {len(cols)} Part B columns.")


if __name__ == "__main__":
    main()
