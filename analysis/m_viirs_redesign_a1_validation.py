"""M-VIIRS-REDESIGN-A1 Step D — validate the production two-output VIIRS path.

Runs engine.ghg.compute_viirs_two_output at the 17 AOIs (parallel) and checks the
regression locks: VR8 (Comodoro/patagonia_seed flaring fires), VR9 (quiet AOIs don't
fire), and heavy/middle separation from quiet. Production code path, no engine change.

Run: PYTHONPATH=. EE_PROJECT_ID=supply-chain-observatory python analysis/m_viirs_redesign_a1_validation.py
"""
from __future__ import annotations
import os
os.environ.setdefault("EE_PROJECT_ID", "supply-chain-observatory")
import concurrent.futures
import ee, pandas as pd
from engine.ghg import compute_viirs_two_output
from analysis.m_ghg_sanity_a1_probe import AOIS, WINDOW, RADIUS_KM

HERE = os.path.dirname(os.path.abspath(__file__))
QUIET = {"patagonia_diag", "nz_south", "appalachia", "amazon_wet"}


def _one(rec):
    rid, lat, lon, tier, note = rec
    aoi = {"centre": {"lat": lat, "lon": lon}, "radius_km": RADIUS_KM}
    row = {"id": rid, "tier": tier}
    try:
        r = compute_viirs_two_output(aoi, WINDOW, "screening", ee)
        row["flaring"] = r.get("ghg.viirs.score")
        row["flaring_frac"] = r.get("ghg.viirs.flaring_frac")
        row["attributability"] = r.get("ghg.viirs.attributability_state")
        row["lit_pct"] = r.get("ghg.viirs.lit_contrast_percentile")
    except Exception as e:  # noqa: BLE001
        row["error"] = f"{type(e).__name__}: {str(e)[:50]}"
    print(f"  {rid:22} {tier:4} flaring={row.get('flaring')} attrib={row.get('attributability')} "
          f"lit_pct={row.get('lit_pct')} {row.get('error','')}", flush=True)
    return row


def main():
    ee.Initialize(project=os.environ["EE_PROJECT_ID"])
    print(f"Step D validation — {len(AOIS)} AOIs, production compute_viirs_two_output")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(_one, AOIS))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "m_viirs_redesign_a1_validation.csv"), index=False)
    fl = df.set_index("id")["flaring"]
    como = fl.get("patagonia_seed")
    quiet_max = df[df.id.isin(QUIET)]["flaring"].max()
    print(f"\nVR8 Comodoro flaring = {como}  (fires if > 0)")
    print(f"VR9 quiet max flaring = {quiet_max}  (guard if low)")
    print("tier means:\n", df.groupby("tier")["flaring"].mean().round(3).to_string())
    print("done")


if __name__ == "__main__":
    main()
