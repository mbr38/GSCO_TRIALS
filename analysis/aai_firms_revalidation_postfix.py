"""AAI/FIRMS revalidation against the POST-FIX engine (M-DIAG-A4 temporal denominator).

The original aai_firms_validation report (§1-§9) was run against the OLD spatial-std
denominator. The engine now normalises the per-day anomaly by the *temporal* std of a
trailing ~90-day clean baseline (engine/core/repeatable_core.py::_climatology_bg_std).
This re-runs the SAME 10 events + 5 controls through the production path
(engine.air.compute_pollutant_snapshot -> six_step) so catch rate and false-positive
rate are measured on the formula the engine actually uses today.

Metric design (mirrors the original report, production-faithful):
  - EVENT  caught  := run snapshot over the documented PEAK window -> hf > 0
                      (>=1 day crossed z>=2.0 inside the peak), matching the original
                      "fired_in_peak" per-day metric.
  - CONTROL false+ := run snapshot over the CONTROL window -> hf > 0 (>=1 hot day in a
                      known-clean window), matching the original per-day FP metric.
  - Aggregate z>=2.0 is captured alongside for the "aggregate flag" comparison.

Radius 5 km (production standard, matches the original report). AAI only.

Run from repo root:
    EE_PROJECT_ID=supply-chain-observatory python analysis/aai_firms_revalidation_postfix.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import ee

from engine.air import compute_pollutant_snapshot

Z_THRESHOLD = 2.0
RADIUS_KM = 5
HERE = Path(__file__).resolve().parent
SUMMARY_CSV = HERE / "aai_firms_event_summary.csv"


def _init_ee() -> None:
    project = os.environ.get("EE_PROJECT_ID", "supply-chain-observatory")
    ee.Initialize(project=project)


def _load_cases() -> list[dict]:
    df = pd.read_csv(SUMMARY_CSV)
    cases = []
    for _, r in df.iterrows():
        if r["kind"] in ("fire", "dust"):
            # Events: evaluate over the documented peak window.
            win = (str(r["peak_start"]), str(r["peak_end"]))
            role = "event"
        else:
            # Controls: evaluate over the full clean control window.
            win = (str(r["window_start"]), str(r["window_end"]))
            role = "control"
        cases.append({
            "id": r["id"], "label": r["label"], "kind": r["kind"], "role": role,
            "lat": float(r["lat"]), "lon": float(r["lon"]), "window": win,
            "old_engine_z": r.get("engine_z"), "old_engine_hf": r.get("engine_hf"),
            "old_bg_std": r.get("bg_std"), "old_max_day_z": r.get("max_day_z"),
            "old_fired_in_peak": r.get("fired_in_peak"),
        })
    return cases


def _snapshot_row(case: dict) -> dict:
    aoi = {"centre": {"lat": case["lat"], "lon": case["lon"]}, "radius_km": RADIUS_KM}
    pid = "air.aai"
    out = {k: case[k] for k in ("id", "label", "kind", "role", "window")}
    try:
        snap = compute_pollutant_snapshot(aoi, "aai", case["window"], "screening", None)
        prov = snap.get(f"_provenance.{pid}", {}) or {}
        extra = prov.get("extra", {}) or {}
        z = snap.get(f"{pid}.z")
        hf = snap.get(f"{pid}.hf")
        out.update({
            "post_z": z,
            "post_hf": hf,
            "post_score": snap.get(f"{pid}.score"),
            "bg_std_spatial": extra.get("bg_std_spatial"),
            "bg_std_temporal": extra.get("bg_std_temporal"),
            "clim_baseline_applied": extra.get("clim_baseline_applied"),
            "clim_baseline_valid_days": extra.get("clim_baseline_valid_days"),
            "fired_perday": (hf is not None and hf > 0),
            "fired_aggregate": (z is not None and z >= Z_THRESHOLD),
        })
        # carry old values for side-by-side
        out.update({k: case[k] for k in
                    ("old_engine_z", "old_engine_hf", "old_bg_std",
                     "old_max_day_z", "old_fired_in_peak")})
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def main() -> None:
    _init_ee()
    cases = _load_cases()
    rows = []
    for c in cases:
        print(f"[reval] {c['role']:7s} {c['id']:22s} {c['window']} …", flush=True)
        row = _snapshot_row(c)
        rows.append(row)
        print("   ", json.dumps({k: row.get(k) for k in
              ("post_z", "post_hf", "bg_std_temporal", "fired_perday",
               "fired_aggregate", "error")}, default=str), flush=True)

    out = HERE / "aai_firms_revalidation_postfix.json"
    out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

    # ---- headline tallies -------------------------------------------------
    events = [r for r in rows if r.get("role") == "event" and "error" not in r]
    controls = [r for r in rows if r.get("role") == "control" and "error" not in r]
    errs = [r for r in rows if "error" in r]
    n_ev_caught = sum(1 for r in events if r["fired_perday"])
    n_ev_agg = sum(1 for r in events if r["fired_aggregate"])
    n_ctl_fp = sum(1 for r in controls if r["fired_perday"])
    n_ctl_agg = sum(1 for r in controls if r["fired_aggregate"])

    print("\n=== POST-FIX (temporal denominator) ===")
    print(f"Per-day catch rate (events):       {n_ev_caught}/{len(events)}")
    print(f"Aggregate z>=2.0 (events):         {n_ev_agg}/{len(events)}")
    print(f"Per-day false-positive (controls): {n_ctl_fp}/{len(controls)}")
    print(f"Aggregate z>=2.0 (controls):       {n_ctl_agg}/{len(controls)}")
    if errs:
        print(f"ERRORS: {[(r['id'], r['error']) for r in errs]}")
    print(f"[reval] wrote {out}")


if __name__ == "__main__":
    main()
