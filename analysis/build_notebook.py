"""Assemble analysis/ghg_odiac_validation.ipynb from nbformat cells.

The notebook is the Steps D + F analysis surface: it loads the CSV produced by
extract_part_a.py + extract_part_b.py, renders the data table, regenerates the
7 plots (also saved as PNGs for the markdown/docx report), and prints the
per-regime correlation tables and divergence cases. Reuses the functions in
analysis_plots.py so the notebook figures are byte-identical to the report's.

Build:   python analysis/build_notebook.py
Execute: jupyter nbconvert --to notebook --execute --inplace analysis/ghg_odiac_validation.ipynb
"""
import nbformat as nbf
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell

nb = new_notebook()
cells = []

cells.append(new_markdown_cell(
    "# GHG ↔ ODIAC + OCO-2/OCO-3 validation — analysis notebook\n\n"
    "Steps D + F of the validation brief. **Activity validation** (Part A) "
    "compares the GHG pillar's raw inputs (CH₄ anomaly z, CH₄ raw "
    "concentration, VIIRS) against ODIAC fossil-CO₂ emissions; **concentration "
    "validation** (Part B) compares them against OCO-2/OCO-3 XCO₂ atmospheric "
    "retrievals.\n\n"
    "Run `analysis/extract_part_a.py` and `analysis/extract_part_b.py` first to "
    "build `analysis/ghg_odiac_validation.csv`. ODIAC is sampled via Earth "
    "Engine; OCO XCO₂ is **not** in EE and is sourced via `earthaccess` from "
    "NASA GES DISC. N=25, operator-picked — findings are illustrative, not "
    "statistically conclusive. See `docs/ghg_odiac_validation.md`."
))

cells.append(new_code_cell(
    "import sys, os\n"
    "sys.path.insert(0, os.path.abspath('..'))\n"
    "%matplotlib inline\n"
    "import pandas as pd\n"
    "from IPython.display import Image, display\n"
    "from analysis import analysis_plots as ap\n"
    "df = ap.load()\n"
    "pd.set_option('display.width', 200); pd.set_option('display.max_columns', 40)\n"
    "df"
))

cells.append(new_markdown_cell(
    "## Part A — activity validation (vs ODIAC)\n\n"
    "ODIAC uses its 2023 vintage; CH₄/VIIRS use the 2025-06→2025-12 window "
    "(temporal-aggregation mismatch — see report §7). Plots saved to "
    "`analysis/plots/`."
))
cells.append(new_code_cell(
    "ap.part_a_plots(df)\n"
    "for p in ['plot1_ch4z_vs_odiac','plot2_viirs_vs_odiac',\n"
    "          'plot3_odiac_point_vs_mean','plot4_ch4z_vs_viirs']:\n"
    "    display(Image(filename=f'plots/{p}.png'))"
))
cells.append(new_code_cell(
    "print(ap.corr_tables(df))\n"
    "print(ap.divergence(df))"
))

cells.append(new_markdown_cell(
    "## Part B — concentration validation (vs OCO XCO₂)\n\n"
    "XCO₂ delta = AOI-box (±0.25° ≈ 25 km) mean − local-background (0.25°–1.0° "
    "annulus) mean, pooled over the window from good-quality OCO-2 + OCO-3 "
    "soundings. Sparse-coverage locations (no delta) are excluded from the "
    "scatters; coverage varies by regime — rural/landfill are sparsest."
))
cells.append(new_code_cell(
    "ap.part_b_plots(df)\n"
    "for p in ['plot5_viirs_vs_xco2','plot6_ch4_vs_xco2','plot7_combined_vs_xco2']:\n"
    "    display(Image(filename=f'plots/{p}.png'))"
))
cells.append(new_code_cell(
    "cov = df[['regime','location','xco2_count','xco2_n_oco2','xco2_n_oco3',\n"
    "          'xco2_bg_count','xco2_delta','partB_flags']]\n"
    "cov"
))

cells.append(new_markdown_cell(
    "## Caveats\n\n"
    "- **N=25, operator-picked** — illustrative, not statistically conclusive.\n"
    "- **ODIAC is monthly bottom-up inventory** (2020–2023), not observation; "
    "the GHG pillar is window-based and current — a temporal-aggregation "
    "mismatch.\n"
    "- **OCO coverage varies by location** — sparse-evidence findings are "
    "weaker; rural/landfill regimes have fewer retrievals than urban/point "
    "sources.\n"
    "- **Atmospheric transport decouples local sources from local "
    "concentration peaks** — the wind-attributability story applies to XCO₂ "
    "as it did to air quality (M-WIND-A1).\n"
    "- **ODIAC and OCO measure different things** (emissions allocation vs "
    "column concentration) — two complementary benchmarks, each one form of "
    "evidence."
))

nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}
with open("analysis/ghg_odiac_validation.ipynb", "w") as f:
    nbf.write(nb, f)
print("Wrote analysis/ghg_odiac_validation.ipynb with", len(cells), "cells")
