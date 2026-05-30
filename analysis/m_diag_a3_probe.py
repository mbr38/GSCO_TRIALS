"""M-DIAG-A3 — AAI bg_std denominator-collapse diagnostic probe (Step C).

Investigation only — NO engine changes (DGB1). Reuses the AAI↔FIRMS validation
evidence where possible (DGB2) and adds the small fresh probes the diagnosis needs:

  D1 → analysis/m_diag_a3_d1_ring_values.csv     raw ring-pixel distribution at the
                                                  5 control sites (H1a/H1b) + the
                                                  spatial-vs-temporal scale test (H1c)
  D2 → analysis/m_diag_a3_d2_cross_indicator.csv  bg_std + per-day hot-day behaviour for
                                                  9 air + CH₄ + VIIRS at 8 clean sites
  D3 → analysis/m_diag_a3_d3_floor_sweep.csv      false-positive vs bg_std floor, and
                                                  true-positive preservation at events

Run:  PYTHONPATH=. EE_PROJECT_ID=supply-chain-observatory python analysis/m_diag_a3_probe.py

Mechanism under test (recon A1): `bg_std` is the SPATIAL std across the 5–25 km ring of
the TIME-AVERAGED field (engine/core/repeatable_core.py::_background_value_reduction,
img = ic.mean() → reduceRegion(median, stdDev)). It is then used as the denominator for
PER-DAY temporal deviations in _server_side_hf::per_image. H1c = that spatial-vs-temporal
mismatch, not just "genuine" (H1a) vs "computational" (H1b).
"""
from __future__ import annotations

import os
os.environ.setdefault("EE_PROJECT_ID", "supply-chain-observatory")

import ee
import numpy as np
import pandas as pd

from engine.air import AIR_POLLUTANT_CONFIG, _build_image_collection as air_ic
from engine.ghg import GHG_INDICATOR_CONFIG, _build_image_collection as ghg_ic
from engine.core.buffers import site_buffer, background_ring
from engine.core.repeatable_core import background_value
from engine.constants import (
    ANOMALY_Z_THRESHOLD, BACKGROUND_RING_RADIUS_MULTIPLE, BACKGROUND_RING_MAX_KM,
)
from engine.exceptions import IndicatorComputeError
from analysis.aai_firms_extract import _per_image_features, RADIUS_KM, CFG as AAI_CFG

HERE = os.path.dirname(os.path.abspath(__file__))

# 5 AAI controls (same windows as the validation) — bg_std reused/recomputed here.
CONTROLS = [
    ("quebec_2023_ctrl",   49.7,  -76.0, "2023-05-01", "2023-05-31"),
    ("bayarea_2020_ctrl",  37.7, -122.2, "2020-07-15", "2020-08-14"),
    ("godzilla_2020_ctrl", 18.2,  -66.5, "2020-05-15", "2020-06-14"),
    ("beijing_2021_ctrl",  39.9,  116.4, "2021-02-01", "2021-03-03"),
    ("phoenix_2021_ctrl",  33.4, -112.0, "2021-06-01", "2021-07-01"),
]
# 3 fresh clean sites for the cross-indicator survey (fixed comparison window).
FRESH = [
    ("ocean_pacific",   0.0, -140.0, "2023-07-01", "2023-07-31"),
    ("desert_sahara",  23.0,   13.0, "2023-07-01", "2023-07-31"),
    ("forest_amazon", -10.0,  -60.0, "2023-07-01", "2023-07-31"),
]
# D2 indicators (Q-DGB-A: NDVI excluded — doesn't feed the per-day HF severity path).
AIR_INDS = ["no2", "so2", "co", "hcho", "o3", "aai", "pm25", "pm10", "aod"]
GHG_INDS = ["ch4", "viirs"]
FLOORS = [0.05, 0.1, 0.2, 0.3, 0.5, 1.0]  # Step B lock


def _aoi(lat, lon):
    return {"centre": {"lat": lat, "lon": lon}, "radius_km": RADIUS_KM}


def _window_ic(cfg, build, centre, start, end):
    r_bg = min(BACKGROUND_RING_RADIUS_MULTIPLE * RADIUS_KM, BACKGROUND_RING_MAX_KM)
    env = site_buffer(centre, r_bg)
    return build(cfg).filterDate(start, end).filterBounds(env.bounds())


# --------------------------------------------------------------------------- #
# D1 — raw ring pixel distribution + spatial-vs-temporal scale test (H1c)
# --------------------------------------------------------------------------- #
def d1_ring_values():
    rows = []
    day = pd.read_csv(os.path.join(HERE, "aai_firms_validation.csv"))
    for cid, lat, lon, start, end in CONTROLS:
        centre = {"lat": lat, "lon": lon}
        ic_window = _window_ic(AAI_CFG, air_ic, centre, start, end)
        ring = background_ring(centre, RADIUS_KM)
        # The exact engine field: SPATIAL distribution of the TIME-MEAN AAI over the ring.
        mean_img = ic_window.select(AAI_CFG.band).mean()
        if ring["mask"] is not None:
            mean_img = mean_img.updateMask(ring["mask"])
        vals = mean_img.reduceRegion(
            reducer=ee.Reducer.toList(), geometry=ring["geometry"],
            scale=AAI_CFG.scale_m, bestEffort=True, maxPixels=int(1e9),
        ).get(AAI_CFG.band).getInfo() or []
        vals = np.array([v for v in vals if v is not None], dtype=float)
        # H1c: temporal std of the per-day site series (what a temporal z SHOULD scale by),
        # straight from the existing validation data (DGB2).
        site_series = day[(day.id == cid)]["site_aai"].dropna().to_numpy()
        spatial_std = float(vals.std()) if vals.size else None
        temporal_std = float(site_series.std()) if site_series.size else None
        rows.append(dict(
            control=cid, window=f"{start}/{end}",
            n_ring_px=int(vals.size),
            ring_min=float(vals.min()) if vals.size else None,
            ring_max=float(vals.max()) if vals.size else None,
            ring_mean=float(vals.mean()) if vals.size else None,
            ring_median=float(np.median(vals)) if vals.size else None,
            ring_spatial_std=spatial_std,               # = bg_std (the denominator used)
            ring_n_unique=int(np.unique(np.round(vals, 6)).size) if vals.size else 0,
            ring_iqr=float(np.percentile(vals, 75) - np.percentile(vals, 25)) if vals.size else None,
            site_temporal_std=temporal_std,             # what a temporal-z denominator would be
            temporal_over_spatial=(temporal_std / spatial_std)
                if (temporal_std and spatial_std) else None,
        ))
        print(f"  D1 {cid:20} n_px={vals.size:4} spatial_std={spatial_std} "
              f"temporal_std={temporal_std} ratio={rows[-1]['temporal_over_spatial']}")
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "m_diag_a3_d1_ring_values.csv"), index=False)
    return rows


# --------------------------------------------------------------------------- #
# D2 — cross-indicator bg_std + per-day hot-day survey
# --------------------------------------------------------------------------- #
def _indicator_cfg_build(ind):
    if ind in AIR_INDS:
        return AIR_POLLUTANT_CONFIG[ind], air_ic, "air"
    return GHG_INDICATOR_CONFIG[ind], ghg_ic, "ghg"


def d2_cross_indicator():
    rows = []
    sites = [(c[0], c[1], c[2], c[3], c[4], "control") for c in CONTROLS] + \
            [(f[0], f[1], f[2], f[3], f[4], "fresh") for f in FRESH]
    for sid, lat, lon, start, end, site_kind in sites:
        centre = {"lat": lat, "lon": lon}
        aoi = _aoi(lat, lon)
        for ind in AIR_INDS + GHG_INDS:
            cfg, build, pillar = _indicator_cfg_build(ind)
            rec = dict(site=sid, site_kind=site_kind, lat=lat, lon=lon, pillar=pillar,
                       indicator=ind, native_scale_m=cfg.scale_m, window=f"{start}/{end}",
                       bg_median=None, bg_std=None, cv=None,
                       n_valid_days=None, n_hot_days=None, hf=None, max_day_z=None, error="")
            try:
                ic_window = _window_ic(cfg, build, centre, start, end)
                ring = background_ring(centre, RADIUS_KM)
                bg_median, bg_std = background_value(
                    aoi, ic_window, cfg.band, seasonal=True, scale=cfg.scale_m, ring=ring)
                rec["bg_median"], rec["bg_std"] = bg_median, bg_std
                rec["cv"] = abs(bg_std / bg_median) if bg_median not in (0, None) else None
                geom = site_buffer(centre, RADIUS_KM)
                feats = _per_image_features(ic_window, geom, cfg.band, cfg.scale_m,
                                            bg_median, bg_std, ANOMALY_Z_THRESHOLD)
                df = pd.DataFrame(feats)
                if not df.empty:
                    valid, hot, zmax = set(), set(), None
                    for db, g in df.groupby("day_bucket"):
                        vg = g[g["is_valid"].astype(bool)]
                        if len(vg):
                            valid.add(int(db))
                            dz = (float(vg["site_mean"].mean()) - bg_median) / bg_std if bg_std else None
                            zmax = dz if (zmax is None or (dz is not None and dz > zmax)) else zmax
                        if bool(g["is_hot"].astype(bool).any()):
                            hot.add(int(db))
                    rec["n_valid_days"], rec["n_hot_days"] = len(valid), len(hot)
                    rec["hf"] = len(hot) / len(valid) if valid else None
                    rec["max_day_z"] = zmax
            except IndicatorComputeError as e:
                rec["error"] = f"{type(e).__name__}"
            except Exception as e:  # noqa: BLE001
                rec["error"] = f"{type(e).__name__}: {str(e)[:60]}"
            rows.append(rec)
            print(f"  D2 {sid:16} {ind:6} bg_std={rec['bg_std']} hf={rec['hf']} {rec['error']}")
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "m_diag_a3_d2_cross_indicator.csv"), index=False)
    return rows


# --------------------------------------------------------------------------- #
# D3 — bg_std floor sweep (pure recompute on existing validation per-day data)
# --------------------------------------------------------------------------- #
def d3_floor_sweep():
    day = pd.read_csv(os.path.join(HERE, "aai_firms_validation.csv"))
    summ = pd.read_csv(os.path.join(HERE, "aai_firms_event_summary.csv"))
    controls = day[day.kind == "control"]
    # Event hit-days = days inside each event's peak window (the brief's TP criterion).
    ev = summ[summ.kind != "control"].set_index("id")
    rows = []
    for floor in FLOORS:
        # False positives: control days whose floored per-day z still ≥ 2.0.
        c = controls.copy()
        c["z_floored"] = (c["site_aai"] - c["bg_median"]) / np.maximum(c["bg_std"], floor)
        fp_days = int((c["z_floored"] >= ANOMALY_Z_THRESHOLD).sum())
        ctrl_with_fp = c[c["z_floored"] >= ANOMALY_Z_THRESHOLD]["id"].nunique()
        # True positives preserved: of the 9 events that fired in peak, how many still fire?
        tp_kept = 0
        tp_total = 0
        for eid, erow in ev.iterrows():
            if not erow["fired_in_peak"]:
                continue
            tp_total += 1
            g = day[(day.id == eid) & (day.date >= erow["peak_start"]) & (day.date <= erow["peak_end"])].copy()
            g["z_floored"] = (g["site_aai"] - g["bg_median"]) / np.maximum(g["bg_std"], floor)
            if (g["z_floored"] >= ANOMALY_Z_THRESHOLD).any():
                tp_kept += 1
        rows.append(dict(floor=floor, control_fp_days=fp_days, controls_with_fp=ctrl_with_fp,
                         n_controls=controls["id"].nunique(),
                         tp_events_kept=tp_kept, tp_events_total=tp_total))
        print(f"  D3 floor={floor:>4}: control_FP_days={fp_days:3} controls_w_FP={ctrl_with_fp}/5 "
              f"TP_kept={tp_kept}/{tp_total}")
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "m_diag_a3_d3_floor_sweep.csv"), index=False)
    return rows


def main():
    ee.Initialize(project=os.environ["EE_PROJECT_ID"])
    print("D1 — ring-value probe + H1c scale test")
    d1_ring_values()
    print("D3 — floor sweep (existing data)")
    d3_floor_sweep()
    print("D2 — cross-indicator survey (slowest)")
    d2_cross_indicator()
    print("done — wrote m_diag_a3_d1/d2/d3 CSVs")


if __name__ == "__main__":
    main()
