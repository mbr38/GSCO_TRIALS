"""Render the two Section 7 inline figures (read-only, from the sweep CSV).

matplotlib → PNG @ 300 dpi, restrained report style. No titles (captions in the
docx serve that role).

    python tools/report_figures.py
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[1]
SUMMARY_CSV = REPO / "tools" / "report_example_sweep.csv"
FIG_A = REPO / "tools" / "fig_7a_ghg_slope.png"
FIG_A2 = REPO / "tools" / "fig_7a2_ghg_activity.png"
FIG_CORE = REPO / "tools" / "fig_7a2_ghg_core.png"
FIG_B = REPO / "tools" / "fig_7b_pillar_signatures.png"

# GHG core weights — CORE_GHG_AUDIT_SUPPORT_WEIGHTS (engine/constants.py:330).
W_COMBUSTION = 0.60
W_ACTIVITY = 0.40

# Site archetype labels (shown in brackets under each location name).
SITE_TYPE = {
    "Jamnagar": "refinery",
    "Comodoro": "oil & gas field",
    "Norilsk": "smelter",
    "Morowali": "nickel smelter",
    "Escondida": "copper mine",
    "Carajás": "iron ore mine",
}

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 9,
    "axes.edgecolor": "#555555",
    "axes.linewidth": 0.8,
    "text.color": "#222222",
    "axes.labelcolor": "#222222",
    "ytick.color": "#555555",
    "xtick.color": "#555555",
})

DIVERGENT = "#2f6f9f"   # muted blue — informative divergence
CONVERGENT = "#b0b0b0"  # muted grey — grammars agree


def _load() -> dict[str, dict]:
    with SUMMARY_CSV.open(encoding="utf-8") as fh:
        return {r["site"]: r for r in csv.DictReader(fh)}


def _sk(S: dict, needle: str) -> str:
    return next(k for k in S if needle.lower() in k.lower())


# ---------------------------------------------------------------------------
# Figure 7.A — GHG grammar slope chart
# ---------------------------------------------------------------------------

def make_fig_a() -> None:
    S = _load()
    order = ["Jamnagar", "Comodoro", "Norilsk", "Morowali", "Escondida", "Carajás"]
    convergent = {"Escondida", "Carajás"}

    rows = []
    for needle in order:
        r = S[_sk(S, needle)]
        rows.append((needle,
                     float(r["ghg_combustion_proxy"]),
                     float(r["ghg_viirs_flaring_score"])))
    # Top-to-bottom by descending (VIIRS − combustion) divergence gap.
    rows.sort(key=lambda t: -(t[2] - t[1]))

    comb_col = "#a9c4dd"   # consistent lighter shade for combustion
    div_col = DIVERGENT    # primary — divergent-site VIIRS
    conv_col = CONVERGENT  # muted grey — convergent-site VIIRS

    fig, ax = plt.subplots(figsize=(6.7, 4.5))
    fig.subplots_adjust(left=0.27, right=0.96, top=0.99, bottom=0.20)

    y = np.arange(len(rows))
    h = 0.38
    for i, (name, comb, vii) in enumerate(rows):
        div = name not in convergent
        ax.barh(y[i] - h / 2, comb, height=h, color=comb_col, zorder=3)
        ax.barh(y[i] + h / 2, vii, height=h,
                color=div_col if div else conv_col, zorder=3)
        ax.text(comb + 0.012, y[i] - h / 2, f"{comb:.2f}", va="center",
                ha="left", fontsize=8, color="#333")
        ax.text(vii + 0.012, y[i] + h / 2, f"{vii:.2f}", va="center",
                ha="left", fontsize=8, color="#333")

    ax.set_yticks(y)
    ax.set_yticklabels([f"{t[0]}\n({SITE_TYPE[t[0]]})" for t in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.1)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xlabel("Score (0–1)")
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(left=False)
    ax.xaxis.grid(True, color="#eeeeee", lw=0.6)
    ax.set_axisbelow(True)

    from matplotlib.patches import Patch
    handles = [
        Patch(color=comb_col, label="Combustion proxy (borrowed Air signal)"),
        Patch(color=div_col, label="VIIRS flaring score — divergent site"),
        Patch(color=conv_col, label="VIIRS flaring score — convergent site"),
    ]
    ax.legend(handles=handles, frameon=False, ncol=1, loc="lower right",
              fontsize=8, bbox_to_anchor=(1.0, 0.02))

    fig.savefig(FIG_A, dpi=300)
    plt.close(fig)
    print(f"[fig] wrote {FIG_A}")


# ---------------------------------------------------------------------------
# Figure 7.A companion — resolved GHG activity score per site
# ---------------------------------------------------------------------------

def make_fig_a2() -> None:
    S = _load()
    order = ["Jamnagar", "Comodoro", "Norilsk", "Morowali", "Escondida", "Carajás"]
    rows = []
    for needle in order:
        r = S[_sk(S, needle)]
        rows.append((needle,
                     float(r["ghg_combustion_proxy"]),
                     float(r["ghg_viirs_flaring_score"]),
                     float(r["ghg_activity_score"])))
    # Same top-to-bottom order as Figure 7.A (descending divergence gap).
    rows.sort(key=lambda t: -(t[2] - t[1]))

    fig, ax = plt.subplots(figsize=(6.7, 4.5))
    fig.subplots_adjust(left=0.27, right=0.93, top=0.99, bottom=0.13)

    y = np.arange(len(rows))
    for i, (name, comb, vii, act) in enumerate(rows):
        ax.barh(y[i], act, height=0.6, color=DIVERGENT, zorder=3)
        ax.text(act + 0.012, y[i], f"{act:.2f}", va="center", ha="left",
                fontsize=8.5, color="#333")

    ax.set_yticks(y)
    ax.set_yticklabels([f"{t[0]}\n({SITE_TYPE[t[0]]})" for t in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.1)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xlabel("GHG activity score (0–1)")
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(left=False)
    ax.xaxis.grid(True, color="#eeeeee", lw=0.6)
    ax.set_axisbelow(True)

    fig.savefig(FIG_A2, dpi=300)
    plt.close(fig)
    print(f"[fig] wrote {FIG_A2}")


# ---------------------------------------------------------------------------
# Figure 7.A companion — combined GHG core score (combustion + flaring, no
# confidence/quality yet). core = 0.60·combustion_proxy + 0.40·viirs_flaring.
# ---------------------------------------------------------------------------

def make_fig_core() -> None:
    S = _load()
    needles = ["Jamnagar", "Comodoro", "Norilsk", "Morowali", "Escondida", "Carajás"]
    rows = []
    for needle in needles:
        r = S[_sk(S, needle)]
        comb = float(r["ghg_combustion_proxy"])
        act = float(r["ghg_activity_score"])
        core = W_COMBUSTION * comb + W_ACTIVITY * act
        rows.append((needle, core))
    # Rank by the combined core (descending) — the figure's whole point is the
    # re-ranking: Morowali (high on both grammars) overtakes the pure-flaring sites.
    rows.sort(key=lambda t: -t[1])

    fig, ax = plt.subplots(figsize=(6.7, 4.5))
    fig.subplots_adjust(left=0.27, right=0.93, top=0.99, bottom=0.13)

    y = np.arange(len(rows))
    for i, (name, core) in enumerate(rows):
        ax.barh(y[i], core, height=0.6, color=DIVERGENT, zorder=3)
        ax.text(core + 0.012, y[i], f"{core:.2f}", va="center", ha="left",
                fontsize=8.5, color="#333")

    ax.set_yticks(y)
    ax.set_yticklabels([f"{t[0]}\n({SITE_TYPE[t[0]]})" for t in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.0)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xlabel("GHG core score  (0.60·combustion + 0.40·VIIRS flaring)")
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(left=False)
    ax.xaxis.grid(True, color="#eeeeee", lw=0.6)
    ax.set_axisbelow(True)

    fig.savefig(FIG_CORE, dpi=300)
    plt.close(fig)
    print(f"[fig] wrote {FIG_CORE}")


# ---------------------------------------------------------------------------
# Figure 7.B — pillar signatures grouped bar
# ---------------------------------------------------------------------------

def make_fig_b() -> None:
    S = _load()
    com = S[_sk(S, "Comodoro")]
    car = S[_sk(S, "Carajás")]
    # Three pillar follow-ups + the composite (their equal-weighted mean),
    # shown as a distinct dark bar per site.
    series = ["Air", "GHG", "Nature", "Composite"]
    keys = ["air_followup", "ghg_followup", "nature_followup", "composite_overall"]
    com_v = [float(com[k]) for k in keys]
    car_v = [float(car[k]) for k in keys]
    colors = {"Air": "#6f9bc4", "GHG": "#c79a4b", "Nature": "#6a9a6a",
              "Composite": "#3f4a59"}

    fig, ax = plt.subplots(figsize=(6.4, 4.1))
    fig.subplots_adjust(left=0.11, right=0.97, top=0.88, bottom=0.13)

    x = np.arange(2)
    w = 0.20
    for i, name in enumerate(series):
        vals = [com_v[i], car_v[i]]
        ax.bar(x + (i - 1.5) * w, vals, w, label=name, color=colors[name],
               edgecolor="white", lw=0.6, zorder=3)
        if name == "Composite":  # label the composite bar with its value
            for xi, v in zip(x, vals):
                ax.text(xi + (i - 1.5) * w, v + 0.012, f"{v:.2f}", ha="center",
                        va="bottom", fontsize=8, color=colors["Composite"],
                        fontweight="bold")

    # Composite-confidence dot above each group.
    confs = [float(com["composite_confidence"]), float(car["composite_confidence"])]
    for xi, cf in zip(x, confs):
        ax.plot(xi, cf, marker="o", ms=7, color="#3a3a3a", zorder=5)
        ax.text(xi, cf + 0.02, f"composite confidence {cf:.3f}", ha="center",
                va="bottom", fontsize=8, color="#333")

    ax.set_ylim(0, 0.82)
    ax.set_ylabel("Follow-up priority / composite (0–1)")
    ax.set_xticks(x)
    ax.set_xticklabels(["Comodoro Rivadavia\n(oil & gas)", "Carajás\n(iron ore)"])
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.yaxis.grid(True, color="#eeeeee", lw=0.6)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, ncol=4, loc="upper center",
              bbox_to_anchor=(0.5, 1.12), fontsize=8.5)

    fig.savefig(FIG_B, dpi=300)
    plt.close(fig)
    print(f"[fig] wrote {FIG_B}")


def main() -> None:
    make_fig_a()
    make_fig_b()


if __name__ == "__main__":
    main()
