"""M-DIAG-A1 — read the 5 instrumented diagnostic seeds and emit the tables
the report §4.1 / §4.2 / §6 need.

Pure-Python analysis script — no EE. Reads
``demo/saved_analyses/diagnostic/*.json``, walks every
``_provenance.<id>.extra._diag_bg_std`` block, and writes markdown tables
to stdout plus a JSON summary to ``demo/saved_analyses/diagnostic/_summary.json``
so the report can either link to the rendered tables or quote raw numbers.

Sections produced:

  §4.1  bg_std behaviour characterisation per (seed × indicator)
        Columns: bg_std, bg_median, cv=bg_std/|bg_median|, ring spread,
        plume_contam ratios.

  §4.2  Aggregate vs per-day comparison
        Columns: z_aggregate, hf, n_anomaly_days, per-day-z {min,med,max},
        % days at z >= {1.5, 2.0, 2.5}, direction of disagreement.

  §6    Cross-pillar summary
        One row per (pillar × indicator) collapsing the 5-seed pattern
        into "where does bg_std collapse / inflate / contaminate".

Reverted at Step F (DG6) — kept in tree as a Q-DG-1 audit artefact, but
loses its data source once the instrumentation is removed.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from statistics import median
from typing import Any

_DIAG_DIR: Path = (
    Path(__file__).resolve().parents[1] / "demo" / "saved_analyses" / "diagnostic"
)
_SEED_ORDER: tuple[str, ...] = ("sapezal", "brasilia", "suape", "comodoro", "norilsk")


# Indicators we know go through six_step (i.e. should carry _diag_bg_std).
# Sorted by pillar then ID so the cross-pillar table reads pillar-first.
_AIR_IDS: tuple[str, ...] = (
    "air.no2", "air.so2", "air.co", "air.hcho", "air.o3",
    "air.aai", "air.aod", "air.pm25", "air.pm10",
)
_GHG_IDS: tuple[str, ...] = ("ghg.ch4", "ghg.viirs")
_NATURE_IDS: tuple[str, ...] = ("nature.ndvi",)
_INDICATOR_ORDER: tuple[str, ...] = _AIR_IDS + _GHG_IDS + _NATURE_IDS


def _fmt(value: Any, fmt: str = "{:.3g}") -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        try:
            return fmt.format(value)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _load_seed(name: str) -> dict | None:
    path = _DIAG_DIR / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _diag_for(payload: dict, indicator_id: str) -> dict | None:
    prov = payload.get(f"_provenance.{indicator_id}")
    if not isinstance(prov, dict):
        return None
    extra = prov.get("extra") or {}
    return extra.get("_diag_bg_std")


def _per_day_z_stats(diag: dict) -> dict:
    bg_median = diag.get("bg_median")
    bg_std = diag.get("bg_std")
    per_day = diag.get("per_day_site_means") or {}
    if bg_std in (None, 0) or bg_median is None or not per_day:
        return {
            "n": 0, "min": None, "med": None, "max": None,
            "pct_ge_1_5": None, "pct_ge_2_0": None, "pct_ge_2_5": None,
        }
    zs = [
        (v - bg_median) / bg_std
        for v in per_day.values()
        if isinstance(v, (int, float))
    ]
    if not zs:
        return {
            "n": 0, "min": None, "med": None, "max": None,
            "pct_ge_1_5": None, "pct_ge_2_0": None, "pct_ge_2_5": None,
        }
    n = len(zs)
    return {
        "n": n,
        "min": min(zs),
        "med": median(zs),
        "max": max(zs),
        "pct_ge_1_5": 100.0 * sum(1 for z in zs if z >= 1.5) / n,
        "pct_ge_2_0": 100.0 * sum(1 for z in zs if z >= 2.0) / n,
        "pct_ge_2_5": 100.0 * sum(1 for z in zs if z >= 2.5) / n,
    }


def _n_anomaly_days(payload: dict, indicator_id: str) -> int | None:
    prov = payload.get(f"_provenance.{indicator_id}") or {}
    extra = prov.get("extra") or {}
    n = extra.get("wind_n_anomaly_days")
    if n is None:
        return None
    try:
        return int(n)
    except (TypeError, ValueError):
        return None


def _hf(payload: dict, indicator_id: str) -> float | None:
    v = payload.get(f"{indicator_id}.hf")
    return v if isinstance(v, (int, float)) else None


def _classify_disagreement(z_agg: float | None, hf: float | None) -> str:
    """One-shot classifier for §4.2's 'direction of disagreement' column."""
    if z_agg is None or hf is None:
        return "n/a"
    z_strong = z_agg >= 2.0
    z_weak   = abs(z_agg) < 1.0
    hf_high  = hf >= 0.5
    hf_zero  = hf == 0.0
    if z_strong and hf_zero:
        return "aggr-strong, per-day-silent"  # Norilsk NO2
    if z_weak and hf_high:
        return "aggr-quiet, per-day-saturated"  # AAI artefact
    if z_strong and hf_high:
        return "agree (strong)"
    if z_weak and hf_zero:
        return "agree (quiet)"
    return "partial"


def main() -> None:
    print("=" * 78)
    print("M-DIAG-A1 — bg_std diagnostic analysis")
    print("=" * 78)

    seeds: OrderedDict[str, dict] = OrderedDict()
    for name in _SEED_ORDER:
        seed = _load_seed(name)
        if seed is None:
            print(f"WARN: seed {name!r} not found in {_DIAG_DIR}; skipping")
            continue
        seeds[name] = seed["payload"]

    if not seeds:
        print("No diagnostic seeds found. Run tools/m_diag_a1_rerun_seeds.py first.")
        return

    # --------------------------------------------------------------
    # §4.1 — bg_std characterisation
    # --------------------------------------------------------------
    print()
    print("## §4.1 — bg_std behaviour characterisation")
    print()
    print(
        "| seed | indicator | site | bg_median | bg_std | cv=σ/|μ| | "
        "ring_p10..p90 | ring_max | ring_p90/site_p90 | ring_max/site_p90 |"
    )
    print(
        "|---|---|---|---|---|---|---|---|---|---|"
    )

    summary: list[dict] = []
    for seed_name, payload in seeds.items():
        for ind in _INDICATOR_ORDER:
            diag = _diag_for(payload, ind)
            if diag is None:
                continue
            bg_median = diag.get("bg_median")
            bg_std = diag.get("bg_std")
            ring = diag.get("ring") or {}
            site_buf = diag.get("site_buf") or {}
            plume = diag.get("plume_contam") or {}
            cv = None
            if (
                isinstance(bg_std, (int, float))
                and isinstance(bg_median, (int, float))
                and bg_median != 0
            ):
                cv = bg_std / abs(bg_median)
            ring_spread = (
                f"{_fmt(ring.get('p10'))}…{_fmt(ring.get('p90'))}"
                if ring else "—"
            )
            site_value = payload.get(f"{ind}.site")
            print(
                f"| {seed_name} | {ind} | {_fmt(site_value)} | "
                f"{_fmt(bg_median)} | {_fmt(bg_std)} | {_fmt(cv)} | "
                f"{ring_spread} | {_fmt(ring.get('max'))} | "
                f"{_fmt(plume.get('ring_p90_over_site_p90'))} | "
                f"{_fmt(plume.get('ring_max_over_site_p90'))} |"
            )
            summary.append({
                "seed": seed_name,
                "indicator": ind,
                "section": "4.1",
                "site": site_value,
                "bg_median": bg_median,
                "bg_std": bg_std,
                "cv": cv,
                "ring": ring,
                "site_buf": site_buf,
                "plume_contam": plume,
            })

    # --------------------------------------------------------------
    # §4.2 — aggregate vs per-day
    # --------------------------------------------------------------
    print()
    print("## §4.2 — Aggregate z vs per-day HF comparison")
    print()
    print(
        "| seed | indicator | z_aggr | hf | n_anom_days | per-day-z min | "
        "med | max | % ≥1.5 | % ≥2.0 | % ≥2.5 | disagreement |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")

    for seed_name, payload in seeds.items():
        for ind in _INDICATOR_ORDER:
            diag = _diag_for(payload, ind)
            if diag is None:
                continue
            z_agg = diag.get("z_aggregate")
            hf = _hf(payload, ind)
            n_anom = _n_anomaly_days(payload, ind)
            stats = _per_day_z_stats(diag)
            disagreement = _classify_disagreement(z_agg, hf)
            print(
                f"| {seed_name} | {ind} | {_fmt(z_agg)} | {_fmt(hf, '{:.3f}')} | "
                f"{n_anom if n_anom is not None else '—'} | "
                f"{_fmt(stats['min'], '{:.2f}')} | "
                f"{_fmt(stats['med'], '{:.2f}')} | "
                f"{_fmt(stats['max'], '{:.2f}')} | "
                f"{_fmt(stats['pct_ge_1_5'], '{:.0f}')} | "
                f"{_fmt(stats['pct_ge_2_0'], '{:.0f}')} | "
                f"{_fmt(stats['pct_ge_2_5'], '{:.0f}')} | "
                f"{disagreement} |"
            )
            summary.append({
                "seed": seed_name,
                "indicator": ind,
                "section": "4.2",
                "z_aggregate": z_agg,
                "hf": hf,
                "n_anomaly_days": n_anom,
                "per_day_z_stats": stats,
                "disagreement_class": disagreement,
            })

    # --------------------------------------------------------------
    # §6 — cross-pillar pattern roll-up
    # --------------------------------------------------------------
    print()
    print("## §6 — Cross-pillar pattern (per indicator, across 5 seeds)")
    print()
    print(
        "| indicator | bg_std range | hf range | most common disagreement | "
        "seeds where plume contaminated (ring_p90 ≥ site_p90) |"
    )
    print("|---|---|---|---|---|")
    for ind in _INDICATOR_ORDER:
        bg_std_vals: list[float] = []
        hf_vals: list[float] = []
        disagreements: list[str] = []
        contaminated_seeds: list[str] = []
        for seed_name, payload in seeds.items():
            diag = _diag_for(payload, ind)
            if diag is None:
                continue
            bg = diag.get("bg_std")
            if isinstance(bg, (int, float)):
                bg_std_vals.append(bg)
            hf = _hf(payload, ind)
            if isinstance(hf, (int, float)):
                hf_vals.append(hf)
            z_agg = diag.get("z_aggregate")
            disagreements.append(_classify_disagreement(z_agg, hf))
            plume = diag.get("plume_contam") or {}
            ratio = plume.get("ring_p90_over_site_p90")
            if isinstance(ratio, (int, float)) and ratio >= 1.0:
                contaminated_seeds.append(seed_name)
        if not bg_std_vals and not hf_vals:
            print(f"| {ind} | (no data) | — | — | — |")
            continue
        bg_range = (
            f"{min(bg_std_vals):.3g}…{max(bg_std_vals):.3g}"
            if bg_std_vals else "—"
        )
        hf_range = (
            f"{min(hf_vals):.2f}…{max(hf_vals):.2f}" if hf_vals else "—"
        )
        # Mode of disagreements
        if disagreements:
            counts: dict[str, int] = {}
            for d in disagreements:
                counts[d] = counts.get(d, 0) + 1
            mode = max(counts.items(), key=lambda kv: kv[1])[0]
            mode_str = f"{mode} ({counts[mode]}/{len(disagreements)})"
        else:
            mode_str = "—"
        contam_str = ", ".join(contaminated_seeds) if contaminated_seeds else "none"
        print(f"| {ind} | {bg_range} | {hf_range} | {mode_str} | {contam_str} |")

    # --------------------------------------------------------------
    # Write summary JSON
    # --------------------------------------------------------------
    summary_path = _DIAG_DIR / "_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print()
    print(f"Wrote summary JSON: {summary_path}")


if __name__ == "__main__":
    main()
