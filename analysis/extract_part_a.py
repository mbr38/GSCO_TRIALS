"""Step C — Part A extraction (activity validation): GHG raw inputs vs ODIAC.

For each of the 25 locked locations, at the 5 km production radius:
  - CH4 anomaly z (raw z-score)            ghg.ch4.z
  - CH4 raw concentration (window mean)    ghg.ch4.site   [ppb]
  - VIIRS raw activity                     ghg.viirs.site
  - VIIRS anomaly z                        ghg.viirs.z
  - ODIAC point sample at AOI centre       [annualised t CO2 / cell]
  - ODIAC AOI-mean (radius-averaged)       ghg.co2.mean   [annualised t CO2 / cell]
  - ODIAC relative intensity (site/ring)   ghg.co2.relative_intensity
  - GHG composite score (context)          ghg.core_audit_support  (CH4+VIIRS, live)
  - coverage / fallback flags

Writes/updates analysis/ghg_odiac_validation.csv (one row per location).
ODIAC uses its 2023 vintage window; CH4/VIIRS use the 2025 production window
(documented temporal mismatch — see docs/ghg_odiac_validation.md §7).

Run: python analysis/extract_part_a.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

import ee
import pandas as pd

from analysis.locations import (
    LOCATIONS, RADIUS_KM, WINDOW_NOW, WINDOW_ODIAC, CSV_PATH,
)

ee.Initialize(project="supply-chain-observatory")

from engine import ghg
from engine.ghg import GHG_INDICATOR_CONFIG
from engine.constants import CO2_TO_C_RATIO


def _num(d: dict, key: str):
    v = d.get(key)
    return float(v) if isinstance(v, (int, float)) else None


def odiac_point_at_centre(lat: float, lon: float) -> float | None:
    """ODIAC value for the single cell at the AOI centre, annualised to
    t CO2 / cell — same units/annualisation as the engine's AOI-mean so the
    point and mean are directly comparable. ODIAC is t C / cell / month."""
    cfg = GHG_INDICATOR_CONFIG["co2"]
    ic = ee.ImageCollection(cfg.asset_id).filterDate(*WINDOW_ODIAC)
    summed = ic.select(cfg.band).sum()  # Σ months → t C / cell over the window
    pt = ee.Geometry.Point([lon, lat])
    combined = ee.Dictionary({
        "n_months": ic.size(),
        "pt": summed.reduceRegion(
            reducer=ee.Reducer.first(), geometry=pt,
            scale=cfg.scale_m, bestEffort=True, maxPixels=int(1e9),
        ),
    }).getInfo() or {}
    n_months = int(combined.get("n_months") or 0)
    raw_t_c = (combined.get("pt") or {}).get(cfg.band)
    if raw_t_c is None or n_months == 0:
        return None
    return float(raw_t_c) * (12.0 / n_months) * CO2_TO_C_RATIO


def extract_location(regime: str, name: str, lat: float, lon: float) -> dict:
    aoi = {"centre": {"lat": lat, "lon": lon}, "radius_km": RADIUS_KM}
    row: dict = {
        "regime": regime, "location": name, "lat": lat, "lon": lon,
        "radius_km": RADIUS_KM,
    }
    flags: list[str] = []

    # CH4 + VIIRS over the 2025 production window
    try:
        ch4 = ghg.compute_ch4_snapshot(aoi, WINDOW_NOW, "screening", None)
        row["ch4_z"] = _num(ch4, "ghg.ch4.z")
        row["ch4_site_ppb"] = _num(ch4, "ghg.ch4.site")
        row["ch4_background_ppb"] = _num(ch4, "ghg.ch4.background")
        row["ch4_anomaly_ppb"] = _num(ch4, "ghg.ch4.anomaly")
        row["ch4_confidence"] = _num(ch4, "ghg.ch4.confidence")
        row["ch4_score"] = _num(ch4, "ghg.ch4.score")
    except Exception as e:
        flags.append(f"ch4_fail:{type(e).__name__}")
        for k in ("ch4_z", "ch4_site_ppb", "ch4_background_ppb",
                  "ch4_anomaly_ppb", "ch4_confidence", "ch4_score"):
            row[k] = None

    try:
        v = ghg.compute_viirs_activity(aoi, WINDOW_NOW, "screening", None)
        row["viirs_site"] = _num(v, "ghg.viirs.site")
        row["viirs_z"] = _num(v, "ghg.viirs.z")
        row["viirs_score"] = _num(v, "ghg.viirs.score")
    except Exception as e:
        flags.append(f"viirs_fail:{type(e).__name__}")
        for k in ("viirs_site", "viirs_z", "viirs_score"):
            row[k] = None

    # ODIAC: AOI-mean (engine) over the 2023 vintage window + centre-point sample
    try:
        co2 = ghg.compute_co2_snapshot(aoi, WINDOW_ODIAC, "screening", None)
        row["odiac_aoi_mean_tco2"] = _num(co2, "ghg.co2.mean")
        row["odiac_total_tco2"] = _num(co2, "ghg.co2.total")
        row["odiac_relative_intensity"] = _num(co2, "ghg.co2.relative_intensity")
    except Exception as e:
        flags.append(f"odiac_fail:{type(e).__name__}")
        for k in ("odiac_aoi_mean_tco2", "odiac_total_tco2",
                  "odiac_relative_intensity"):
            row[k] = None
    try:
        row["odiac_point_tco2"] = odiac_point_at_centre(lat, lon)
    except Exception as e:
        flags.append(f"odiac_point_fail:{type(e).__name__}")
        row["odiac_point_tco2"] = None

    # GHG composite (live, CH4+VIIRS — ODIAC is demoted from the live composite)
    try:
        payload = ghg.run_pillar(
            aoi, WINDOW_NOW, "screening",
            {"ghg.ch4", "ghg.viirs"}, None,
        )
        row["ghg_composite"] = _num(payload, "ghg.core_audit_support")
        row["ghg_activity_score"] = _num(payload, "ghg.activity_score")
        if payload.get("_failures"):
            flags.append("pillar_partial")
    except Exception as e:
        flags.append(f"pillar_fail:{type(e).__name__}")
        row["ghg_composite"] = None
        row["ghg_activity_score"] = None

    row["partA_flags"] = ";".join(flags) if flags else ""
    return row


def main() -> None:
    rows = []
    for i, (regime, name, lat, lon) in enumerate(LOCATIONS, 1):
        print(f"[{i:2d}/25] {regime:9} {name:16} ...", flush=True)
        row = extract_location(regime, name, lat, lon)
        rows.append(row)
        print(
            f"        ch4_z={row.get('ch4_z')!s:>8.8}  "
            f"viirs={row.get('viirs_site')!s:>8.8}  "
            f"odiac_pt={row.get('odiac_point_tco2')!s:>8.8}  "
            f"flags={row.get('partA_flags')}",
            flush=True,
        )
    df = pd.DataFrame(rows)
    df.to_csv(CSV_PATH, index=False)
    print(f"\nWrote {len(df)} rows × {len(df.columns)} cols -> {CSV_PATH}")


if __name__ == "__main__":
    main()
