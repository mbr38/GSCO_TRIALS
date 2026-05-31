"""M-VIIRS-DIAG-A1 — Mixed-AOI VIIRS distribution diagnostic (Step C).

Empirical diagnostic, NO engine changes (DG10). Runs the production VIIRS
persistence-weighted ring-relative sustained-contrast scoring
(`engine.ghg.compute_viirs_sustained_contrast`, M-GHG-REDESIGN-A1) across 12 AOIs
in three industrial-intensity tiers, captures the three DG5 metrics, applies the
DG6 decision criteria, and runs the (free) P_FLOOR micro-sweep (§4.4, Step B:
unconditional).

Outputs (DG9):
  analysis/m_viirs_diag_a1_results.csv
  analysis/m_viirs_diag_a1_plot_{persistence,contrast,score}.png
  analysis/m_viirs_diag_a1_pfloor_sweep.csv

Run: PYTHONPATH=. EE_PROJECT_ID=supply-chain-observatory python analysis/m_viirs_diag_a1_probe.py

Decision criteria (DG6), applied mechanically with this precedence: saturation → working → ambiguous.
  saturation  = (#heavy pf>0.85 ≥ 3) AND (#middle pf>0.85 ≥ 2)
  working     = NOT saturation AND ( (#middle in [0.3,0.7] ≥ 3)            # middle cluster
                                     OR (#heavy in [0.6,0.95] ≥ 3 AND #heavy>0.95 ≤ 1) )  # heavy span, not all ~1.0
  ambiguous   = otherwise
"""
from __future__ import annotations
import os
os.environ.setdefault("EE_PROJECT_ID", "supply-chain-observatory")

import ee, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

from engine.ghg import compute_viirs_sustained_contrast, _persistence_factor
from engine.constants import (
    VIIRS_PERSISTENCE_FLOOR, VIIRS_PERSISTENCE_FLOOR_DISCOUNT,
)

HERE = os.path.dirname(os.path.abspath(__file__))
RADIUS_KM = 10          # Step B
WINDOW = ("2025-09-01", "2025-11-30")   # Step B: settled recent 90 days
PF_SAT = 0.85           # DG6 persistence_factor saturation threshold

# 12 AOIs (Step B locked). (name, lat, lon, tier, ground_truth_note)
AOIS = [
    # Heavy (DG2)
    ("Norilsk",       69.35,  88.20, "heavy", "Nornickel smelter complex; among brightest industrial NTL on Earth (also demo seed)"),
    ("Korba",         22.35,  82.68, "heavy", "Korba coal-power + aluminium cluster, Chhattisgarh IN"),
    ("Jamshedpur",    22.80,  86.20, "heavy", "Tata steel works, Jharkhand IN"),
    ("Yanbu",         24.09,  38.06, "heavy", "Yanbu petrochemical/refining city, Saudi Red Sea coast"),
    # Middle (DG4 — Step B accepted)
    ("Ploiesti",      44.94,  26.03, "middle", "Mid-size oil-refining city, Romania"),
    ("Pavlodar",      52.29,  76.95, "middle", "Refinery + aluminium smelter, secondary city KZ"),
    ("Vadodara",      22.31,  73.18, "middle", "Gujarat petrochem/industrial secondary city IN"),
    ("Rondonopolis", -16.47, -54.64, "middle", "Soy-crushing agro-industrial hub, Mato Grosso BR"),
    # Quiet (DG3 — vetted clean under M-DIAG-A4)
    ("Patagonia",    -51.00, -72.90, "quiet", "Patagonian steppe wilderness (also demo seed)"),
    ("NZ_South",     -45.50, 170.00, "quiet", "NZ South Island rural"),
    ("Appalachia",    35.50, -82.50, "quiet", "W. North Carolina forest"),
    ("Amazon_wet",    -4.00, -63.00, "quiet", "Central Amazon interior"),
]
PFLOOR_SWEEP = [VIIRS_PERSISTENCE_FLOOR, VIIRS_PERSISTENCE_FLOOR * 1.10,
                VIIRS_PERSISTENCE_FLOOR * 1.25, VIIRS_PERSISTENCE_FLOOR * 1.50]


def _pf(persistence, p_floor=VIIRS_PERSISTENCE_FLOOR, d=VIIRS_PERSISTENCE_FLOOR_DISCOUNT):
    """persistence_factor at an arbitrary P_FLOOR (pure math — §4.4 sweep is free)."""
    if persistence is None:
        return None
    return d + (1.0 - d) * min(persistence / p_floor, 1.0)


def extract():
    rows = []
    for name, lat, lon, tier, note in AOIS:
        aoi = {"centre": {"lat": lat, "lon": lon}, "radius_km": RADIUS_KM}
        rec = dict(name=name, tier=tier, lat=lat, lon=lon, note=note,
                   site=None, contrast=None, persistence=None, score=None,
                   confidence=None, persistence_factor=None, n_valid=None, n_lit=None, error="")
        try:
            r = compute_viirs_sustained_contrast(aoi, WINDOW, "screening", ee)
            rec["site"] = r.get("ghg.viirs.site")
            rec["contrast"] = r.get("ghg.viirs.contrast")
            rec["persistence"] = r.get("ghg.viirs.persistence")
            rec["score"] = r.get("ghg.viirs.score")
            rec["confidence"] = r.get("ghg.viirs.confidence")
            rec["persistence_factor"] = (
                _persistence_factor(rec["persistence"]) if rec["persistence"] is not None else None)
            extra = (r.get("_provenance.ghg.viirs", {}) or {}).get("extra", {}) or {}
            rec["n_valid"] = extra.get("n_valid") or extra.get("n_valid_dates")
            rec["n_lit"] = extra.get("n_lit")
        except Exception as e:  # noqa: BLE001
            rec["error"] = f"{type(e).__name__}: {str(e)[:80]}"
        pf = rec["persistence_factor"]
        print(f"  [{tier:6}] {name:13} persistence={rec['persistence']} "
              f"contrast={rec['contrast']} pf={None if pf is None else round(pf,3)} "
              f"score={rec['score']} {rec['error']}")
        rows.append(rec)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "m_viirs_diag_a1_results.csv"), index=False)
    return df


def verdict(df):
    ok = df[df.persistence_factor.notna()]
    heavy = ok[ok.tier == "heavy"]["persistence_factor"]
    middle = ok[ok.tier == "middle"]["persistence_factor"]
    n_heavy_sat = int((heavy > PF_SAT).sum())
    n_mid_sat = int((middle > PF_SAT).sum())
    n_mid_cluster = int(((middle >= 0.3) & (middle <= 0.7)).sum())
    n_heavy_span = int(((heavy >= 0.6) & (heavy <= 0.95)).sum())
    n_heavy_top = int((heavy > 0.95).sum())
    saturation = (n_heavy_sat >= 3) and (n_mid_sat >= 2)
    working = (not saturation) and ((n_mid_cluster >= 3) or (n_heavy_span >= 3 and n_heavy_top <= 1))
    bucket = "saturation" if saturation else ("working-correctly" if working else "ambiguous")
    detail = dict(n_heavy_sat=n_heavy_sat, n_mid_sat=n_mid_sat, n_mid_cluster=n_mid_cluster,
                  n_heavy_span=n_heavy_span, n_heavy_top=n_heavy_top, bucket=bucket)
    print("\nDG6 verdict:", detail)
    return detail


def plots(df):
    ok = df[df.persistence_factor.notna()].copy()
    colors = {"heavy": "tab:red", "middle": "tab:orange", "quiet": "tab:green"}
    tiers = ["heavy", "middle", "quiet"]
    for metric, fname, ref in [
        ("persistence_factor", "plot_persistence", PF_SAT),
        ("contrast", "plot_contrast", None),
        ("score", "plot_score", None)]:
        fig, ax = plt.subplots(figsize=(7, 4.2))
        for i, t in enumerate(tiers):
            sub = ok[ok.tier == t]
            xs = np.random.default_rng(i + 1).normal(i, 0.05, len(sub))
            ax.scatter(xs, sub[metric], color=colors[t], s=70, label=t, edgecolor="k", linewidth=0.4)
            for _, row in sub.iterrows():
                ax.annotate(row["name"], (i, row[metric]), fontsize=6, xytext=(6, 0),
                            textcoords="offset points", va="center")
        if ref is not None:
            ax.axhline(ref, color="grey", ls="--", lw=1, label=f"DG6 sat threshold {ref}")
        ax.set_xticks(range(len(tiers))); ax.set_xticklabels(tiers)
        ax.set_ylabel(metric); ax.set_title(f"M-VIIRS-DIAG-A1 — {metric} by tier ({WINDOW[0]}→{WINDOW[1]})")
        ax.grid(axis="y", alpha=0.3); ax.legend(fontsize=7)
        fig.tight_layout(); fig.savefig(os.path.join(HERE, f"m_viirs_diag_a1_{fname}.png"), dpi=130)


def pfloor_sweep(df):
    ok = df[df.persistence.notna()]
    rows = []
    for pf_val in PFLOOR_SWEEP:
        for _, r in ok.iterrows():
            pf = _pf(r["persistence"], p_floor=pf_val)
            rows.append(dict(p_floor=round(pf_val, 3), name=r["name"], tier=r["tier"],
                             persistence=r["persistence"], persistence_factor=pf,
                             score=(r["contrast"] * pf if r["contrast"] is not None else None)))
    sweep = pd.DataFrame(rows)
    sweep.to_csv(os.path.join(HERE, "m_viirs_diag_a1_pfloor_sweep.csv"), index=False)
    # summary: how many heavy/middle saturate (pf>0.85) at each floor
    print("\nP_FLOOR sweep (saturating pf>0.85 counts):")
    for pf_val in PFLOOR_SWEEP:
        s = sweep[sweep.p_floor == round(pf_val, 3)]
        nh = int((s[s.tier == "heavy"].persistence_factor > PF_SAT).sum())
        nm = int((s[s.tier == "middle"].persistence_factor > PF_SAT).sum())
        nq = int((s[s.tier == "quiet"].persistence_factor > PF_SAT).sum())
        print(f"  P_FLOOR={pf_val:.3f}: heavy_sat={nh}/4 middle_sat={nm}/4 quiet_sat={nq}/4")
    return sweep


def main():
    ee.Initialize(project=os.environ["EE_PROJECT_ID"])
    print(f"M-VIIRS-DIAG-A1 — 12 AOIs, r={RADIUS_KM}km, window {WINDOW}")
    df = extract()
    verdict(df)
    plots(df)
    pfloor_sweep(df)
    print("\ndone — wrote results CSV, 3 plots, P_FLOOR sweep CSV")


if __name__ == "__main__":
    main()
