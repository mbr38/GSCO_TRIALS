"""Regenerate the per-country climatology fixture (M-FALLBACK-A1 §4.3).

One-off / annual pipeline. For each in-scope indicator
(``engine.constants.CLIMATOLOGY_INDICATORS``: 9 Air + CH₄ + VIIRS) and each
country in the GAUL level0 boundary asset, it computes the area-weighted
per-country median + standard deviation over a 3-year window, in the same
display units the pillar engine produces (it reuses the pillars' own asset
configs, so the climatology baseline and the live ``site`` value are
directly comparable in the z-score).

Output is written to ``demo/climatology.json`` with vintage metadata. The
pipeline is idempotent — re-running the same window produces bit-identical
output (sorted keys, no timestamps in the values).

Mirrors the EE-init + write-fixture pattern of
``tools/regen_saved_analyses_m_tier_a3.py``.

Usage:
    EE_PROJECT_ID=<project> .venv/bin/python tools/regen_climatology_fixtures.py
    # dev: only a few countries, to sanity-check before the full run
    EE_PROJECT_ID=<project> .venv/bin/python tools/regen_climatology_fixtures.py \
        --countries Brazil India --vintage 2026

The full run (~200 countries × 11 indicators) costs a few hours of EE
quota. Refresh annually (FB13): drop the oldest year, add the newest.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make the repo root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.constants import CLIMATOLOGY_COUNTRY_ASSET, CLIMATOLOGY_INDICATORS  # noqa: E402

_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "demo" / "climatology.json"

# Country-scale reductions over native pixels are enormous; reduce at a
# deliberately coarse scale and let bestEffort downsample further. Country
# medians are robust to this — we want a regional baseline, not a fenceline
# measurement.
_DEFAULT_REDUCE_SCALE_M = 10_000.0


def _init_ee() -> None:
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        sys.exit("EE_PROJECT_ID not set — export it before running.")
    import ee

    ee.Initialize(project=project)


def _indicator_asset(indicator_key: str):
    """Return (asset_id, band, scale_factor, preprocess) for an indicator,
    reusing the pillars' own configs so units match the live engine."""
    pillar = indicator_key.split(".")[0]
    name = indicator_key.split(".")[1]
    if pillar == "air":
        from engine.air import AIR_POLLUTANT_CONFIG

        cfg = AIR_POLLUTANT_CONFIG[name]
        return cfg.asset_id, cfg.band, cfg.scale_factor, cfg.preprocess
    if pillar == "ghg":
        from engine.ghg import GHG_INDICATOR_CONFIG

        cfg = GHG_INDICATOR_CONFIG[name]
        return cfg.asset_id, cfg.band, cfg.scale_factor, getattr(cfg, "preprocess", None)
    raise ValueError(f"climatology not defined for pillar {pillar!r}")


def _scaled_mean_image(indicator_key: str, window: tuple[str, str], geom):
    """Build the window-mean image for one indicator, scaled to display units.

    `geom` restricts the collection via `filterBounds` — the standard EE
    idiom. For granule-footprint assets (MAIAC AOD, VIIRS NTL) this slashes
    the number of images touched; for global daily grids (S5P L3, CAMS) it's
    a no-op on image count but harmless. Build per-country (it's lazy — no
    getInfo until `reduceRegion`).
    """
    import ee

    asset_id, band, scale_factor, preprocess = _indicator_asset(indicator_key)
    ic = (
        ee.ImageCollection(asset_id)
        .filterDate(window[0], window[1])
        .filterBounds(geom)
    )
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


def _country_stats(country_geom, image, band: str, scale_m: float):
    """Area-weighted median + stdDev of `band` over `country_geom`."""
    import ee

    reducers = ee.Reducer.median().combine(ee.Reducer.stdDev(), sharedInputs=True)
    info = image.reduceRegion(
        reducer=reducers,
        geometry=country_geom,
        scale=scale_m,
        bestEffort=True,
        maxPixels=int(1e10),
    ).getInfo()
    median = info.get(f"{band}_median") if info else None
    std = info.get(f"{band}_stdDev") if info else None
    return median, std


def _country_geometries(only: list[str] | None):
    """Yield (name, geometry) for each GAUL level0 country (optionally filtered)."""
    import ee

    fc = ee.FeatureCollection(CLIMATOLOGY_COUNTRY_ASSET)
    if only:
        fc = fc.filter(ee.Filter.inList("ADM0_NAME", only))
    names = fc.aggregate_array("ADM0_NAME").distinct().sort().getInfo()
    for name in names:
        geom = fc.filter(ee.Filter.eq("ADM0_NAME", name)).geometry()
        yield str(name), geom


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vintage", default="2026", help="Published vintage year")
    parser.add_argument(
        "--window-start", default="2023-01-01", help="3-year window start (ISO)"
    )
    parser.add_argument(
        "--window-end", default="2025-12-31", help="3-year window end (ISO)"
    )
    parser.add_argument(
        "--scale-m", type=float, default=_DEFAULT_REDUCE_SCALE_M,
        help="Reduction scale in metres (coarse for country-level)",
    )
    parser.add_argument(
        "--countries", nargs="*", default=None,
        help="Restrict to these ADM0_NAME values (dev sanity-check)",
    )
    parser.add_argument(
        "--simplify-m", type=float, default=5000.0,
        help="Simplify country polygons to this maxError (m); 0 disables. "
             "Cuts vertex count for complex coastlines (Brazil, Indonesia).",
    )
    parser.add_argument(
        "--out", default=str(_FIXTURE_PATH), help="Output fixture path"
    )
    args = parser.parse_args()

    _init_ee()
    window = (args.window_start, args.window_end)

    countries: dict[str, dict] = {}
    for name, geom in _country_geometries(args.countries):
        if args.simplify_m:
            geom = geom.simplify(maxError=args.simplify_m)
        entry: dict[str, dict] = {}
        for ind in CLIMATOLOGY_INDICATORS:
            # Build per-country so filterBounds(geom) can prune granule-based
            # collections. Lazy — no getInfo until _country_stats.
            image, band = _scaled_mean_image(ind, window, geom)
            try:
                median, std = _country_stats(geom, image, band, args.scale_m)
            except Exception as err:  # noqa: BLE001 — log & continue per country×indicator
                print(f"  ! {name} / {ind}: {err}", file=sys.stderr)
                median, std = None, None
            if median is not None and std is not None:
                entry[ind] = {"median": round(float(median), 4), "std": round(float(std), 4)}
            print(f"  {name} / {ind}: {'ok' if ind in entry else 'skip'}", flush=True)
        if entry:
            countries[name] = dict(sorted(entry.items()))
        print(f"  {name}: {len(entry)}/{len(CLIMATOLOGY_INDICATORS)} indicators", flush=True)

    fixture = {
        "_meta": {
            "schema": "gsco.climatology.v1",
            "vintage": args.vintage,
            "source_window": f"{window[0]}/{window[1]}",
            "granularity": "per_country",
            "country_asset": CLIMATOLOGY_COUNTRY_ASSET,
            "country_key": "ADM0_NAME",
            "indicators": list(CLIMATOLOGY_INDICATORS),
            "reduce_scale_m": args.scale_m,
            "stats": "Per-country area-weighted median and standard deviation over the source window.",
            "generated_by": "tools/regen_climatology_fixtures.py",
            "is_placeholder": False,
        },
        "countries": dict(sorted(countries.items())),
    }

    out_path = Path(args.out)
    out_path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False, sort_keys=False) + "\n")
    print(f"Wrote {len(countries)} countries → {out_path}")


if __name__ == "__main__":
    main()
