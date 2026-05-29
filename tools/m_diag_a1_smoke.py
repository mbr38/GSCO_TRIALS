"""M-DIAG-A1 — fast EE smoke test of the instrumented six_step.

Runs ONE indicator (air.no2) at the Sapezal centre to verify the diagnostic
bundle reaches provenance.extra._diag_bg_std before we commit to another
~45-minute full 5-seed re-run. ~30-60 seconds end-to-end.

Asserts:
  - `air.no2.site` is a finite number (the combined-reducer bare-vs-suffixed
    key fix lands the mean)
  - `_diag_bg_std` is present in extra
  - It carries `bg_std`, `bg_median`, `ring` percentiles, `site_buf`
    percentiles, and `per_day_site_means` with at least 1 entry

Reverted at Step F of the milestone (tool stays in tree as audit artefact
but loses meaningful output once the instrumentation is removed).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ee  # noqa: E402

from engine.air import compute_pollutant_snapshot  # noqa: E402


def _init_ee() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        sys.exit("EE_PROJECT_ID not set; export it and rerun.")
    ee.Initialize(project=project)


def main() -> None:
    _init_ee()
    aoi = {"centre": {"lat": -13.5417, "lon": -58.7642}, "radius_km": 5}
    time_range = ("2026-02-22", "2026-05-23")

    print("[smoke] running air.no2 at Sapezal centre…", flush=True)
    result = compute_pollutant_snapshot(
        aoi=aoi,
        pollutant="no2",
        time_range=time_range,
        mode="screening",
        ee_client=None,
    )

    site = result.get("air.no2.site")
    bg = result.get("air.no2.background")
    z = result.get("air.no2.z")
    hf = result.get("air.no2.hf")
    print(f"[smoke] site={site}  bg={bg}  z={z}  hf={hf}", flush=True)

    prov = result.get("_provenance.air.no2") or {}
    extra = prov.get("extra") or {}
    diag = extra.get("_diag_bg_std")

    print(f"[smoke] _diag_bg_std present: {diag is not None}", flush=True)
    if diag is None:
        print(f"[smoke] FAIL — extra keys: {sorted(extra.keys())}", flush=True)
        sys.exit(1)

    print(
        "[smoke] diag bundle: "
        f"bg_std={diag.get('bg_std')}  bg_median={diag.get('bg_median')}  "
        f"z_aggregate={diag.get('z_aggregate')}",
        flush=True,
    )
    ring = diag.get("ring") or {}
    site_buf = diag.get("site_buf") or {}
    pdsm = diag.get("per_day_site_means") or {}
    print(
        f"[smoke] ring keys: {sorted(ring.keys())}  "
        f"site_buf keys: {sorted(site_buf.keys())}  "
        f"per_day_site_means entries: {len(pdsm)}",
        flush=True,
    )

    if site is None:
        print("[smoke] FAIL — site is None (the band-key fix did not land)", flush=True)
        sys.exit(2)
    if not ring or ring.get("stdDev") is None:
        print("[smoke] FAIL — ring percentile bundle empty", flush=True)
        sys.exit(3)
    if not site_buf or site_buf.get("mean") is None:
        print("[smoke] FAIL — site_buf percentile bundle empty", flush=True)
        sys.exit(4)
    if len(pdsm) == 0:
        print("[smoke] FAIL — per_day_site_means is empty", flush=True)
        sys.exit(5)

    print("[smoke] OK — diagnostic surface lands; safe to run full 5-seed regen", flush=True)


if __name__ == "__main__":
    main()
