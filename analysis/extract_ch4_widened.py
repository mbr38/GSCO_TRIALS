"""CH4 Response B — re-extract CH4 anomaly z + raw at a WIDENED 15 km AOI.

Tests whether widening the AOI to clearly exceed Sentinel-5P TROPOMI's ~7 km
native CH4 footprint restores the CH4 anomaly-z signal that the 5 km screening
radius washed out (site-minus-background self-cancellation; see
docs/ghg_odiac_validation.md §1, §6.1).

Everything except the AOI radius is held constant: same 25 locations, same
window (2025-06-01 → 2025-12-01), same CH4 band, same engine path
(engine.ghg.compute_ch4_snapshot). At 15 km the background ring scales to
15–75 km (BACKGROUND_RING_RADIUS_MULTIPLE=5, uncapped < 200 km).

Output: analysis/ghg_odiac_validation_widened_aoi.csv (CH4 columns only).
Compared against the 5 km values in analysis/ghg_odiac_validation.csv.

Run: python analysis/extract_ch4_widened.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

import ee
import pandas as pd

from analysis.locations import LOCATIONS, WINDOW_NOW

ee.Initialize(project="supply-chain-observatory")
from engine import ghg

WIDE_RADIUS_KM = 15.0  # Response B locked parameter (5 km → 15 km)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "ghg_odiac_validation_widened_aoi.csv")


def _num(d, k):
    v = d.get(k)
    return float(v) if isinstance(v, (int, float)) else None


def extract(regime, name, lat, lon):
    aoi = {"centre": {"lat": lat, "lon": lon}, "radius_km": WIDE_RADIUS_KM}
    row = {"regime": regime, "location": name, "lat": lat, "lon": lon,
           "radius_km": WIDE_RADIUS_KM}
    try:
        ch4 = ghg.compute_ch4_snapshot(aoi, WINDOW_NOW, "screening", None)
        row["ch4_z_15km"] = _num(ch4, "ghg.ch4.z")
        row["ch4_site_ppb_15km"] = _num(ch4, "ghg.ch4.site")
        row["ch4_background_ppb_15km"] = _num(ch4, "ghg.ch4.background")
        row["ch4_anomaly_ppb_15km"] = _num(ch4, "ghg.ch4.anomaly")
        row["ch4_confidence_15km"] = _num(ch4, "ghg.ch4.confidence")
        row["partA_flags_15km"] = ""
    except Exception as e:
        for k in ("ch4_z_15km", "ch4_site_ppb_15km", "ch4_background_ppb_15km",
                  "ch4_anomaly_ppb_15km", "ch4_confidence_15km"):
            row[k] = None
        row["partA_flags_15km"] = f"ch4_fail:{type(e).__name__}"
    return row


def main():
    rows = []
    for i, (regime, name, lat, lon) in enumerate(LOCATIONS, 1):
        r = extract(regime, name, lat, lon)
        rows.append(r)
        print(f"[{i:2d}/25] {regime:9} {name:16} z@15km={r.get('ch4_z_15km')!s:>9.9} "
              f"flags={r.get('partA_flags_15km')}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    print(f"\nWrote {len(df)} rows -> {OUT}")


if __name__ == "__main__":
    main()
