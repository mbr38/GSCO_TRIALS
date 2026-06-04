"""
Report §7.11 validation figures (Figures 7.11a / 7.11b / 7.11c).

Renders the three validation "key figures" in the GSCO report house style:
Arial, muted pillar palettes (Air slate-blue, GHG teal). Reads the committed
per-location / per-event validation tables in analysis/ — no engine or EE calls.

Outputs:
  analysis/report_fig_7_11a_aod_pm25.png   — AOD vs surface PM2.5, by regime
  analysis/report_fig_7_11b_aai_bgstd.png  — AAI per-day z vs bg_std (denominator collapse)
  analysis/report_fig_7_11c_ghg_odiac.png  — VIIRS & CH4-z vs ODIAC
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr

# ---- house style -----------------------------------------------------------
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

AIR_FILL, AIR_LINE = "#cdd9e6", "#3f5f86"      # Air slate-blue
GHG_FILL, GHG_LINE = "#cfe0df", "#3f7370"      # GHG teal
NAT_LINE = "#3f7340"                            # Nature green (accent only)
MUTED_CLAY = "#b07a5a"                          # muted contrast for "miss/false-positive"
GREY = "#9aa0a6"

HERE = "analysis"


def _finish(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------------------
# 7.11a — AOD vs PM2.5 window means, by regime
# ---------------------------------------------------------------------------
def fig_a():
    import json
    df = pd.read_csv(f"{HERE}/aod_pm25_validation.csv")
    # post-fix engine anomaly z (M-DIAG-A4 temporal denominator), by location
    reval = {r["location"]: r for r in json.load(
        open(f"{HERE}/aod_postfix_revalidation.json"))}
    df["post_z"] = df["location"].map(lambda l: reval.get(l, {}).get("post_z"))

    # Air-pillar palette: regimes shaded from light to dark slate; clean in grey.
    regime_color = {
        "clean":      GREY,
        "biomass":    "#9db4cd",
        "dust":       "#6f8bad",
        "coal":       "#52749c",
        "industrial": AIR_LINE,
    }
    order = ["clean", "biomass", "dust", "coal", "industrial"]
    rho, _ = spearmanr(df["aod_mean_scaled"], df["pm25_mean_ugm3"])
    GATE = 0.30   # illustrative absolute-AOD gate

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.8, 5.0))

    # --- left: raw column AOD vs surface PM2.5 (the benchmark), + gate caution
    for reg in order:
        sub = df[df["regime"] == reg]
        ax1.scatter(sub["aod_mean_scaled"], sub["pm25_mean_ugm3"],
                    s=56, c=regime_color[reg], edgecolor="#33414f",
                    linewidth=0.6, alpha=0.92, label=reg.capitalize(), zorder=3)
    ax1.set_ylim(-3, 86)
    ax1.set_xlim(0.03, 0.82)
    ax1.axvline(GATE, color="#b23b3b", linestyle="--", linewidth=1.0, zorder=2)
    ax1.text(GATE + 0.012, 80, f"raw-AOD gate ≈ {GATE}", color="#b23b3b",
             fontsize=8, va="center", ha="left")
    # annotate the failure the gate would make — text in the empty upper-mid band
    kat = df[df["location"].str.startswith("Katowice")]
    if len(kat):
        x, y = float(kat["aod_mean_scaled"].iloc[0]), float(kat["pm25_mean_ugm3"].iloc[0])
        ax1.annotate("Katowice — high surface PM$_{2.5}$,\nthin column (a raw gate misses it)",
                     (x, y), xytext=(0.23, 62), fontsize=7.5, color="#8a5638",
                     va="center", arrowprops=dict(arrowstyle="->", color="#8a5638", lw=0.8))
    ax1.set_xlabel("Raw column AOD (MODIS MAIAC, window mean)")
    ax1.set_ylabel("Surface PM$_{2.5}$ (OpenAQ, µg/m³, window mean)")
    ax1.set_title("Raw AOD vs surface PM$_{2.5}$", fontsize=9.5, loc="left",
                  color=AIR_LINE)
    ax1.legend(frameon=False, fontsize=8, loc="lower right", handletextpad=0.3,
               labelspacing=0.3)
    ax1.text(0.04, 0.96, f"Spearman ρ = {rho:.2f}", transform=ax1.transAxes,
             fontsize=9.5, color="#33414f", va="top", fontweight="bold")
    ax1.text(0.04, 0.905, "(clean-vs-polluted contrast)", transform=ax1.transAxes,
             fontsize=7.5, color="#5f6b78", va="top")
    _finish(ax1)

    # --- right: engine anomaly severity (post-fix z) vs raw AOD = orthogonal
    for reg in order:
        sub = df[df["regime"] == reg].dropna(subset=["post_z"])
        ax2.scatter(sub["aod_mean_scaled"], sub["post_z"], s=56,
                    c=regime_color[reg], edgecolor="#33414f", linewidth=0.6,
                    alpha=0.92, zorder=3)
    ax2.set_ylim(-1.15, 1.15)
    ax2.set_xlim(0.03, 0.82)
    ax2.axhline(1.0, color="#b23b3b", linestyle="--", linewidth=1.0)
    ax2.axhline(-1.0, color="#b23b3b", linestyle="--", linewidth=1.0)
    ax2.text(0.80, 1.02, "|z| = 1.0 Concern band", color="#b23b3b",
             fontsize=8, va="bottom", ha="right")
    ax2.axhline(0, color="#cccccc", linewidth=0.7, zorder=1)
    ax2.set_xlabel("Raw column AOD (MODIS MAIAC, window mean)")
    ax2.set_ylabel("Engine anomaly z (post-fix, what is scored)")
    ax2.set_title("Engine severity vs raw AOD", fontsize=9.5, loc="left",
                  color="#8a5638")
    ax2.text(0.05, 0.42, "orthogonal to absolute haze —", transform=ax2.transAxes,
             fontsize=8, color="#5f6b78", va="top")
    ax2.text(0.05, 0.365, "haziest sites sit at z ≈ 0 → Normal\n(post-fix: 0/23 reach Concern)",
             transform=ax2.transAxes, fontsize=7.5, color="#5f6b78", va="top")
    _finish(ax2)

    fig.suptitle("Figure 7.11a  AOD: raw column signal (tracks PM$_{2.5}$ cross-site) vs the scored anomaly (blind to it)",
                 fontsize=10.5, color="#222222", x=0.012, ha="left", y=1.01)
    fig.tight_layout()
    out = f"{HERE}/report_fig_7_11a_aod_pm25.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print("wrote", out, "| rho=", round(rho, 3))


# ---------------------------------------------------------------------------
# 7.11b — what the engine scores (anomaly z, inert) vs the absolute column
#         signal (separates fires). Post-fix engine z + raw-AAI gate.
# ---------------------------------------------------------------------------
def fig_b():
    import json
    summ = pd.read_csv(f"{HERE}/aai_firms_event_summary.csv")
    summ["raw"] = summ["peak_aai_in_peak"].fillna(summ["peak_aai"])
    reval = {r["id"]: r for r in json.load(
        open(f"{HERE}/aai_firms_revalidation_postfix.json"))}
    summ["post_z"] = summ["id"].map(lambda i: reval.get(i, {}).get("post_z"))

    cats = [("fire", "Fires", AIR_LINE, "#27384b"),
            ("dust", "Dust", "#8fa6c0", "#4a627d"),
            ("control", "Controls", MUTED_CLAY, "#6e4630")]
    # deterministic horizontal spread within each category
    def xs(n, base):
        if n == 1:
            return [base]
        return [base - 0.18 + 0.36 * k / (n - 1) for k in range(n)]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.4, 4.5))

    for ax, col, thr, thr_lbl in (
        (ax1, "post_z", 2.0, "z = 2.0 hot threshold"),
        (ax2, "raw", 1.5, "raw-AAI gate ≈ 1.5"),
    ):
        for i, (kind, lbl, fill, edge) in enumerate(cats):
            sub = summ[summ["kind"] == kind].dropna(subset=[col])
            vals = list(sub[col])
            for x, y in zip(xs(len(vals), i), vals):
                ax.scatter(x, y, s=64, c=fill, edgecolor=edge, linewidth=0.7,
                           zorder=3)
        ax.axhline(thr, color="#b23b3b", linestyle="--", linewidth=1.0, zorder=2)
        ax.text(2.32, thr, thr_lbl, color="#b23b3b", fontsize=8,
                va="bottom", ha="right")
        ax.set_xticks(range(len(cats)))
        ax.set_xticklabels([c[1] for c in cats])
        ax.set_xlim(-0.5, 2.5)
        ax.axhline(0, color="#cccccc", linewidth=0.7, zorder=1)
        _finish(ax)

    ax1.set_ylabel("Engine anomaly z (post-fix, what is scored)")
    ax1.set_title("Anomaly z — site vs surrounding ring", fontsize=9.5,
                  loc="left", color=AIR_LINE)
    ax1.text(0.03, 0.80, "inert: nothing reaches 2.0;\nregional events go negative",
             transform=ax1.transAxes, fontsize=8, color="#5f6b78", va="top")

    ax2.set_ylabel("Absolute column AAI (peak in window)")
    ax2.set_title("Absolute AAI — column signal", fontsize=9.5,
                  loc="left", color="#8a5638")
    ax2.text(0.34, 0.93, "fires separate cleanly (4/5 above gate);\ncontrols 0/5, dust 1/5",
             transform=ax2.transAxes, fontsize=8, color="#5f6b78", va="top")

    fig.suptitle("Figure 7.11b  AAI as an event detector: local anomaly (scored) vs absolute column signal",
                 fontsize=10.5, color="#222222", x=0.012, ha="left", y=1.01)
    fig.tight_layout()
    out = f"{HERE}/report_fig_7_11b_aai_axes.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print("wrote", out)


# ---------------------------------------------------------------------------
# 7.11c — VIIRS & CH4-z vs ODIAC (two panels)
# ---------------------------------------------------------------------------
def fig_c():
    df = pd.read_csv(f"{HERE}/ghg_odiac_validation.csv")
    # Faithful to the report: Spearman is computed on all sites incl. the rural
    # ODIAC=0 cases (VIIRS n=25 -> rho 0.70; CH4 n=23 -> rho -0.01). On the log
    # axis the rural ODIAC=0 sites are placed at a left-hand floor strip.
    pos = df[df["odiac_point_tco2"] > 0]
    floor = np.log10(pos["odiac_point_tco2"].min()) - 1.0
    df = df.copy()
    df["log_odiac"] = np.where(df["odiac_point_tco2"] > 0,
                               np.log10(df["odiac_point_tco2"].clip(lower=1e-9)),
                               floor)

    viirs = df.dropna(subset=["viirs_site"])
    ch4 = df.dropna(subset=["ch4_z"])
    rho_v, _ = spearmanr(viirs["odiac_point_tco2"], viirs["viirs_site"])
    rho_c, _ = spearmanr(ch4["odiac_point_tco2"], ch4["ch4_z"])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 4.4))

    for ax in (ax1, ax2):
        ax.axvspan(floor - 0.45, floor + 0.45, color="#f2f2f0", zorder=0)
        ax.text(floor, ax.get_ylim()[0], "ODIAC = 0\n(rural)", fontsize=7,
                color="#9aa0a6", ha="center", va="bottom")

    ax1.scatter(viirs["log_odiac"], viirs["viirs_site"], s=58, c=GHG_FILL,
                edgecolor=GHG_LINE, linewidth=0.9, zorder=3)
    ax1.set_xlabel("log$_{10}$ ODIAC fossil-CO$_2$ (t/cell, point sample)")
    ax1.set_ylabel("VIIRS nightlight radiance (site)")
    ax1.set_title("VIIRS activity proxy", fontsize=10, loc="left", color=GHG_LINE)
    ax1.text(0.40, 0.72, f"Spearman ρ = {rho_v:.2f}",
             transform=ax1.transAxes, fontsize=9.5, color=GHG_LINE,
             va="top", fontweight="bold")
    ax1.text(0.40, 0.655, "tracks the inventory (n = 25)", transform=ax1.transAxes,
             fontsize=8, color="#5f6b78", va="top")
    _finish(ax1)

    ax2.scatter(ch4["log_odiac"], ch4["ch4_z"], s=58, c="#e4e9e3",
                edgecolor=MUTED_CLAY, linewidth=0.9, zorder=3)
    ax2.axhline(1.5, color="#b23b3b", linestyle="--", linewidth=1.0)
    ax2.text(0.97, 0.945, "z = 1.5 firing bar", color="#b23b3b", transform=ax2.transAxes,
             fontsize=8, va="bottom", ha="right")
    ax2.set_xlabel("log$_{10}$ ODIAC fossil-CO$_2$ (t/cell, point sample)")
    ax2.set_ylabel("CH$_4$ anomaly z-score (site)")
    ax2.set_title("CH$_4$ anomaly proxy", fontsize=10, loc="left", color=MUTED_CLAY)
    ax2.text(0.27, 0.30, f"Spearman ρ = {rho_c:.2f}",
             transform=ax2.transAxes, fontsize=9.5, color="#8a5638",
             va="top", fontweight="bold")
    ax2.text(0.27, 0.235, "no relationship (n = 23; 1/25 fired)",
             transform=ax2.transAxes, fontsize=8, color="#5f6b78", va="top")
    _finish(ax2)

    fig.suptitle("Figure 7.11c  GHG activity proxies vs the ODIAC fossil-CO$_2$ inventory (n = 25 / 23)",
                 fontsize=10.5, color="#222222", x=0.012, ha="left", y=1.01)
    fig.tight_layout()
    out = f"{HERE}/report_fig_7_11c_ghg_odiac.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print("wrote", out, "| viirs_rho=", round(rho_v, 3), "ch4_rho=", round(rho_c, 3))


if __name__ == "__main__":
    fig_a()
    fig_b()
    fig_c()
