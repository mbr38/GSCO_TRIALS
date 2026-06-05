"""NDVI validation — analysis + house-style figure (evidence-only).

Reads analysis/ndvi_gpp_validation.csv. Reports cross-site Spearman ρ of raw
NDVI and of the engine anomaly score against the independent MOD17 GPP
reference, category separation, and writes the report figure.

Run: python analysis/ndvi_gpp_analysis.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "analysis" / "ndvi_gpp_validation.csv"
FIG = ROOT / "analysis" / "ndvi_gpp_fig.png"

CATS = ["stable_forest_control", "deforestation_frontier", "mine_adjacent",
        "plantation_monoculture", "drought_affected"]
CAT_LABEL = {
    "stable_forest_control": "Stable forest (control)",
    "deforestation_frontier": "Deforestation frontier",
    "mine_adjacent": "Mine-adjacent",
    "plantation_monoculture": "Plantation / monoculture",
    "drought_affected": "Drought-affected",
}

# ---- house style (matches analysis/report_fig_7_11.py) ----------------------
plt.rcParams.update({
    "font.family": "Arial",
    "font.size": 10,
    "axes.edgecolor": "#4d4d4d",
    "axes.linewidth": 0.8,
    "axes.labelcolor": "#222222",
    "xtick.color": "#4d4d4d",
    "ytick.color": "#4d4d4d",
    "axes.grid": True,
    "grid.color": "#e6e6e6",
    "grid.linewidth": 0.6,
    "figure.dpi": 150,
})
# Nature-green palette (control = deep green; stressed categories warmer/greyer)
NAT_LINE = "#3f7340"
CAT_COLOR = {
    "stable_forest_control":  "#3f7340",   # deep nature green = healthy anchor
    "deforestation_frontier": "#8aa84b",   # yellow-green
    "mine_adjacent":          "#b07a5a",   # muted clay
    "plantation_monoculture": "#6f9e6a",   # mid green (looks healthy — the confound)
    "drought_affected":       "#c9a24b",   # ochre / dry
}


def _finish(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_axisbelow(True)


def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 3:
        return np.nan, np.nan, int(m.sum())
    r, p = stats.spearmanr(x[m], y[m])
    return r, p, int(m.sum())


def main() -> None:
    df = pd.read_csv(CSV)

    # ---- correlations against the independent reference --------------------
    r_raw, p_raw, n_raw = spearman(df.ndvi_raw, df.gpp_ref)
    r_ano, p_ano, n_ano = spearman(df.ndvi_score, df.gpp_ref)

    print("=" * 68)
    print("Cross-site Spearman ρ vs MOD17 GPP (independent reference)")
    print("=" * 68)
    print(f"  raw NDVI (site mean)        ρ = {r_raw:+.2f}  (p={p_raw:.3f}, n={n_raw})  "
          "[expect POSITIVE: higher NDVI → higher GPP]")
    print(f"  engine anomaly score        ρ = {r_ano:+.2f}  (p={p_ano:.3f}, n={n_ano})  "
          "[expect NEGATIVE: higher score = worse → lower GPP]")

    # ---- category separation -----------------------------------------------
    print("\n" + "=" * 68)
    print("Category means (n=5 each)")
    print("=" * 68)
    print(f"  {'category':26s} {'GPP_ref':>9s} {'raw_NDVI':>9s} {'anom_score':>11s} {'#score=0':>9s}")
    g = df.groupby("category")
    cat_stats = {}
    for c in CATS:
        s = df[df.category == c]
        nzero = int((s.ndvi_score.fillna(-1) == 0.0).sum())
        cat_stats[c] = dict(
            gpp=s.gpp_ref.mean(), raw=s.ndvi_raw.mean(),
            score=s.ndvi_score.mean(), nzero=nzero)
        print(f"  {CAT_LABEL[c]:26s} {s.gpp_ref.mean():9.4f} {s.ndvi_raw.mean():9.3f} "
              f"{s.ndvi_score.mean():11.3f} {nzero:9d}")

    ctrl = cat_stats["stable_forest_control"]
    print("\nSeparation of each stressed category from the stable-forest control:")
    for c in CATS[1:]:
        cs = cat_stats[c]
        ref_drop = (ctrl["gpp"] - cs["gpp"]) / ctrl["gpp"] * 100
        raw_drop = (ctrl["raw"] - cs["raw"]) / ctrl["raw"] * 100
        score_up = cs["score"] - ctrl["score"]
        print(f"  {CAT_LABEL[c]:26s}  GPP {ref_drop:+5.0f}%  rawNDVI {raw_drop:+5.0f}%  "
              f"Δscore {score_up:+.2f}")

    # ---- monoculture confound spotlight (§5.4 N1/N4/N6) --------------------
    palms = df[df.id.str.startswith("plant_palm")]
    ctrl_rows = df[df.category == "stable_forest_control"]
    print("\n" + "=" * 68)
    print("Monoculture confound (oil palm vs intact-forest controls)")
    print("=" * 68)
    print(f"  oil-palm raw NDVI mean   = {palms.ndvi_raw.mean():.3f}")
    print(f"  control  raw NDVI mean   = {ctrl_rows.ndvi_raw.mean():.3f}  "
          f"(Δ = {palms.ndvi_raw.mean()-ctrl_rows.ndvi_raw.mean():+.3f})")
    print(f"  oil-palm GPP mean        = {palms.gpp_ref.mean():.4f}")
    print(f"  control  GPP mean        = {ctrl_rows.gpp_ref.mean():.4f}  "
          f"(Δ = {palms.gpp_ref.mean()-ctrl_rows.gpp_ref.mean():+.4f})")

    # ---- figure ------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.8, 5.0))
    for c in CATS:
        s = df[df.category == c]
        ax1.scatter(s.gpp_ref, s.ndvi_raw, s=58, c=CAT_COLOR[c],
                    edgecolor="#33414f", linewidth=0.6, alpha=0.92,
                    label=CAT_LABEL[c], zorder=3)
        ax2.scatter(s.gpp_ref, s.ndvi_score, s=58, c=CAT_COLOR[c],
                    edgecolor="#33414f", linewidth=0.6, alpha=0.92, zorder=3)

    ax1.set_xlabel("Independent reference — MOD17 GPP (kg C m$^{-2}$ 8d$^{-1}$, window mean)")
    ax1.set_ylabel("Raw NDVI (MOD13Q1, site window mean)")
    ax1.set_title("Raw NDVI vs productivity", fontsize=9.5, loc="left", color=NAT_LINE)
    ax1.text(0.04, 0.05, f"Spearman ρ = {r_raw:+.2f}", transform=ax1.transAxes,
             fontsize=9.5, color="#2f5530", va="bottom", fontweight="bold")
    ax1.legend(frameon=False, fontsize=7.5, loc="lower right", handletextpad=0.3)
    _finish(ax1)

    ax2.set_xlabel("Independent reference — MOD17 GPP (kg C m$^{-2}$ 8d$^{-1}$, window mean)")
    ax2.set_ylabel("Engine anomaly score (inverted, higher = worse)")
    ax2.set_title("Anomaly-scored NDVI vs productivity", fontsize=9.5, loc="left", color=NAT_LINE)
    ax2.text(0.96, 0.96, f"Spearman ρ = {r_ano:+.2f}", transform=ax2.transAxes,
             fontsize=9.5, color="#7a5a2f", va="top", ha="right", fontweight="bold")
    _finish(ax2)

    fig.suptitle("Figure — NDVI: raw greenness vs the scored anomaly, against MOD17 GPP",
                 fontsize=10.5, color="#222222", x=0.012, ha="left", y=1.01)
    fig.tight_layout()
    fig.savefig(FIG, bbox_inches="tight")
    print(f"\nwrote {FIG}")


if __name__ == "__main__":
    main()
