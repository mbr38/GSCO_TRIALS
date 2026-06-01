"""M-CALIBRATION-SWEEP-A1 C6 — VIIRS LIT_CONTRAST_THRESHOLD sweep (decision gate).

Diagnostic-directed (M-VIIRS-DIAG-A1): P_FLOOR is inert; the lever is the lit-contrast
threshold (0.02 too low → persistence pins at 1.0). Extract per-timestep contrasts once
per AOI (parallel), then re-derive persistence/score at each candidate lit-threshold.
Gate: does raising it separate middle from heavy? If not → escalate to purpose-built method.
Evidence only, no engine change.
Run: PYTHONPATH=. EE_PROJECT_ID=supply-chain-observatory python analysis/m_calibration_sweep_c6.py
"""
from __future__ import annotations
import os
os.environ.setdefault("EE_PROJECT_ID", "supply-chain-observatory")
import concurrent.futures
import ee, numpy as np, pandas as pd
from engine.ghg import _michelson_contrast, _percentile, _persistence_factor
from engine.core.repeatable_core import per_image_site_ring_series
from engine.core.buffers import background_ring
from engine.ghg import GHG_INDICATOR_CONFIG
from engine.constants import VIIRS_CONTRAST_PERCENTILE, VIIRS_PERSISTENCE_FLOOR, VIIRS_PERSISTENCE_FLOOR_DISCOUNT
from analysis.m_viirs_diag_a1_probe import AOIS, WINDOW, RADIUS_KM

HERE = os.path.dirname(os.path.abspath(__file__))
LIT_GRID = [0.02, 0.05, 0.10, 0.15, 0.20, 0.30]   # current 0.02 + sweep up
CFG = GHG_INDICATOR_CONFIG["viirs"]


def contrasts_for(aoi):
    ic = ee.ImageCollection(CFG.asset_id).select(CFG.band)
    ring = background_ring(aoi["centre"], aoi["radius_km"])
    s = per_image_site_ring_series(aoi, ic, CFG.band, WINDOW, scale=CFG.scale_m,
                                   ring=ring, indicator_id="ghg.viirs")
    return [_michelson_contrast(site, r) for _iso, site, r in s.timesteps]


def score_at(contrasts, lit_thr):
    n = len(contrasts)
    if n == 0:
        return None, None, None
    lit = [c for c in contrasts if c >= lit_thr]
    persistence = len(lit) / n
    if not lit:
        return 0.0, 0.0, 0.0
    cow = _percentile(sorted(lit), VIIRS_CONTRAST_PERCENTILE)
    pf = VIIRS_PERSISTENCE_FLOOR_DISCOUNT + (1 - VIIRS_PERSISTENCE_FLOOR_DISCOUNT) * min(persistence / VIIRS_PERSISTENCE_FLOOR, 1.0)
    return persistence, pf, max(0.0, min(1.0, cow * pf))


def _one(rec):
    name, lat, lon, tier, note = rec
    aoi = {"centre": {"lat": lat, "lon": lon}, "radius_km": RADIUS_KM}
    try:
        cs = contrasts_for(aoi)
    except Exception as e:  # noqa: BLE001
        print(f"  {name:13} ERROR {type(e).__name__}", flush=True)
        return None
    row = {"name": name, "tier": tier, "n_ts": len(cs)}
    for lt in LIT_GRID:
        p, pf, sc = score_at(cs, lt)
        row[f"persist@{lt}"] = p
        row[f"score@{lt}"] = sc
    print(f"  {name:13} n={len(cs):3} "
          + " ".join(f"s@{lt}={None if row[f'score@{lt}'] is None else round(row[f'score@{lt}'],2)}" for lt in LIT_GRID), flush=True)
    return row


def main():
    ee.Initialize(project=os.environ["EE_PROJECT_ID"])
    print(f"C6 — VIIRS lit-threshold sweep, {len(AOIS)} AOIs, window {WINDOW}")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        rows = [r for r in ex.map(_one, AOIS) if r]
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "m_calibration_sweep_c6_lit_sweep.csv"), index=False)
    # Tier separation per lit-threshold: do middle scores drop below heavy as threshold rises?
    print("\nTier-mean SCORE by lit-threshold (gate: does middle separate from heavy?):")
    print(f"{'lit_thr':>8} {'heavy':>7} {'middle':>7} {'quiet':>7}  middle<heavy?")
    for lt in LIT_GRID:
        col = f"score@{lt}"
        h = df[df.tier=='heavy'][col].mean()
        m = df[df.tier=='middle'][col].mean()
        q = df[df.tier=='quiet'][col].mean()
        sep = "YES" if m < h - 0.10 else "no"
        print(f"{lt:>8} {h:>7.2f} {m:>7.2f} {q:>7.2f}  {sep}")
    print("done")


if __name__ == "__main__":
    main()
