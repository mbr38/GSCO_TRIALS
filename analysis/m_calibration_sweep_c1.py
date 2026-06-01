"""M-CALIBRATION-SWEEP-A1 — Step C1: global air severity-band grid evidence.

Step B locks carried in:
  * Single GLOBAL zscore band (no per-indicator restructure) — operator 1 Jun 2026.
  * Capture-first: maximise event capture s.t. control false-positive rate ≤ 20%,
    target event capture ≥ 90% (CS2).
  * Grid: High ∈ {1.5,1.75,2.0,2.25,2.5,3.0}, Concern ∈ {0.5,0.75,1.0,1.25,1.5}, High>Concern.

Severity is driven by |z| (ui/components/severity.py — magnitude drives the word).
The tuning set MUST use POST-M-DIAG-A4 z (the denominator changed; the old validation
CSVs carry stale pre-fix z), so this re-extracts against the current engine.

Capture metric: an event is captured if its indicator's |aggregate z| ≥ Concern_cut
(severity ≥ Concern) over the event window. FP metric: fraction of (clean-control site
× air indicator) cells whose |z| ≥ Concern_cut. Evidence only — operator approves the
locked cutpoint before any commit (CS8). No engine changes.

Run: PYTHONPATH=. EE_PROJECT_ID=supply-chain-observatory python analysis/m_calibration_sweep_c1.py
"""
from __future__ import annotations
import os
os.environ.setdefault("EE_PROJECT_ID", "supply-chain-observatory")
import ee, numpy as np, pandas as pd

from engine.air import compute_pollutant_snapshot
from analysis.aai_firms_extract import EVENTS, _event_window

HERE = os.path.dirname(os.path.abspath(__file__))
RADIUS_KM = 5                     # AAI-validation / demo-seed standard
FP_CEILING = 0.20                 # CS2 (Step B)
CAPTURE_TARGET = 0.90             # CS2 (Step B)
HIGH_GRID = [1.5, 1.75, 2.0, 2.25, 2.5, 3.0]
CONCERN_GRID = [0.5, 0.75, 1.0, 1.25, 1.5]

# 5 re-selected clean controls (M-DIAG-A4 Phase 2 / DGC6) with their vetted clean windows.
CONTROLS = [
    ("patagonia",  -51.0, -72.9, "2021-06-01", "2021-06-30"),
    ("amazon_wet",  -4.0, -63.0, "2021-03-01", "2021-03-31"),
    ("nz_south",   -45.5, 170.0, "2021-06-01", "2021-06-30"),
    ("appalachia",  35.5, -82.5, "2021-04-01", "2021-04-30"),
    ("puerto_rico", 18.2, -66.5, "2020-05-15", "2020-06-14"),
]
# AOD biomass events (smoke regime) — coords from aod_pm25_validation.csv.
AOD_EVENTS = [
    ("chico_ca",     39.76168, -121.84047, "2020-09-08", "2020-09-20", "Bear/N.Complex smoke"),
    ("chiang_mai",   18.7909,    98.99,    "2024-03-10", "2024-03-25", "N. Thailand burn season"),
]
# Control FP measured across the air indicators that M-DIAG-A3 D2 showed over-firing.
FP_INDICATORS = ["aai", "aod", "no2", "so2", "co", "hcho", "o3"]


def _aoi(lat, lon):
    return {"centre": {"lat": lat, "lon": lon}, "radius_km": RADIUS_KM}


def _abs_z(indicator, aoi, window):
    try:
        snap = compute_pollutant_snapshot(aoi, indicator, window, "screening", ee)
        z = snap.get(f"air.{indicator}.z")
        hf = snap.get(f"air.{indicator}.hf")
        return (abs(z) if z is not None else None), hf, ""
    except Exception as e:  # noqa: BLE001
        return None, None, f"{type(e).__name__}: {str(e)[:50]}"


def extract():
    rows = []
    # Events — AAI (fire/dust) + AOD (biomass). Captured indicator's |z| over event window.
    for ev in EVENTS:
        w = _event_window(ev)
        z, hf, err = _abs_z("aai", _aoi(ev["lat"], ev["lon"]), w)
        rows.append(dict(role="event", indicator="aai", id=ev["id"], kind=ev["kind"],
                         window=f"{w[0]}/{w[1]}", abs_z=z, hf=hf, error=err))
        print(f"  event   aai  {ev['id']:14} |z|={None if z is None else round(z,2)} {err}")
    for eid, lat, lon, s, e, note in AOD_EVENTS:
        z, hf, err = _abs_z("aod", _aoi(lat, lon), (s, e))
        rows.append(dict(role="event", indicator="aod", id=eid, kind="biomass",
                         window=f"{s}/{e}", abs_z=z, hf=hf, error=err))
        print(f"  event   aod  {eid:14} |z|={None if z is None else round(z,2)} {err}")
    # Controls — every air indicator at each clean site (each cell = a potential false High).
    for cid, lat, lon, s, e in CONTROLS:
        for ind in FP_INDICATORS:
            z, hf, err = _abs_z(ind, _aoi(lat, lon), (s, e))
            rows.append(dict(role="control", indicator=ind, id=cid, kind="clean",
                             window=f"{s}/{e}", abs_z=z, hf=hf, error=err))
            print(f"  control {ind:4} {cid:14} |z|={None if z is None else round(z,2)} {err}")
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "m_calibration_sweep_c1_zvalues.csv"), index=False)
    return df


def grid(df):
    ev = df[(df.role == "event") & df.abs_z.notna()]
    ct = df[(df.role == "control") & df.abs_z.notna()]
    rows = []
    for concern in CONCERN_GRID:
        for high in HIGH_GRID:
            if high <= concern:
                continue
            cap = (ev.abs_z >= concern).mean()                     # severity ≥ Concern fires
            fp = (ct.abs_z >= concern).mean()
            cap_high = (ev.abs_z >= high).mean()
            fp_high = (ct.abs_z >= high).mean()
            rows.append(dict(concern=concern, high=high,
                             event_capture=round(float(cap), 3), control_fp=round(float(fp), 3),
                             event_high=round(float(cap_high), 3), control_fp_high=round(float(fp_high), 3),
                             meets=bool(cap >= CAPTURE_TARGET and fp <= FP_CEILING)))
    g = pd.DataFrame(rows).sort_values(["concern", "high"]).reset_index(drop=True)
    g.to_csv(os.path.join(HERE, "m_calibration_sweep_c1_grid.csv"), index=False)
    # Capture-first pick: among grid points meeting both targets, the one with highest capture
    # then lowest FP; if none meet, report the best-capture-under-ceiling point.
    feasible = g[g.meets]
    if len(feasible):
        pick = feasible.sort_values(["event_capture", "control_fp"], ascending=[False, True]).iloc[0]
        note = "meets both targets"
    else:
        under = g[g.control_fp <= FP_CEILING]
        pick = (under.sort_values("event_capture", ascending=False).iloc[0] if len(under)
                else g.sort_values("control_fp").iloc[0])
        note = "NO grid point meets both — best under FP ceiling (or lowest FP)"
    return g, pick, note


def main():
    ee.Initialize(project=os.environ["EE_PROJECT_ID"])
    print("Step C1 — extracting POST-FIX z for calibration set …")
    df = extract()
    g, pick, note = grid(df)
    # hf-based separation (the hypothesis: an hf-banded tile separates events from controls)
    ev_hf = df[(df.role=="event") & df.hf.notna()]["hf"]
    ct_hf = df[(df.role=="control") & df.hf.notna()]["hf"]
    print("\nhf separation check (severity from hot-day fraction instead of aggregate z):")
    print(f"  events  hf: n={len(ev_hf)} median={ev_hf.median():.3f} mean={ev_hf.mean():.3f} min={ev_hf.min():.3f} max={ev_hf.max():.3f}")
    print(f"  controls hf: n={len(ct_hf)} median={ct_hf.median():.3f} mean={ct_hf.mean():.3f} min={ct_hf.min():.3f} max={ct_hf.max():.3f}")
    for cut in [0.05,0.10,0.15,0.20,0.25]:
        cap=(ev_hf>=cut).mean(); fp=(ct_hf>=cut).mean()
        print(f"  hf-cut {cut:.2f}: event_capture={cap:.2f} control_fp={fp:.2f} {'<= MEETS >=' if cap>=0.9 and fp<=0.2 else ''}")
    print("\nGrid (Concern-cut drives the fire threshold):")
    print(g.to_string(index=False))
    print(f"\nCapture-first pick ({note}):")
    print(f"  Concern={pick.concern}  High={pick.high}  "
          f"event_capture={pick.event_capture}  control_fp={pick.control_fp}")
    print(f"  (current bands: Concern=1.0, High=2.0)")
    print("done — wrote m_calibration_sweep_c1_zvalues.csv + _grid.csv")


if __name__ == "__main__":
    main()
