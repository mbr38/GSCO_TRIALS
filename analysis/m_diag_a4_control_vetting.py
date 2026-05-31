"""M-DIAG-A4 Step A5 — vet candidate clean-control windows.

M-DIAG-A3 found 4/5 original controls were secretly dirty. Before proposing 4 new
controls (+ retained Puerto Rico, DGC6), vet a candidate pool against the spec's
criteria: no FIRMS fire pixels within 50 km ±30 days, and low peak AAI in the window.
Reconnaissance only — no engine changes.

Run: PYTHONPATH=. EE_PROJECT_ID=supply-chain-observatory python analysis/m_diag_a4_control_vetting.py
"""
from __future__ import annotations
import os
os.environ.setdefault("EE_PROJECT_ID", "supply-chain-observatory")
from datetime import date, timedelta
import ee, numpy as np, pandas as pd
from engine.core.buffers import site_buffer
from analysis.aai_firms_extract import _build_image_collection, CFG, RADIUS_KM, MS_PER_UTC_DAY, _firms_daily_counts

# Candidate pool (6 → choose best 4). Clean-air, dark surface (avoid snow/desert AAI bias),
# non-fire / non-dust season, post-2018-07 archive.
CANDS = [
    ("patagonia_chile",  -51.0, -72.9, "2021-06-01", "2021-06-30", "Patagonian steppe, austral winter"),
    ("amazon_wet",        -4.0, -63.0, "2021-03-01", "2021-03-31", "Central Amazon, wet season (min. burning)"),
    ("nz_south",         -45.5, 170.0, "2021-06-01", "2021-06-30", "NZ South Island, maritime winter"),
    ("appalachia_us",     35.5, -82.5, "2021-04-01", "2021-04-30", "W. North Carolina forest, spring"),
    ("tasmania",         -42.0, 146.5, "2021-06-01", "2021-06-30", "Tasmania interior, winter"),
    ("congo_wet",          1.0,  23.0, "2021-04-01", "2021-04-30", "Congo basin, wet season"),
]


def daily_site_aai(centre, start, end):
    from engine.constants import BACKGROUND_RING_RADIUS_MULTIPLE, BACKGROUND_RING_MAX_KM
    r = min(BACKGROUND_RING_RADIUS_MULTIPLE * RADIUS_KM, BACKGROUND_RING_MAX_KM)
    env = site_buffer(centre, r)
    ic = _build_image_collection(CFG).filterDate(start, end).filterBounds(env.bounds())
    geom = site_buffer(centre, RADIUS_KM)
    b, s = CFG.band, CFG.scale_m

    def pi(im):
        red = im.select(b).reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True),
            geometry=geom, scale=s, bestEffort=True, maxPixels=int(1e9))
        c = ee.Number(red.get(f"{b}_count", 0))
        return ee.Feature(None, {"v": ee.Algorithms.If(c.gt(0), red.get(f"{b}_mean", 0.0), None),
                                 "db": ee.Number(im.get("system:time_start")).divide(MS_PER_UTC_DAY).floor()})
    df = pd.DataFrame([f["properties"] for f in ic.map(pi).getInfo()["features"]]).dropna()
    if df.empty:
        return None, None, 0
    daily = df.groupby("db")["v"].mean()
    return float(daily.max()), float(daily.mean()), int(daily.size)


def main():
    ee.Initialize(project=os.environ["EE_PROJECT_ID"])
    rows = []
    for cid, lat, lon, start, end, note in CANDS:
        c = {"lat": lat, "lon": lon}
        fs = (date.fromisoformat(start) - timedelta(days=30)).isoformat()
        fe = (date.fromisoformat(end) + timedelta(days=30)).isoformat()
        firms = _firms_daily_counts(lat, lon, fs, fe, 50)
        fire_px = sum(firms.values())
        maxa, meana, ndays = daily_site_aai(c, start, end)
        clean = (fire_px == 0) and (maxa is not None and maxa < 1.0)
        rows.append(dict(id=cid, lat=lat, lon=lon, window=f"{start}/{end}", note=note,
                         firms_fire_px_pm30d=fire_px, n_aai_days=ndays,
                         max_daily_aai=maxa, mean_daily_aai=meana, looks_clean=clean))
        print(f"  {cid:16} fire_px(±30d,50km)={fire_px:5.0f}  n_days={ndays:3}  "
              f"max_aai={None if maxa is None else round(maxa,2)}  clean={clean}")
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "m_diag_a4_control_vetting.csv"), index=False)
    print("\nClean candidates (fire_px==0 and max_aai<1.0):",
          ", ".join(df[df.looks_clean].id.tolist()) or "NONE")


if __name__ == "__main__":
    main()
