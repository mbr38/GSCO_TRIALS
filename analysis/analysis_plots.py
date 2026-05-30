"""Steps D + F — analysis & plots for the GHG ↔ ODIAC + OCO validation.

Loads analysis/ghg_odiac_validation.csv (after both extraction scripts have
run) and produces:

  Part A (activity validation, ODIAC):
    plot1  CH4 anomaly z      vs log10(ODIAC point)   — landfills annotated
    plot2  VIIRS              vs log10(ODIAC point)
    plot3  ODIAC point        vs ODIAC AOI-mean        — sampling robustness
    plot4  CH4 anomaly z      vs VIIRS                 — the proxy's two axes
    + per-regime Pearson/Spearman table (CH4–ODIAC, VIIRS–ODIAC)
    + divergence cases (CH4 z>1.5 firing by regime)

  Part B (concentration validation, OCO XCO2):
    plot5  VIIRS              vs XCO2 delta
    plot6  CH4 raw conc.      vs XCO2 delta
    plot7  GHG activity score vs XCO2 delta           — combined signal
    + per-regime Pearson/Spearman table (VIIRS–XCO2, CH4–XCO2)

Saves PNGs to analysis/plots/ and writes correlation tables to
analysis/corr_tables.md. Plain script so it runs head-less and is also the
source for the committed notebook.

Run: python analysis/analysis_plots.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

from analysis.locations import CSV_PATH

_HERE = os.path.dirname(os.path.abspath(__file__))
PLOTS = os.path.join(_HERE, "plots")
CORR_TABLES_MD = os.path.join(_HERE, "corr_tables.md")
CH4_FIRE_Z = 1.5  # anomaly-z threshold for "CH4 fired" (brief Step D)

REGIME_ORDER = ["Urban", "Oil/Gas", "Coal", "Landfill", "Rural"]
REGIME_COLOR = {
    "Urban": "#1f77b4", "Oil/Gas": "#d62728", "Coal": "#7f7f7f",
    "Landfill": "#2ca02c", "Rural": "#ff7f0e",
}


def load() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH)
    df["regime"] = pd.Categorical(df["regime"], categories=REGIME_ORDER, ordered=True)
    return df


def _scatter(ax, df, xcol, ycol, *, logx=False, annotate_regime=None):
    for reg in REGIME_ORDER:
        sub = df[df["regime"] == reg]
        x = sub[xcol].astype(float).values
        y = sub[ycol].astype(float).values
        if logx:
            x = np.where(x > 0, x, np.nan)
            x = np.log10(x)
        ax.scatter(x, y, label=reg, color=REGIME_COLOR[reg], s=70,
                   edgecolor="k", linewidth=0.4, alpha=0.85, zorder=3)
        if annotate_regime and reg == annotate_regime:
            for _, r in sub.iterrows():
                xv = r[xcol]
                if logx:
                    xv = np.log10(xv) if xv and xv > 0 else np.nan
                if pd.notna(xv) and pd.notna(r[ycol]):
                    ax.annotate(r["location"], (xv, r[ycol]), fontsize=7,
                                xytext=(4, 3), textcoords="offset points")
    ax.legend(fontsize=7, framealpha=0.9)
    ax.grid(True, alpha=0.25)


def part_a_plots(df: pd.DataFrame):
    # plot1 CH4 z vs log10(ODIAC point) — landfills annotated
    fig, ax = plt.subplots(figsize=(7, 5))
    _scatter(ax, df, "odiac_point_tco2", "ch4_z", logx=True,
             annotate_regime="Landfill")
    ax.axhline(CH4_FIRE_Z, color="crimson", ls="--", lw=1,
               label=f"CH4 z = {CH4_FIRE_Z}")
    ax.set_xlabel("log10(ODIAC point sample, annualised t CO2 / cell)")
    ax.set_ylabel("CH4 anomaly z")
    ax.set_title("Plot 1 — CH4 anomaly z vs ODIAC (activity), by regime")
    fig.tight_layout(); fig.savefig(f"{PLOTS}/plot1_ch4z_vs_odiac.png", dpi=130)
    plt.close(fig)

    # plot2 VIIRS vs log10(ODIAC point)
    fig, ax = plt.subplots(figsize=(7, 5))
    _scatter(ax, df, "odiac_point_tco2", "viirs_site", logx=True)
    ax.set_xlabel("log10(ODIAC point sample, annualised t CO2 / cell)")
    ax.set_ylabel("VIIRS nighttime lights (raw)")
    ax.set_title("Plot 2 — VIIRS vs ODIAC (both industrial-activity signals)")
    fig.tight_layout(); fig.savefig(f"{PLOTS}/plot2_viirs_vs_odiac.png", dpi=130)
    plt.close(fig)

    # plot3 ODIAC point vs AOI-mean (sampling robustness)
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    for reg in REGIME_ORDER:
        sub = df[df["regime"] == reg]
        x = sub["odiac_aoi_mean_tco2"].clip(lower=1e-3)
        y = sub["odiac_point_tco2"].clip(lower=1e-3)
        ax.scatter(x, y, label=reg, color=REGIME_COLOR[reg], s=70,
                   edgecolor="k", linewidth=0.4, alpha=0.85, zorder=3)
    lim = [1e-2, max(df["odiac_point_tco2"].max(), df["odiac_aoi_mean_tco2"].max()) * 2]
    ax.plot(lim, lim, "k--", lw=1, alpha=0.6, label="1:1")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("ODIAC AOI-mean (t CO2 / cell)")
    ax.set_ylabel("ODIAC point @ centre (t CO2 / cell)")
    ax.set_title("Plot 3 — ODIAC point vs AOI-mean (sampling robustness)")
    ax.legend(fontsize=7); ax.grid(True, alpha=0.25, which="both")
    fig.tight_layout(); fig.savefig(f"{PLOTS}/plot3_odiac_point_vs_mean.png", dpi=130)
    plt.close(fig)

    # plot4 CH4 z vs VIIRS — the proxy's two axes
    fig, ax = plt.subplots(figsize=(7, 5))
    _scatter(ax, df, "viirs_site", "ch4_z", annotate_regime="Landfill")
    ax.axhline(CH4_FIRE_Z, color="crimson", ls="--", lw=1)
    ax.set_xlabel("VIIRS nighttime lights (raw)")
    ax.set_ylabel("CH4 anomaly z")
    ax.set_title("Plot 4 — CH4 anomaly z vs VIIRS (the two proxy axes)")
    fig.tight_layout(); fig.savefig(f"{PLOTS}/plot4_ch4z_vs_viirs.png", dpi=130)
    plt.close(fig)


def part_b_plots(df: pd.DataFrame):
    db = df.copy()
    have = db["xco2_delta"].notna()
    db = db[have]
    specs = [
        ("viirs_site", "VIIRS nighttime lights (raw)", "plot5_viirs_vs_xco2", "Plot 5 — VIIRS vs XCO2 enhancement"),
        ("ch4_site_ppb", "CH4 raw concentration (ppb)", "plot6_ch4_vs_xco2", "Plot 6 — CH4 raw vs XCO2 enhancement"),
        ("ghg_activity_score", "GHG activity score (CH4+VIIRS combined)", "plot7_combined_vs_xco2", "Plot 7 — combined signal vs XCO2 enhancement"),
    ]
    for xcol, xlab, fname, title in specs:
        fig, ax = plt.subplots(figsize=(7, 5))
        for reg in REGIME_ORDER:
            sub = db[db["regime"] == reg]
            ax.scatter(sub[xcol], sub["xco2_delta"], label=reg,
                       color=REGIME_COLOR[reg], s=70, edgecolor="k",
                       linewidth=0.4, alpha=0.85, zorder=3)
            for _, r in sub.iterrows():
                if pd.notna(r[xcol]) and pd.notna(r["xco2_delta"]):
                    ax.annotate(r["location"], (r[xcol], r["xco2_delta"]),
                                fontsize=6, xytext=(3, 2), textcoords="offset points")
        ax.axhline(0, color="k", lw=0.8, alpha=0.5)
        ax.set_xlabel(xlab)
        ax.set_ylabel("XCO2 AOI − background delta (ppm)")
        ax.set_title(title + f"  (n={len(db)} with delta)")
        ax.legend(fontsize=7); ax.grid(True, alpha=0.25)
        fig.tight_layout(); fig.savefig(f"{PLOTS}/{fname}.png", dpi=130)
        plt.close(fig)


def _corr(x, y):
    m = pd.notna(x) & pd.notna(y)
    x, y = np.asarray(x)[m], np.asarray(y)[m]
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return (None, None, len(x))
    pr = stats.pearsonr(x, y)[0]
    sr = stats.spearmanr(x, y)[0]
    return (round(float(pr), 2), round(float(sr), 2), len(x))


def corr_tables(df: pd.DataFrame) -> str:
    df = df.copy()
    df["log_odiac"] = np.log10(df["odiac_point_tco2"].clip(lower=1e-3))
    lines = []

    def block(title, pairs):
        lines.append(f"\n### {title}\n")
        lines.append("| regime | " + " | ".join(
            f"{a} Pearson | {a} Spearman | n" for a, _, _ in pairs) + " |")
        lines.append("|" + "---|" * (1 + 3 * len(pairs)))
        for reg in REGIME_ORDER + ["ALL"]:
            sub = df if reg == "ALL" else df[df["regime"] == reg]
            cells = [reg]
            for _, xc, yc in pairs:
                pr, sr, n = _corr(sub[xc], sub[yc])
                cells += [str(pr), str(sr), str(n)]
            lines.append("| " + " | ".join(cells) + " |")

    block("Part A — activity (vs ODIAC point, log10)", [
        ("CH4–ODIAC", "ch4_z", "log_odiac"),
        ("VIIRS–ODIAC", "viirs_site", "log_odiac"),
    ])
    block("Part B — concentration (vs XCO2 delta)", [
        ("VIIRS–XCO2", "viirs_site", "xco2_delta"),
        ("CH4–XCO2", "ch4_site_ppb", "xco2_delta"),
    ])
    return "\n".join(lines)


def divergence(df: pd.DataFrame) -> str:
    out = ["\n### Divergence cases (CH4 anomaly z firing, threshold z>1.5)\n"]
    for reg in REGIME_ORDER:
        sub = df[df["regime"] == reg]
        fired = sub[sub["ch4_z"] > CH4_FIRE_Z]["location"].tolist()
        notf = sub[sub["ch4_z"] <= CH4_FIRE_Z]["location"].tolist()
        out.append(f"- **{reg}** — fired: {fired or '(none)'}; did not fire: {notf or '(none)'}")
    # XCO2 coverage summary
    out.append("\n### XCO2 coverage (Part B)\n")
    for reg in REGIME_ORDER:
        sub = df[df["regime"] == reg]
        cov = sub[sub["xco2_delta"].notna()]["location"].tolist()
        out.append(f"- **{reg}** — usable XCO2 delta: {cov or '(none)'}")
    return "\n".join(out)


def main():
    os.makedirs(PLOTS, exist_ok=True)
    df = load()
    part_a_plots(df)
    part_b_plots(df)
    tables = corr_tables(df)
    div = divergence(df)
    with open(CORR_TABLES_MD, "w") as f:
        f.write("# Correlation tables & divergence cases\n")
        f.write(tables + "\n" + div + "\n")
    print(tables)
    print(div)
    print("\nSaved 7 plots to", PLOTS)


if __name__ == "__main__":
    main()
