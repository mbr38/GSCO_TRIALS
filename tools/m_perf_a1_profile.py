"""M-PERF-A1 — Profile getInfo round-trips + capture regression baseline.

Runs ``ScreeningRun`` against the three M-PERF-A1 regression AOIs:

  - Sapezal 5 km (small inland — matches the existing high_priority_amazon save)
  - Distrito Federal 43.1 km (large — matches low_priority_brasilia)
  - Rio coastal 20 km (exercises the M-TIER-A3 land mask)

For each AOI, the script:

  1. Resets the profiling counter.
  2. Executes the full pillar + composite stack with the
     ``engine.core.ee_resilience`` wrapper installed (retry ON + profile ON).
  3. Writes the result payload to ``tests/baselines/m_perf_a1/<aoi>.json``
     — this is the golden fixture the tolerance-based regression harness
     (Step E) checks subsequent batched runs against.
  4. Snapshots the call-site count distribution and stashes it in the
     same fixture for the §4.2 ranking table.

After all three AOIs run, emits a combined Markdown report at
``docs/M-PERF-A1_profiling_report.md`` showing the top getInfo offenders
across AOIs (PF9 — batching decisions ride on the actual measurements,
not the static hypothesis).

The cloudy/sparse AOI from spec PF16 is intentionally omitted from this
run: M-FALLBACK-A1's climatology fallback path is not yet operational,
so the four-corner coverage will be revisited once that milestone lands.

Run from the repo root::

    EE_PROJECT_ID=<your-project> python tools/m_perf_a1_profile.py

Optional flags:
    --aoi sapezal|df|rio   Run only one AOI (the others are skipped).
    --no-retry             Install the wrapper with retries disabled.
                           Use only to reproduce the un-wrapped baseline
                           if you suspect retries are mutating outputs
                           (they should be transparent on success paths).

Cumulative wall time across all three AOIs is ~15-25 minutes — DF
dominates (43.1 km buffer compounds with every per-indicator reducer).
"""

# M-PERF-A1
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

# Repo root on sys.path so engine + ui import when running directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ee

from engine.core.ee_resilience import (
    install_getinfo_wrapper,
    reset_profile,
    set_profiling_enabled,
    snapshot_profile,
)
from engine.orchestrator import ScreeningRun
from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS


# ---------------------------------------------------------------------------
# Regression AOI catalogue (PF16, minus the cloudy/sparse corner)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RegressionAOI:
    aoi_id: str
    name: str
    centre: dict
    radius_km: float
    centre_metadata: dict


# Time range mirrors the seeded saves so baselines stay comparable.
_TIME_RANGE: tuple[str, str] = ("2026-02-22", "2026-05-23")


_AOIS: tuple[RegressionAOI, ...] = (
    RegressionAOI(
        aoi_id="sapezal_5km",
        name="Sapezal 5 km (small inland)",
        centre={"lat": -13.5417, "lon": -58.7642},
        radius_km=5.0,
        centre_metadata={
            "node_id":   "soy_04",
            "node_name": "Sapezal Plantation (demo)",
            "country":   "Brazil",
            "source":    "M-PERF-A1 profiling — small-AOI corner",
        },
    ),
    RegressionAOI(
        aoi_id="distrito_federal_43_1km",
        name="Distrito Federal 43.1 km (large)",
        centre={"lat": -15.7808, "lon": -47.7968},
        radius_km=43.1,
        centre_metadata={
            "country":     "Brazil",
            "region_name": "Distrito Federal",
            "source":      "M-PERF-A1 profiling — large-AOI corner",
        },
    ),
    RegressionAOI(
        aoi_id="rio_coastal_20km",
        name="Rio de Janeiro coastal 20 km (M-TIER-A3 land mask)",
        # Centre is just inland of Guanabara Bay so the buffer pulls a
        # substantial share of ocean into the background ring — exactly
        # what we want to exercise the land-mask path.
        centre={"lat": -22.9068, "lon": -43.1729},
        radius_km=20.0,
        centre_metadata={
            "country":     "Brazil",
            "region_name": "Rio de Janeiro",
            "source":      "M-PERF-A1 profiling — coastal corner",
        },
    ),
)


_BASELINE_DIR = Path("tests/baselines/m_perf_a1")
_REPORT_PATH  = Path("docs/M-PERF-A1_profiling_report.md")


# ---------------------------------------------------------------------------
# EE init mirrors tools/regen_demo_saved_analyses.py
# ---------------------------------------------------------------------------

def _init_ee() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        sys.exit("EE_PROJECT_ID is not set; aborting.")
    ee.Initialize(project=project)


# ---------------------------------------------------------------------------
# Per-AOI run + capture
# ---------------------------------------------------------------------------

def _run_one_aoi(aoi: RegressionAOI) -> dict:
    """Execute one screening, then dump the result + profile snapshot."""
    print(f"[profile] {aoi.name} — starting…")
    aoi_dict = {"centre": aoi.centre, "radius_km": aoi.radius_km}
    indicators = set(ALL_INDICATOR_IDS)

    reset_profile()
    set_profiling_enabled(True)

    wall_start = time.perf_counter()
    payload = ScreeningRun(
        aoi=aoi_dict,
        selected_indicators=indicators,
        time_range=_TIME_RANGE,
        ee_client=None,
        centre_metadata=aoi.centre_metadata,
    ).run()
    wall_elapsed = time.perf_counter() - wall_start

    # Snapshot before disabling so we don't drop in-flight increments.
    profile_rows = snapshot_profile()
    set_profiling_enabled(False)

    total_calls    = sum(row["count"] for row in profile_rows)
    total_failures = sum(row["failures"] for row in profile_rows)

    print(
        f"[profile]   wall={wall_elapsed:.1f}s  "
        f"getInfo calls={total_calls}  failures={total_failures}"
    )

    return {
        "aoi": asdict(aoi),
        "time_range": list(_TIME_RANGE),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "wall_time_seconds": round(wall_elapsed, 3),
        "total_getinfo_calls": total_calls,
        "total_getinfo_failures": total_failures,
        "profile": profile_rows,
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def _aggregate_across_aois(per_aoi: list[dict]) -> list[dict]:
    """Sum getInfo counts across AOIs, per call site.

    The Step B batching plan wants a single "top offenders across the
    behavioural corners" view — a row that's #1 in DF but absent from
    Sapezal is still a strong batching candidate, but the AOI-by-AOI
    view alone hides that pattern."""
    accumulator: dict[tuple[str, str], dict] = {}
    for record in per_aoi:
        for row in record["profile"]:
            key = (row["module"], row["function"])
            agg = accumulator.setdefault(
                key,
                {
                    "module": row["module"],
                    "function": row["function"],
                    "total_count": 0,
                    "total_seconds": 0.0,
                    "per_aoi_counts": {},
                },
            )
            agg["total_count"]   += row["count"]
            agg["total_seconds"] += row["total_seconds"]
            agg["per_aoi_counts"][record["aoi"]["aoi_id"]] = row["count"]
    rows = list(accumulator.values())
    rows.sort(key=lambda r: (-r["total_count"], r["module"], r["function"]))
    return rows


def _write_markdown_report(per_aoi: list[dict], aggregate: list[dict]) -> None:
    """Render the Step A profiling report skeleton with measured data."""
    aoi_ids = [record["aoi"]["aoi_id"] for record in per_aoi]

    lines: list[str] = []
    lines.append("# M-PERF-A1 — Profiling report (Step A output)")
    lines.append("")
    lines.append(
        f"*Captured {datetime.now(timezone.utc).isoformat()} via "
        f"`tools/m_perf_a1_profile.py`.*"
    )
    lines.append("")
    lines.append("## 1. Coverage")
    lines.append("")
    lines.append("| AOI | Centre | Radius | Wall time | getInfo calls | Failures |")
    lines.append("|---|---|---|---:|---:|---:|")
    for record in per_aoi:
        aoi = record["aoi"]
        centre = aoi["centre"]
        lines.append(
            f"| {aoi['name']} | ({centre['lat']:.4f}, {centre['lon']:.4f}) | "
            f"{aoi['radius_km']} km | {record['wall_time_seconds']:.1f} s | "
            f"{record['total_getinfo_calls']} | "
            f"{record['total_getinfo_failures']} |"
        )
    lines.append("")
    lines.append(
        "Spec PF16 named four behavioural corners (Sapezal, DF, coastal, "
        "cloudy). The cloudy/sparse AOI is omitted from this pass because "
        "M-FALLBACK-A1's climatology fallback path is not yet operational; "
        "re-add it once that milestone lands."
    )
    lines.append("")

    lines.append("## 2. Top offenders — aggregate getInfo count across AOIs")
    lines.append("")
    header_cols = "| Rank | Module | Function | Total | Total seconds | "
    header_cols += " | ".join(aoi_ids) + " |"
    sep = "|---:|---|---|---:|---:|" + "|".join(["---:"] * len(aoi_ids)) + "|"
    lines.append(header_cols)
    lines.append(sep)
    for rank, row in enumerate(aggregate, start=1):
        per_aoi_cells = " | ".join(
            str(row["per_aoi_counts"].get(aid, 0)) for aid in aoi_ids
        )
        lines.append(
            f"| {rank} | `{row['module']}` | `{row['function']}` | "
            f"{row['total_count']} | {row['total_seconds']:.1f} | "
            f"{per_aoi_cells} |"
        )
    lines.append("")

    lines.append("## 3. Per-AOI breakdown")
    lines.append("")
    for record in per_aoi:
        aoi = record["aoi"]
        lines.append(f"### {aoi['name']}")
        lines.append("")
        lines.append(f"- Baseline fixture: `tests/baselines/m_perf_a1/{aoi['aoi_id']}.json`")
        lines.append(f"- Wall time: {record['wall_time_seconds']:.1f} s")
        lines.append(f"- getInfo calls: {record['total_getinfo_calls']}")
        lines.append(f"- Failures (retried + reraised): {record['total_getinfo_failures']}")
        lines.append("")
        lines.append("| Module | Function | Count | Seconds | Failures |")
        lines.append("|---|---|---:|---:|---:|")
        for row in record["profile"]:
            lines.append(
                f"| `{row['module']}` | `{row['function']}` | {row['count']} | "
                f"{row['total_seconds']:.1f} | {row['failures']} |"
            )
        lines.append("")

    lines.append("## 4. Step B — batching candidates (to confirm)")
    lines.append("")
    lines.append(
        "The Step B plan picks the top N offenders from §2. Hypothesis from "
        "spec PF10 (to confirm against the table above):"
    )
    lines.append("")
    lines.append(
        "- Nature's per-indicator reductions (7 main + regional_loss + spatial_link)"
    )
    lines.append("- The duplicate DW mode composites (habitat + spatial_link)")
    lines.append("- Air's 9 per-pollutant six-step reductions")
    lines.append("")
    lines.append(
        "Each candidate should be assessed on (a) absolute count, (b) whether "
        "co-located reductions can combine into a single `ee.Dictionary`, "
        "(c) whether sharing crosses a function boundary (PF14 — pure call-"
        "consolidation only)."
    )
    lines.append("")

    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"[profile] wrote {_REPORT_PATH}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--aoi",
        choices=[a.aoi_id for a in _AOIS] + ["all"],
        default="all",
        help="Run only one AOI (sapezal_5km / distrito_federal_43_1km / "
             "rio_coastal_20km), or 'all' for the full pass.",
    )
    parser.add_argument(
        "--no-retry",
        action="store_true",
        help="Install the resilience wrapper with retries disabled "
             "(for un-wrapped baseline reproduction).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    _init_ee()

    # Install the wrapper before any pillar code touches EE. Idempotent
    # so a re-import path can't double-wrap.
    install_getinfo_wrapper(
        enable_retry=not args.no_retry,
        enable_profile=True,
    )

    _BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    aois = _AOIS if args.aoi == "all" else tuple(
        a for a in _AOIS if a.aoi_id == args.aoi
    )

    per_aoi: list[dict] = []
    for aoi in aois:
        record = _run_one_aoi(aoi)
        out_path = _BASELINE_DIR / f"{aoi.aoi_id}.json"
        out_path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"[profile]   wrote {out_path}")
        per_aoi.append(record)

    if len(per_aoi) == len(_AOIS):
        # Only write the combined report when we have all three AOIs;
        # a partial pass would produce a misleading "top offenders" view.
        aggregate = _aggregate_across_aois(per_aoi)
        _write_markdown_report(per_aoi, aggregate)
    else:
        print(
            "[profile] partial pass — skipping combined report; re-run with "
            "--aoi all to refresh docs/M-PERF-A1_profiling_report.md."
        )

    print("[profile] done.")


if __name__ == "__main__":
    main()
