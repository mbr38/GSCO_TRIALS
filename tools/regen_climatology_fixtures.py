"""Regenerate the per-country climatology fixture (M-FALLBACK-A1 §4.3).

One-off / annual pipeline. Computes, for each of the 11 in-scope indicators
(``engine.constants.CLIMATOLOGY_INDICATORS``: 9 Air + CH₄ + VIIRS) and every
country in the GAUL level0 boundary asset, the area-weighted per-country
median + standard deviation over a 3-year window — in the same display units
the pillar engine produces (it reuses the pillars' own asset configs, so the
climatology baseline and the live ``site`` value are directly comparable in
the z-score).

**Architecture (covers the whole world).** Instead of one blocking call per
country × indicator (~2,200 round-trips, slow + timeout-prone), this uses
Earth Engine's ``reduceRegions``: ONE server-side graph per indicator reduces
*all* ~250 countries at once. That's 11 calls for the entire planet.

Two run modes:

1. **getInfo (default)** — 11 ``reduceRegions().getInfo()`` calls, one per
   indicator, checkpointing the fixture after each. Resumable. Best when the
   reductions stay under EE's ~5-minute synchronous limit (use a coarse
   ``--scale-m``; country medians don't need fine resolution).

2. **Export (``--export``)** — kicks off 11 ``Export.table.toDrive`` batch
   tasks (one per indicator). Fully async / no timeout: start them, close the
   laptop, download the 11 CSVs from Drive when they finish, then run
   ``--assemble-from <dir>`` to build the fixture. Use this if getInfo times
   out on the heavy daily-mean indicators (S5P, CAMS).

Usage:
    # whole world, getInfo, coarse scale (recommended first try)
    EE_PROJECT_ID=<project> .venv/bin/python tools/regen_climatology_fixtures.py \
        --out demo/climatology.generated.json

    # resume a partial run
    EE_PROJECT_ID=<project> .venv/bin/python tools/regen_climatology_fixtures.py \
        --out demo/climatology.generated.json --resume

    # async batch export → Drive (bulletproof for timeouts)
    EE_PROJECT_ID=<project> .venv/bin/python tools/regen_climatology_fixtures.py --export

    # after downloading the CSVs from Drive
    .venv/bin/python tools/regen_climatology_fixtures.py \
        --assemble-from ~/Downloads/clim_csvs --out demo/climatology.generated.json

Refresh annually (FB13): drop the oldest year, add the newest.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

# Make the repo root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.constants import CLIMATOLOGY_COUNTRY_ASSET, CLIMATOLOGY_INDICATORS  # noqa: E402

_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "demo" / "climatology.json"

# Country-scale zonal stats don't need fine resolution — a coarse scale keeps
# the per-indicator reduceRegions under EE's synchronous getInfo limit.
_DEFAULT_REDUCE_SCALE_M = 25_000.0
_DEFAULT_TILE_SCALE = 4  # split the reduceRegions computation to avoid OOM
_COUNTRY_KEY = "ADM0_NAME"


def _init_ee() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        sys.exit("EE_PROJECT_ID not set — export it before running.")
    import ee

    ee.Initialize(project=project)


def _indicator_asset(indicator_key: str):
    """Return (asset_id, band, scale_factor, preprocess), reusing the pillars'
    own configs so units match the live engine."""
    pillar, name = indicator_key.split(".", 1)
    if pillar == "air":
        from engine.air import AIR_POLLUTANT_CONFIG

        cfg = AIR_POLLUTANT_CONFIG[name]
        return cfg.asset_id, cfg.band, cfg.scale_factor, cfg.preprocess
    if pillar == "ghg":
        from engine.ghg import GHG_INDICATOR_CONFIG

        cfg = GHG_INDICATOR_CONFIG[name]
        return cfg.asset_id, cfg.band, cfg.scale_factor, getattr(cfg, "preprocess", None)
    raise ValueError(f"climatology not defined for pillar {pillar!r}")


def _scaled_mean_image(indicator_key: str, window: tuple[str, str]):
    """Window-mean image for one indicator, scaled to display units. Global —
    the per-country split happens in reduceRegions, not here."""
    import ee

    asset_id, band, scale_factor, preprocess = _indicator_asset(indicator_key)
    ic = ee.ImageCollection(asset_id).filterDate(window[0], window[1])
    if preprocess is not None:
        ic = ic.map(preprocess)
    ic = ic.select(band)
    if scale_factor != 1.0:
        ic = ic.map(
            lambda img: img.multiply(scale_factor)
            .rename(band)
            .copyProperties(img, ["system:time_start", "system:time_end"])
        )
    return ic.mean(), band


# GAUL countries excluded by default. Antarctica's polygon wraps around the
# south pole; when reduceRegions transforms its edge into the image's planar
# pixel grid, an edge vertex maps to a row off the bottom of the world raster
# (the y=-402 pixel-coord that the May 2026 batch ran into). The other
# entries are tiny disputed-territory placeholders without operational
# suppliers — easier to skip than to special-case.
_DEFAULT_EXCLUDED_COUNTRIES: tuple[str, ...] = (
    "Antarctica",
)


def _country_fc(only: list[str] | None, simplify_m: float, bbox_inset: float,
                excluded: list[str] | None):
    """GAUL level0 FeatureCollection, made safe for global reduceRegions.

    Three guards against "Unable to transform edge" errors:

    1. **Exclude Antarctica** (and any other configured country) — its
       polar-wrapping polygon trips reduceRegions even with a generous bbox
       inset, because the polygon WRAPS the pole rather than just nearing it.
    2. **Clip to a poleward-inset world rectangle** (default 1°) — keeps
       countries with polar-adjacent geometry (e.g. Greenland) safely inside
       the image's valid pixel extent.
    3. **Antimeridian-inset** of the same world rectangle — avoids the
       Russia / USA-Aleutians / Fiji / Kiribati edge-on-±180° trigger.

    Simplify is opt-in (off by default): aggressive simplification can
    *create* the antimeridian-vertex pathology this guard exists to prevent.
    """
    import ee

    fc = ee.FeatureCollection(CLIMATOLOGY_COUNTRY_ASSET)
    skip = list(excluded if excluded is not None else _DEFAULT_EXCLUDED_COUNTRIES)
    if skip:
        fc = fc.filter(ee.Filter.inList(_COUNTRY_KEY, skip).Not())
    if only:
        fc = fc.filter(ee.Filter.inList(_COUNTRY_KEY, only))
    if bbox_inset > 0:
        world = ee.Geometry.Rectangle(
            [-180 + bbox_inset, -90 + bbox_inset,
             180 - bbox_inset, 90 - bbox_inset],
            proj="EPSG:4326", geodesic=False,
        )
        fc = fc.map(
            lambda f: f.setGeometry(f.geometry().intersection(world, maxError=1000))
        )
    if simplify_m:
        fc = fc.map(
            lambda f: f.setGeometry(f.geometry().simplify(maxError=simplify_m))
        )
    return fc


def _stats_fc(indicator_key: str, window, fc, scale_m: float, tile_scale: int):
    """reduceRegions FeatureCollection: one feature per country carrying the
    median + stdDev of the indicator (server-side, all countries at once).

    ``crs="EPSG:4326"`` is set explicitly so the reduction runs in plain
    lat/lon — without it EE picks the image's native projection (S5P/MAIAC
    sinusoidal etc.) and edge-transform errors at the antimeridian fire.
    """
    import ee

    image, band = _scaled_mean_image(indicator_key, window)
    reducers = ee.Reducer.median().combine(ee.Reducer.stdDev(), sharedInputs=True)
    return image.reduceRegions(
        collection=fc,
        reducer=reducers,
        scale=scale_m,
        tileScale=tile_scale,
        crs="EPSG:4326",
    ), band


def _extract_per_country(features: list[dict], band: str) -> dict[str, tuple[float, float]]:
    """Pull {country: (median, std)} out of a reduceRegions getInfo result."""
    out: dict[str, tuple[float, float]] = {}
    for feat in features:
        props = feat.get("properties", {}) or {}
        name = props.get(_COUNTRY_KEY)
        if not name:
            continue
        # Single-band combined reducer → "median"/"stdDev"; some EE versions
        # band-prefix them. Accept either.
        median = props.get("median", props.get(f"{band}_median"))
        std = props.get("stdDev", props.get(f"{band}_stdDev"))
        if median is None or std is None:
            continue
        out[str(name)] = (float(median), float(std))
    return out


def _merge(countries: dict, indicator: str, per_country: dict) -> None:
    for name, (median, std) in per_country.items():
        countries.setdefault(name, {})[indicator] = {
            "median": round(median, 4), "std": round(std, 4),
        }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _write_fixture(out_path: Path, countries: dict, args, window,
                   done_indicators: list[str], *, complete: bool) -> None:
    fixture = {
        "_meta": {
            "schema": "gsco.climatology.v1",
            "vintage": args.vintage,
            "source_window": f"{window[0]}/{window[1]}",
            "granularity": "per_country",
            "country_asset": CLIMATOLOGY_COUNTRY_ASSET,
            "country_key": _COUNTRY_KEY,
            "indicators": list(CLIMATOLOGY_INDICATORS),
            "reduce_scale_m": args.scale_m,
            "stats": "Per-country area-weighted median and standard deviation over the source window.",
            "generated_by": "tools/regen_climatology_fixtures.py (reduceRegions)",
            "is_placeholder": False,
            "complete": complete,
            "computed_indicators": sorted(done_indicators),
            "country_count": len(countries),
        },
        "countries": dict(sorted(countries.items())),
    }
    out_path.write_text(
        json.dumps(fixture, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    )


def _indicators_to_run(only_indicators: list[str] | None) -> list[str]:
    """Honor ``--only-indicators`` if set, else the full in-scope list."""
    if not only_indicators:
        return list(CLIMATOLOGY_INDICATORS)
    selected = [i for i in only_indicators if i in CLIMATOLOGY_INDICATORS]
    unknown = sorted(set(only_indicators) - set(CLIMATOLOGY_INDICATORS))
    if unknown:
        print(f"WARNING: ignoring unknown --only-indicators: {unknown}", file=sys.stderr)
    return selected


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def _run_getinfo(args, window) -> None:
    out_path = Path(args.out)
    countries: dict[str, dict] = {}
    done: set[str] = set()

    if args.resume and out_path.exists():
        try:
            prior = json.loads(out_path.read_text())
            countries = dict(prior.get("countries", {}))
            done = set(prior.get("_meta", {}).get("computed_indicators", []))
            print(f"Resuming: {len(done)} indicators, {len(countries)} countries already done")
        except (json.JSONDecodeError, OSError) as err:
            print(f"Could not read --out for resume ({err}); starting fresh.")

    fc = _country_fc(args.countries, args.simplify_m, args.bbox_inset, args.exclude_countries)
    indicators = _indicators_to_run(args.only_indicators)

    for ind in indicators:
        if ind in done:
            print(f"  {ind}: skip (already computed)", flush=True)
            continue
        t0 = time.time()
        try:
            stats, band = _stats_fc(ind, window, fc, args.scale_m, args.tile_scale)
            features = stats.getInfo().get("features", [])
            per_country = _extract_per_country(features, band)
        except Exception as err:  # noqa: BLE001 — log & continue per indicator
            print(f"  ! {ind}: {err}", file=sys.stderr, flush=True)
            print(f"    (retry just this one, or use --export for it)", flush=True)
            continue
        _merge(countries, ind, per_country)
        done.add(ind)
        print(
            f"  {ind}: {len(per_country)} countries in {time.time() - t0:.0f}s",
            flush=True,
        )
        # Checkpoint after every indicator — partial run stays usable/resumable.
        _write_fixture(out_path, countries, args, window, list(done), complete=False)

    complete = done.issuperset(CLIMATOLOGY_INDICATORS)
    _write_fixture(out_path, countries, args, window, list(done), complete=complete)
    print(
        f"{'DONE' if complete else 'PARTIAL'} — {len(done)}/{len(CLIMATOLOGY_INDICATORS)} "
        f"indicators, {len(countries)} countries → {out_path}",
        flush=True,
    )


def _run_export(args, window) -> None:
    import ee

    fc = _country_fc(args.countries, args.simplify_m, args.bbox_inset, args.exclude_countries)
    indicators = _indicators_to_run(args.only_indicators)
    tasks = []
    for ind in indicators:
        stats, _band = _stats_fc(ind, window, fc, args.scale_m, args.tile_scale)
        prefix = f"clim_{args.vintage}_{ind.replace('.', '_')}"
        task = ee.batch.Export.table.toDrive(
            collection=stats,
            description=prefix,
            folder=args.export_folder,
            fileNamePrefix=prefix,
            fileFormat="CSV",
            selectors=[_COUNTRY_KEY, "median", "stdDev"],
        )
        task.start()
        tasks.append((ind, prefix, task.id))
        print(f"  started export {prefix} (task {task.id})", flush=True)

    print(
        f"\nStarted {len(tasks)} export tasks → Drive folder '{args.export_folder}'.\n"
        f"Monitor with `earthengine task list` or the Code Editor Tasks tab.\n"
        f"When all complete, download the CSVs and run:\n"
        f"  .venv/bin/python tools/regen_climatology_fixtures.py "
        f"--assemble-from <csv_dir> --out {args.out}\n"
    )


def _run_assemble(args, window) -> None:
    """Build the fixture from downloaded reduceRegions CSVs (one per indicator).

    Matches each CSV to its indicator by the underscored id in the filename
    (e.g. ``clim_2026_air_no2.csv`` → ``air.no2``).
    """
    csv_dir = Path(args.assemble_from)
    countries: dict[str, dict] = {}
    done: list[str] = []
    csvs = list(csv_dir.glob("*.csv"))
    for ind in CLIMATOLOGY_INDICATORS:
        token = ind.replace(".", "_")
        match = next((p for p in csvs if token in p.stem), None)
        if match is None:
            print(f"  ! no CSV found for {ind} (looked for '*{token}*.csv')", file=sys.stderr)
            continue
        per_country: dict[str, tuple[float, float]] = {}
        with match.open(newline="") as fh:
            for row in csv.DictReader(fh):
                name = row.get(_COUNTRY_KEY)
                median, std = row.get("median"), row.get("stdDev")
                if not name or median in (None, "") or std in (None, ""):
                    continue
                try:
                    per_country[name] = (float(median), float(std))
                except ValueError:
                    continue
        _merge(countries, ind, per_country)
        done.append(ind)
        print(f"  {ind}: {len(per_country)} countries from {match.name}")

    out_path = Path(args.out)
    complete = set(done).issuperset(CLIMATOLOGY_INDICATORS)
    _write_fixture(out_path, countries, args, window, done, complete=complete)
    print(f"Assembled {len(done)} indicators, {len(countries)} countries → {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vintage", default="2026", help="Published vintage year")
    parser.add_argument("--window-start", default="2023-01-01", help="3-year window start (ISO)")
    parser.add_argument("--window-end", default="2025-12-31", help="3-year window end (ISO)")
    parser.add_argument(
        "--scale-m", type=float, default=_DEFAULT_REDUCE_SCALE_M,
        help="reduceRegions scale in metres (coarse for country-level)",
    )
    parser.add_argument(
        "--tile-scale", type=int, default=_DEFAULT_TILE_SCALE,
        help="reduceRegions tileScale (raise if you hit 'computed value too large')",
    )
    parser.add_argument(
        "--simplify-m", type=float, default=0.0,
        help="Simplify country polygons to this maxError (m); 0 disables. "
             "Off by default: simplify can create antimeridian-vertex edges "
             "that crash reduceRegions.",
    )
    parser.add_argument(
        "--bbox-inset", type=float, default=1.0,
        help="Clip country geometries to a world rectangle inset this many "
             "degrees from ±180°/±90°. 1° leaves Greenland / extreme-north "
             "land intact while clipping polar-wrapping geometry safely.",
    )
    parser.add_argument(
        "--exclude-countries", nargs="*", default=None,
        help=f"GAUL ADM0_NAME values to skip. Default: "
             f"{list(_DEFAULT_EXCLUDED_COUNTRIES)}",
    )
    parser.add_argument(
        "--only-indicators", nargs="*", default=None,
        help="Restrict the run to this subset of CLIMATOLOGY_INDICATORS "
             "(useful for retrying memory-hungry indicators at a higher "
             "--tile-scale without redoing the whole world).",
    )
    parser.add_argument(
        "--countries", nargs="*", default=None,
        help="Restrict to these ADM0_NAME values (dev sanity-check)",
    )
    parser.add_argument("--out", default=str(_FIXTURE_PATH), help="Output fixture path")
    parser.add_argument(
        "--resume", action="store_true",
        help="getInfo mode: skip indicators already in --out (after a partial run).",
    )
    parser.add_argument(
        "--export", action="store_true",
        help="Async mode: start 11 Export.table.toDrive tasks instead of getInfo.",
    )
    parser.add_argument(
        "--export-folder", default="gsco_climatology",
        help="Drive folder for --export CSVs.",
    )
    parser.add_argument(
        "--assemble-from", default=None,
        help="Build the fixture from downloaded reduceRegions CSVs in this dir.",
    )
    args = parser.parse_args()
    window = (args.window_start, args.window_end)

    if args.assemble_from:
        _run_assemble(args, window)  # no EE needed
        return

    _init_ee()
    if args.export:
        _run_export(args, window)
    else:
        _run_getinfo(args, window)


if __name__ == "__main__":
    main()
