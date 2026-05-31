"""M-DIAG-A4 Phase 2 — live validation of the climatology-baseline denominator.

Runs the POST-FIX engine (engine.air.compute_pollutant_snapshot → six_step)
for AAI + O3 at:
  - a re-selected clean control (Patagonia / Comodoro Rivadavia), and
  - the strongest validation event (Quebec 2023 wildfires, DGC12 candidate),
and surfaces, per indicator/location:
  - bg_std_spatial   (the OLD denominator — spatial std of the time-mean ring)
  - bg_std_temporal  (the NEW denominator — temporal σ of the site's per-day series)
  - ratio            (temporal / spatial — the M-DIAG-A3 §4 inflation factor)
  - z, hf, score     (now normalised by the temporal denominator)
  - clim_baseline_*  (applied / valid_days / sparse provenance)

Numerical-correctness reading (spec v2.0 §0): the win is that bg_std_temporal
is the right scale and the resulting z is interpretable — NOT that the control
stops firing. We expect ratio > 1 at clean controls (spatial std collapses; the
temporal std is the honest scale) and a strong positive z at the event.

Run from repo root:
    EE_PROJECT_ID=supply-chain-observatory python analysis/m_diag_a4_validation_probe.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ee

from engine.air import compute_pollutant_snapshot


# (name, centre lat/lon, radius_km, window) — windows chosen so the trailing
# 90-day climatology baseline has S5P coverage (AAI archive starts 2018-07).
_CASES = [
    # Clean control — austral winter, low biomass-burning aerosol.
    ("Patagonia control (clean)", -45.864, -67.496, 10, ("2023-06-01", "2023-09-01")),
    # Strong event — Quebec 2023 wildfire smoke peaked Jun-Jul 2023.
    ("Quebec 2023 wildfire (event)", 52.0, -72.0, 25, ("2023-06-01", "2023-07-15")),
]

_POLLUTANTS = ["aai", "o3"]


def _init_ee() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        sys.exit("EE_PROJECT_ID is not set; aborting.")
    ee.Initialize(project=project)


def _row(name: str, pollutant: str, snap: dict) -> dict:
    pid = f"air.{pollutant}"
    prov = snap.get(f"_provenance.{pid}", {}) or {}
    extra = prov.get("extra", {}) or {}
    spatial = extra.get("bg_std_spatial")
    temporal = extra.get("bg_std_temporal")
    ratio = (temporal / spatial) if (spatial and temporal) else None
    return {
        "location": name,
        "indicator": pid,
        "bg_std_spatial": spatial,
        "bg_std_temporal": temporal,
        "ratio_temporal_over_spatial": ratio,
        "z": snap.get(f"{pid}.z"),
        "hf": snap.get(f"{pid}.hf"),
        "score": snap.get(f"{pid}.score"),
        "clim_baseline_applied": extra.get("clim_baseline_applied"),
        "clim_baseline_valid_days": extra.get("clim_baseline_valid_days"),
        "clim_baseline_sparse": extra.get("clim_baseline_sparse"),
    }


def main() -> None:
    _init_ee()
    rows = []
    for name, lat, lon, radius_km, window in _CASES:
        aoi = {"centre": {"lat": lat, "lon": lon}, "radius_km": radius_km}
        for pollutant in _POLLUTANTS:
            print(f"[probe] {name} — {pollutant} {window} (r={radius_km}km)…", flush=True)
            try:
                snap = compute_pollutant_snapshot(
                    aoi, pollutant, window, "screening", None,
                )
                row = _row(name, pollutant, snap)
            except Exception as exc:  # noqa: BLE001 — record the failure, keep going
                row = {"location": name, "indicator": f"air.{pollutant}",
                       "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            print("   ", json.dumps(row, default=str), flush=True)

    out = Path(__file__).resolve().parent / "m_diag_a4_validation_probe.json"
    out.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"[probe] wrote {out}")


if __name__ == "__main__":
    main()
