"""M-CALIBRATION-SWEEP-A1 — Step C1 (corrected): ATTRIBUTION-framed global air band.

Operator correction (1 Jun 2026): the tool's purpose is attributing SUSTAINED air
pollution to a supplier over a user-selected window — NOT catching transient wildfire/
dust events. So the calibration "should-go-red" set is KNOWN HIGH-POLLUTION INDUSTRIAL
sites (mines, smelters, refineries, coal power), and "should-stay-green" is clean
wilderness. The aggregate (window-averaged) z is the right quantity for this.

Metric (capture-first, CS2 re-framed for attribution):
  capture = fraction of industrial sites that fire (any core pollutant |z| >= Concern)
  FP      = fraction of clean control sites that fire (any core pollutant |z| >= Concern)
Target: capture >= 0.90 at FP <= 0.20.

Core attribution pollutants: NO2 (combustion/power), SO2 (smelters/coal), CO (combustion),
AOD (particulates). AAI excluded — smoke/dust is regional/transient, weak for attribution.

Evidence only; operator approves the band before any commit (CS8). No engine changes.
Run: PYTHONPATH=. EE_PROJECT_ID=supply-chain-observatory python analysis/m_calibration_sweep_c1_attribution.py
"""
from __future__ import annotations
import os
os.environ.setdefault("EE_PROJECT_ID", "supply-chain-observatory")
import concurrent.futures
import ee, numpy as np, pandas as pd
from engine.air import compute_pollutant_snapshot

# Seed: the 8 industrial sites already extracted in the (killed) serial run — kept so we
# don't redo them. None = no data (e.g. sparse SO2). Remaining sites run parallelized below.
SEED = {
    "norilsk":      {"no2": 1.94, "so2": None, "co": 0.10, "aod": 0.17},
    "highveld_za":  {"no2": 0.25, "so2": 0.21, "co": 0.22, "aod": 0.00},
    "jamshedpur":   {"no2": 1.56, "so2": 0.82, "co": 0.53, "aod": 0.13},
    "korba":        {"no2": 1.40, "so2": 1.44, "co": 0.16, "aod": 0.12},
    "jubail_sa":    {"no2": 1.42, "so2": 0.12, "co": 0.16, "aod": 0.10},
    "la_oroya_pe":  {"no2": 0.58, "so2": 0.07, "co": 0.29, "aod": 0.31},
    "chuquicamata": {"no2": 0.36, "so2": 0.05, "co": 0.13, "aod": 0.24},
    "linfen_cn":    {"no2": 2.61, "so2": 0.88, "co": 0.90, "aod": 0.51},
}

HERE = os.path.dirname(os.path.abspath(__file__))
RADIUS_KM = 10                # industrial footprints are extended; controls re-extracted at 10km too
WINDOW = ("2025-09-01", "2025-11-30")   # recent settled ~90-day window (user-window stand-in)
CORE = ["no2", "so2", "co", "aod"]
FP_CEILING, CAPTURE_TARGET = 0.20, 0.90
HIGH_GRID = [1.5, 1.75, 2.0, 2.25, 2.5, 3.0]
CONCERN_GRID = [0.5, 0.75, 1.0, 1.25, 1.5]

# Known high-air-pollution industrial sites (should go red). Substitutable with supplier list.
INDUSTRIAL = [
    ("norilsk",     69.35,  88.20, "Nornickel smelter (SO2)"),
    ("highveld_za", -26.08,  28.97, "Mpumalanga coal power, world-high NO2"),
    ("jamshedpur",  22.80,  86.20, "Tata steel works"),
    ("korba",       22.35,  82.68, "Coal power + aluminium"),
    ("jubail_sa",   27.00,  49.66, "Jubail petrochem/refining"),
    ("la_oroya_pe", -11.52, -75.90, "Polymetallic smelter (SO2)"),
    ("chuquicamata",-22.32, -68.90, "Copper mine + smelter (SO2)"),
    ("linfen_cn",    36.09, 111.52, "Coal/coke basin"),
    ("ahvaz_ir",     31.32,  48.67, "Oil + steel, heavily polluted"),
    ("secunda_za",  -26.52,  29.17, "Sasol coal-to-liquids (NO2/SO2)"),
]
CONTROLS = [
    ("patagonia",  -51.0, -72.9),
    ("amazon_wet",  -4.0, -63.0),
    ("nz_south",   -45.5, 170.0),
    ("appalachia",  35.5, -82.5),
    ("puerto_rico", 18.2, -66.5),
]


def _aoi(lat, lon):
    return {"centre": {"lat": lat, "lon": lon}, "radius_km": RADIUS_KM}


def _abs_z(ind, aoi):
    try:
        snap = compute_pollutant_snapshot(aoi, ind, WINDOW, "screening", ee)
        z = snap.get(f"air.{ind}.z")
        return abs(z) if z is not None else None, ""
    except Exception as e:  # noqa: BLE001
        return None, type(e).__name__


def _extract_one(role, site):
    """One site: 4 pollutant snapshots concurrently (seed-cached if already done)."""
    sid, lat, lon = site[0], site[1], site[2]
    note = site[3] if len(site) > 3 else ""
    aoi = _aoi(lat, lon)
    cell = {"role": role, "id": sid, "note": note}
    if sid in SEED:
        for ind in CORE:
            cell[f"{ind}_absz"] = SEED[sid].get(ind)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(CORE)) as ex:
            futs = {ind: ex.submit(_abs_z, ind, aoi) for ind in CORE}
            for ind, fut in futs.items():
                z, err = fut.result()
                cell[f"{ind}_absz"] = z
                if err:
                    cell[f"{ind}_err"] = err
    zs = [cell.get(f"{ind}_absz") for ind in CORE if cell.get(f"{ind}_absz") is not None]
    cell["max_absz"] = max(zs) if zs else None
    shown = " ".join(f"{ind}={None if cell.get(f'{ind}_absz') is None else round(cell[f'{ind}_absz'],2)}" for ind in CORE)
    print(f"  [{role:10}] {sid:14} {shown}  max={None if cell['max_absz'] is None else round(cell['max_absz'],2)}", flush=True)
    return cell


def extract():
    jobs = [("industrial", s) for s in INDUSTRIAL] + [("control", s) for s in CONTROLS]
    rows = []
    # Parallelize across sites (each site also fans out its 4 pollutants) — ~5× faster.
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(_extract_one, role, s) for role, s in jobs]
        for f in concurrent.futures.as_completed(futs):
            rows.append(f.result())
    # restore stable order (industrial then control, as listed)
    order = {s[0]: i for i, s in enumerate(INDUSTRIAL + CONTROLS)}
    rows.sort(key=lambda r: order.get(r["id"], 999))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "m_calibration_sweep_c1_attribution.csv"), index=False)
    return df


def grid(df):
    ind = df[(df.role == "industrial") & df.max_absz.notna()]
    ctl = df[(df.role == "control") & df.max_absz.notna()]
    rows = []
    for concern in CONCERN_GRID:
        for high in HIGH_GRID:
            if high <= concern:
                continue
            cap = (ind.max_absz >= concern).mean()      # site fires if ANY core pollutant >= cut
            fp = (ctl.max_absz >= concern).mean()
            rows.append(dict(concern=concern, high=high,
                             capture=round(float(cap), 3), control_fp=round(float(fp), 3),
                             meets=bool(cap >= CAPTURE_TARGET and fp <= FP_CEILING)))
    g = pd.DataFrame(rows).sort_values(["concern", "high"]).reset_index(drop=True)
    g.to_csv(os.path.join(HERE, "m_calibration_sweep_c1_attribution_grid.csv"), index=False)
    feasible = g[g.meets]
    if len(feasible):
        pick = feasible.sort_values(["capture", "control_fp"], ascending=[False, True]).iloc[0]
        note = "MEETS both targets"
    else:
        under = g[g.control_fp <= FP_CEILING]
        pick = (under.sort_values("capture", ascending=False).iloc[0] if len(under)
                else g.sort_values("control_fp").iloc[0])
        note = "no point meets both — best under FP ceiling"
    return g, pick, note


def main():
    ee.Initialize(project=os.environ["EE_PROJECT_ID"])
    print(f"Step C1 (attribution) — industrial vs clean, window {WINDOW}, r={RADIUS_KM}km")
    df = extract()
    g, pick, note = grid(df)
    print("\nGrid (Concern-cut = fire threshold):")
    print(g.to_string(index=False))
    print(f"\nCapture-first pick ({note}):  Concern={pick.concern} High={pick.high} "
          f"capture={pick.capture} control_fp={pick.control_fp}  (current: Concern=1.0 High=2.0)")
    print("done")


if __name__ == "__main__":
    main()
