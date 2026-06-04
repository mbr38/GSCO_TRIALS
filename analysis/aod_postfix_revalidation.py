"""AOD anomaly-severity revalidation against the POST-FIX engine (M-DIAG-A4).

The aod_pm25_validation report's engine_z / engine_severity column was computed
with the OLD spatial-std denominator. AOD routes through engine.core.six_step
(engine/air.py:275), so it now uses the temporal-denominator baseline too. This
re-runs the engine AOD anomaly severity for the 23 validation sites through the
production path so §7.11.1's engine-band claims rest on the current formula.

The raw AOD <-> PM2.5 correlation (rho 0.75) is NOT engine-dependent and is not
re-run here; only the engine's anomaly-z / severity band changes with the fix.

Run from repo root:
    EE_PROJECT_ID=supply-chain-observatory python analysis/aod_postfix_revalidation.py
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

HERE = Path(__file__).resolve().parent
VAL_CSV = HERE / "aod_pm25_validation.csv"
WINDOW = ("2025-11-01", "2026-04-30")   # report §2.2, locked
RADIUS_KM = 5                            # P-04 single-supplier default
SPARSE_CONF = 0.40                       # severity.py Sparse override


def _band(z, confidence) -> str:
    if confidence is not None and confidence < SPARSE_CONF:
        return "Sparse"
    if z is None:
        return "Sparse"
    az = abs(z)
    if az >= 2.0:
        return "High"
    if az >= 1.0:
        return "Concern"
    return "Normal"


def _init_ee() -> None:
    ee.Initialize(project=os.environ.get("EE_PROJECT_ID", "supply-chain-observatory"))


def main() -> None:
    _init_ee()
    df = pd.read_csv(VAL_CSV)
    pid = "air.aod"
    rows = []
    for _, r in df.iterrows():
        aoi = {"centre": {"lat": float(r["station_lat"]),
                          "lon": float(r["station_lon"])},
               "radius_km": RADIUS_KM}
        rec = {
            "regime": r["regime"], "location": r["location"],
            "aod_mean_scaled": r["aod_mean_scaled"], "pm25_mean": r["pm25_mean_ugm3"],
            "old_z": r["engine_z"], "old_severity": r["engine_severity"],
            "old_conf": r["engine_confidence"],
        }
        print(f"[aod] {r['regime']:11s} {r['location']:24s} …", flush=True)
        try:
            snap = compute_pollutant_snapshot(aoi, "aod", WINDOW, "screening", None)
            prov = snap.get(f"_provenance.{pid}", {}) or {}
            extra = prov.get("extra", {}) or {}
            z = snap.get(f"{pid}.z")
            conf = snap.get(f"{pid}.confidence")
            rec.update({
                "post_z": z,
                "post_confidence": conf,
                "post_severity": _band(z, conf),
                "post_site": snap.get(f"{pid}.site"),
                "post_background": snap.get(f"{pid}.background"),
                "bg_std_spatial": extra.get("bg_std_spatial"),
                "bg_std_temporal": extra.get("bg_std_temporal"),
                "clim_baseline_applied": extra.get("clim_baseline_applied"),
            })
        except Exception as exc:  # noqa: BLE001
            rec["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(rec)
        print("   ", json.dumps({k: rec.get(k) for k in
              ("old_z", "post_z", "old_severity", "post_severity", "error")},
              default=str), flush=True)

    out = HERE / "aod_postfix_revalidation.json"
    out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

    ok = [r for r in rows if "error" not in r]
    # AOD quartile vs band: does the highest-AOD quartile still read mostly Normal?
    ok_sorted = sorted(ok, key=lambda r: r["aod_mean_scaled"])
    q = len(ok_sorted) // 4
    top_q = ok_sorted[-q:] if q else []
    print("\n=== POST-FIX AOD severity ===")
    print(f"sites: {len(ok)} ok, {len(rows)-len(ok)} errors")
    for tag, band in (("old", "old_severity"), ("post", "post_severity")):
        from collections import Counter
        c = Counter(r[band] for r in ok)
        print(f"  {tag:4s} band mix: {dict(c)}")
    print(f"  highest-AOD quartile (n={len(top_q)}) post-fix bands: "
          f"{[ (r['location'].split(',')[0], r['post_severity']) for r in top_q ]}")
    flips = [(r["location"].split(",")[0], r["old_severity"], r["post_severity"])
             for r in ok if r["old_severity"] != r["post_severity"]]
    print(f"  band flips old->post ({len(flips)}): {flips}")
    print(f"[aod] wrote {out}")


if __name__ == "__main__":
    main()
