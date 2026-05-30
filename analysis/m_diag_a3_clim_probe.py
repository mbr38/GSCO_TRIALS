"""M-DIAG-A3 — D4 climatological-baseline probe (Fix shape 2, empirical).

The within-window temporal-std proxy fails because the event spike contaminates the
denominator. A true climatological baseline computes mean/std from a SEPARATE prior
clean period. This probe tests it empirically: for each event/control, build a 90-day
clean prior window (ending ~10 days before the analysis window), extract the daily site
AAI series there, and compute z_clim = (peak_site_aai − clim_mean) / clim_std.

Investigation only — no engine changes. Output: analysis/m_diag_a3_d4_climatology.csv

Run: PYTHONPATH=. EE_PROJECT_ID=supply-chain-observatory python analysis/m_diag_a3_clim_probe.py
"""
from __future__ import annotations
import os
os.environ.setdefault("EE_PROJECT_ID", "supply-chain-observatory")
from datetime import date, timedelta

import ee
import numpy as np
import pandas as pd

from engine.core.buffers import site_buffer
from engine.constants import BACKGROUND_RING_RADIUS_MULTIPLE, BACKGROUND_RING_MAX_KM, ANOMALY_Z_THRESHOLD
from analysis.aai_firms_extract import (
    EVENTS, CONTROLS, CFG, RADIUS_KM, _build_image_collection, _event_window, MS_PER_UTC_DAY,
)

HERE = os.path.dirname(os.path.abspath(__file__))
CLIM_DAYS = 90
CLIM_GAP = 10  # clean gap between climatology window end and the analysis window start


def _clim_window(analysis_start: str) -> tuple[str, str]:
    a = date.fromisoformat(analysis_start)
    end = a - timedelta(days=CLIM_GAP)
    start = end - timedelta(days=CLIM_DAYS)
    return start.isoformat(), end.isoformat()


def _daily_site_series(centre, start, end):
    """Daily site-buffer mean AAI over [start, end) — the climatology sample."""
    r_bg = min(BACKGROUND_RING_RADIUS_MULTIPLE * RADIUS_KM, BACKGROUND_RING_MAX_KM)
    env = site_buffer(centre, r_bg)
    ic = _build_image_collection(CFG).filterDate(start, end).filterBounds(env.bounds())
    geom = site_buffer(centre, RADIUS_KM)
    band, scale = CFG.band, CFG.scale_m

    def per_image(image):
        red = image.select(band).reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True),
            geometry=geom, scale=scale, bestEffort=True, maxPixels=int(1e9))
        cnt = ee.Number(red.get(f"{band}_count", 0))
        return ee.Feature(None, {
            "v": ee.Algorithms.If(cnt.gt(0), red.get(f"{band}_mean", 0.0), None),
            "db": ee.Number(image.get("system:time_start")).divide(MS_PER_UTC_DAY).floor()})

    feats = ic.map(per_image).getInfo()["features"]
    df = pd.DataFrame([f["properties"] for f in feats]).dropna()
    if df.empty:
        return None, None
    daily = df.groupby("db")["v"].mean()
    return float(daily.mean()), float(daily.std())


def main():
    ee.Initialize(project=os.environ["EE_PROJECT_ID"])
    summ = pd.read_csv(os.path.join(HERE, "aai_firms_event_summary.csv")).set_index("id")
    rows = []
    items = [("event", e["id"], e["lat"], e["lon"], _event_window(e)[0]) for e in EVENTS] + \
            [("control", c["id"], c["lat"], c["lon"], c["win_start"]) for c in CONTROLS]
    for grp, rid, lat, lon, astart in items:
        cs, ce = _clim_window(astart)
        cmean, cstd = _daily_site_series({"lat": lat, "lon": lon}, cs, ce)
        peak = summ.loc[rid, "peak_aai_in_peak"] if grp == "event" else summ.loc[rid, "peak_aai"]
        z_clim = (peak - cmean) / cstd if (cstd and not np.isnan(peak)) else None
        rows.append(dict(id=rid, grp=grp, kind=summ.loc[rid, "kind"], clim_window=f"{cs}/{ce}",
                         clim_mean=cmean, clim_std=cstd, peak_site_aai=peak, z_clim=z_clim,
                         fires=bool(z_clim is not None and z_clim >= ANOMALY_Z_THRESHOLD)))
        print(f"  {grp:7} {rid:20} clim_mean={cmean} clim_std={cstd} z_clim="
              f"{None if z_clim is None else round(z_clim,2)} fires={rows[-1]['fires']}")
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "m_diag_a3_d4_climatology.csv"), index=False)
    ev, ct = df[df.grp == "event"], df[df.grp == "control"]
    print(f"\nclimatological-baseline z @ 2.0: events fire {ev.fires.sum()}/{len(ev)} "
          f"(fire {ev[ev.kind=='fire'].fires.sum()}/5, dust {ev[ev.kind=='dust'].fires.sum()}/5) | "
          f"controls FP {ct.fires.sum()}/{len(ct)}")


if __name__ == "__main__":
    main()
