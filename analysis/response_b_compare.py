"""CH4 Response B — Step C comparison: 5 km vs 15 km AOI.

Merges the original 5 km extraction with the widened 15 km re-extraction and
produces the side-by-side table, the firing-rate change, the CH4-vs-ODIAC
correlation update, and the comparison scatter (plot8). Saves:
  - analysis/plots/plot8_ch4z15_vs_odiac.png
  - analysis/response_b_comparison.md  (side-by-side table + verdict stats)

Run: python analysis/response_b_compare.py
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr, pearsonr

from analysis.analysis_plots import REGIME_ORDER, REGIME_COLOR, CH4_FIRE_Z, PLOTS

_HERE = os.path.dirname(os.path.abspath(__file__))


def load():
    a = pd.read_csv(os.path.join(_HERE, "ghg_odiac_validation.csv"))
    w = pd.read_csv(os.path.join(_HERE, "ghg_odiac_validation_widened_aoi.csv"))
    m = a[["regime", "location", "ch4_z", "ch4_site_ppb", "odiac_point_tco2"]].merge(
        w[["location", "ch4_z_15km", "ch4_site_ppb_15km"]], on="location")
    m["regime"] = pd.Categorical(m["regime"], categories=REGIME_ORDER, ordered=True)
    m["delta_z"] = m["ch4_z_15km"] - m["ch4_z"]
    return m


def corr(m, zcol):
    d = m[(m.odiac_point_tco2 > 0) & m[zcol].notna()].copy()
    lo = np.log10(d.odiac_point_tco2.clip(lower=1e-3))
    return (round(spearmanr(d[zcol], lo)[0], 2),
            round(pearsonr(d[zcol], lo)[0], 2), len(d))


def scatter(m):
    fig, ax = plt.subplots(figsize=(7, 5))
    for reg in REGIME_ORDER:
        sub = m[m.regime == reg]
        x = np.log10(sub.odiac_point_tco2.where(sub.odiac_point_tco2 > 0))
        ax.scatter(x, sub.ch4_z_15km, label=reg, color=REGIME_COLOR[reg],
                   s=70, edgecolor="k", linewidth=0.4, alpha=0.85, zorder=3)
        if reg in ("Landfill", "Oil/Gas"):
            for _, r in sub.iterrows():
                if r.odiac_point_tco2 > 0 and pd.notna(r.ch4_z_15km):
                    ax.annotate(r.location, (np.log10(r.odiac_point_tco2), r.ch4_z_15km),
                                fontsize=6, xytext=(3, 2), textcoords="offset points")
    ax.axhline(CH4_FIRE_Z, color="crimson", ls="--", lw=1, label=f"CH4 z = {CH4_FIRE_Z}")
    ax.set_xlabel("log10(ODIAC point sample, annualised t CO2 / cell)")
    ax.set_ylabel("CH4 anomaly z @ 15 km AOI")
    ax.set_title("Plot 8 — CH4 anomaly z (15 km AOI) vs ODIAC, by regime")
    ax.legend(fontsize=7); ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "plot8_ch4z15_vs_odiac.png"), dpi=130)
    plt.close(fig)


def main():
    m = load()
    lines = ["# Response B — 5 km vs 15 km AOI comparison\n",
             "\n## Side-by-side CH4 anomaly z\n",
             "| regime | location | z @5km | z @15km | Δ |",
             "|---|---|---|---|---|"]
    for _, r in m.iterrows():
        z5 = f"{r.ch4_z:+.2f}" if pd.notna(r.ch4_z) else "n/a"
        z15 = f"{r.ch4_z_15km:+.2f}" if pd.notna(r.ch4_z_15km) else "n/a"
        dz = f"{r.delta_z:+.2f}" if pd.notna(r.delta_z) else "n/a"
        fire = " 🔥" if (pd.notna(r.ch4_z_15km) and r.ch4_z_15km > CH4_FIRE_Z) else ""
        lines.append(f"| {r.regime} | {r.location} | {z5} | {z15}{fire} | {dz} |")

    f5 = m[m.ch4_z > CH4_FIRE_Z].location.tolist()
    f15 = m[m.ch4_z_15km > CH4_FIRE_Z].location.tolist()
    lines += ["\n## Firing (z > 1.5)\n",
              f"- **5 km:** {len(f5)}/25 — {f5 or '(none)'}",
              f"- **15 km:** {len(f15)}/25 — {f15 or '(none)'}\n",
              "Per regime (fired at 15 km):"]
    for reg in REGIME_ORDER:
        sub = m[m.regime == reg]
        ff = sub[sub.ch4_z_15km > CH4_FIRE_Z].location.tolist()
        lines.append(f"  - {reg}: {ff or '(none)'}")

    c5, c15 = corr(m, "ch4_z"), corr(m, "ch4_z_15km")
    lines += ["\n## CH4 vs log10(ODIAC point) correlation\n",
              f"- **5 km:** Spearman {c5[0]}, Pearson {c5[1]} (n={c5[2]})",
              f"- **15 km:** Spearman {c15[0]}, Pearson {c15[1]} (n={c15[2]})\n",
              "## Distribution\n",
              f"- max z: 5 km **{m.ch4_z.max():.2f}** → 15 km **{m.ch4_z_15km.max():.2f}**",
              f"- mean |z|: 5 km **{m.ch4_z.abs().mean():.2f}** → 15 km **{m.ch4_z_15km.abs().mean():.2f}**",
              f"- moved toward firing (Δz>0): **{int((m.delta_z>0).sum())}/{int(m.delta_z.notna().sum())}**"]

    with open(os.path.join(_HERE, "response_b_comparison.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    scatter(m)
    print("\n".join(lines))
    print("\nSaved plot8 + response_b_comparison.md")


if __name__ == "__main__":
    main()
