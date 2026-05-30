"""AAI ↔ FIRMS / dust-catalog event validation — extraction harness (Step C).

Validates whether the post-M-DIAG-A1 AAI (Absorbing Aerosol Index) signal fires
at known smoke/dust events. This module is *engine-faithful*: it reuses the exact
production reductions from ``engine.core.repeatable_core`` and ``engine.air`` so the
per-day ``z`` / ``is_hot`` series it reconstructs matches what the screening engine
computes server-side (the engine only returns the aggregate ``hf`` to callers — see
``docs/aai_firms_validation.md`` §2 for why a reconstruction is necessary).

What it produces:
  analysis/aai_firms_validation.csv       — one row per (event, day): raw AAI, z, is_hot, FIRMS count
  analysis/aai_firms_event_summary.csv    — one row per event/control: engine-official z & hf, hit/miss

Run:  EE_PROJECT_ID=supply-chain-observatory python analysis/aai_firms_extract.py

Method notes (cite engine source):
  * AAI asset: COPERNICUS/S5P/OFFL/L3_AER_AI, band absorbing_aerosol_index — data starts 2018-07.
  * Background = land-masked annulus r_site→5·r_site (5→25 km at radius_km=5),
    computed over the SAME event window as the site (engine has no climatology
    baseline for AAI; seasonal filter is a no-op). Indicators_Computation_v4 §0.2 / §6.2.
  * Per-day z = (site_mean − bg_median)/bg_std; is_hot = z ≥ ANOMALY_Z_THRESHOLD (2.0)
    AND valid. A day is "hot" if ANY S5P granule that UTC day fires — matches
    engine/core/repeatable_core.py::_server_side_hf::per_image (post-M-DIAG-A1 fix).
  * FIRMS (ee.ImageCollection("FIRMS")) is NOT in the GSCO engine catalog — it is read
    here directly as public ground truth for fire events only.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

os.environ.setdefault("EE_PROJECT_ID", "supply-chain-observatory")

import ee
import pandas as pd

from engine.air import AIR_POLLUTANT_CONFIG, _build_image_collection, compute_pollutant_snapshot
from engine.core.buffers import site_buffer, background_ring
from engine.core.repeatable_core import background_value
from engine.constants import (
    ANOMALY_Z_THRESHOLD,
    BACKGROUND_RING_RADIUS_MULTIPLE,
    BACKGROUND_RING_MAX_KM,
)
from engine.exceptions import IndicatorComputeError

MS_PER_UTC_DAY = 86_400_000.0
RADIUS_KM = 5  # production-seed standard (demo/saved_analyses/*.json)
PAD_DAYS = 5   # event window = peak_start − PAD through peak_end + PAD
CONTROL_WINDOW_DAYS = 30
CFG = AIR_POLLUTANT_CONFIG["aai"]
FIRMS_REGION_KM = 50  # ground-truth fire-pixel count radius (wider than the AAI site buffer)


# --------------------------------------------------------------------------- #
# Step B — locked event set (post-2018-07 so Sentinel-5P AER_AI exists)
# --------------------------------------------------------------------------- #
# Each event: id, kind (fire|dust), label, lat, lon, peak_start, peak_end, source.
EVENTS = [
    # ---- Fires (~5) ----
    dict(id="quebec_2023", kind="fire", label="Quebec wildfires (Canada)",
         lat=49.7, lon=-76.0, peak_start="2023-06-01", peak_end="2023-06-08",
         source="2023 Canadian wildfire season; Quebec mega-fires, NASA FIRMS"),
    dict(id="bayarea_2020", kind="fire", label="SF Bay Area smoke (California)",
         lat=37.7, lon=-122.2, peak_start="2020-09-09", peak_end="2020-09-16",
         source="Aug–Sep 2020 CA complex (CZU/SCU/Creek); 'orange sky' day 2020-09-09"),
    dict(id="nsw_2019", kind="fire", label="NSW Black Summer (Australia)",
         lat=-35.5, lon=150.0, peak_start="2019-12-30", peak_end="2020-01-04",
         source="2019–20 Australian Black Summer; NSW south coast peak NYE 2019"),
    dict(id="dixie_2021", kind="fire", label="Dixie Fire (N. California)",
         lat=40.0, lon=-121.2, peak_start="2021-08-05", peak_end="2021-08-15",
         source="2021 Dixie Fire, Plumas/Lassen; FIRMS"),
    dict(id="greece_2023", kind="fire", label="Evros wildfires (NE Greece)",
         lat=41.0, lon=26.2, peak_start="2023-08-21", peak_end="2023-08-28",
         source="2023 Evros/Alexandroupolis wildfires; largest EU fire on record"),
    # ---- Dust (~5) ----
    dict(id="godzilla_2020", kind="dust", label="'Godzilla' Saharan plume (Puerto Rico)",
         lat=18.2, lon=-66.5, peak_start="2020-06-22", peak_end="2020-06-25",
         source="June 2020 record Saharan Air Layer transport to Caribbean"),
    dict(id="beijing_2021", kind="dust", label="Beijing dust storm (China)",
         lat=39.9, lon=116.4, peak_start="2021-03-15", peak_end="2021-03-16",
         source="2021-03-15 worst Beijing sandstorm in a decade (Mongolian dust)"),
    dict(id="baghdad_2022", kind="dust", label="Iraq sandstorm (Baghdad)",
         lat=33.3, lon=44.4, peak_start="2022-05-15", peak_end="2022-05-18",
         source="May 2022 Iraq sandstorm season (repeated regional events)"),
    dict(id="phoenix_2021", kind="dust", label="Monsoon haboob (Phoenix, AZ)",
         lat=33.4, lon=-112.0, peak_start="2021-07-09", peak_end="2021-07-10",
         source="2021-07-09/10 Arizona monsoon haboob"),
    dict(id="dakar_2021", kind="dust", label="Sahel/Bodélé dust outbreak (Dakar)",
         lat=14.7, lon=-17.4, peak_start="2021-03-13", peak_end="2021-03-17",
         source="March 2021 West-African dust outbreak (Bodélé source)"),
]

# Negative controls (~5): same location, a quiet ~30-day window well before the event.
CONTROLS = [
    dict(id="quebec_2023_ctrl", control_for="quebec_2023", label="Quebec — pre-season control",
         lat=49.7, lon=-76.0, win_start="2023-05-01", win_end="2023-05-31",
         source="~1 month before Quebec fires; snowmelt season, no active fire"),
    dict(id="bayarea_2020_ctrl", control_for="bayarea_2020", label="Bay Area — pre-siege control",
         lat=37.7, lon=-122.2, win_start="2020-07-15", win_end="2020-08-14",
         source="Before the 2020-08-16 lightning siege; clear summer air"),
    dict(id="godzilla_2020_ctrl", control_for="godzilla_2020", label="Puerto Rico — control",
         lat=18.2, lon=-66.5, win_start="2020-05-15", win_end="2020-06-14",
         source="Before the June plume (note: minor SAL dust is near-continuous in summer)"),
    dict(id="beijing_2021_ctrl", control_for="beijing_2021", label="Beijing — winter control",
         lat=39.9, lon=116.4, win_start="2021-02-01", win_end="2021-03-03",
         source="~1 month before the March dust storm"),
    dict(id="phoenix_2021_ctrl", control_for="phoenix_2021", label="Phoenix — pre-monsoon control",
         lat=33.4, lon=-112.0, win_start="2021-06-01", win_end="2021-07-01",
         source="Dry pre-monsoon; no haboob activity"),
]


def _iso(d: date) -> str:
    return d.isoformat()


def _event_window(ev: dict) -> tuple[str, str]:
    s = date.fromisoformat(ev["peak_start"]) - timedelta(days=PAD_DAYS)
    e = date.fromisoformat(ev["peak_end"]) + timedelta(days=PAD_DAYS + 1)  # EE end-exclusive
    return _iso(s), _iso(e)


def _aoi(lat: float, lon: float) -> dict:
    return {"centre": {"lat": lat, "lon": lon}, "radius_km": RADIUS_KM}


# --------------------------------------------------------------------------- #
# Engine-faithful per-day reconstruction
# --------------------------------------------------------------------------- #
def _per_image_features(ic_window, geom, band, scale, bg_median, bg_std, z_threshold):
    """Mirror engine/core/repeatable_core.py::_server_side_hf::per_image, but also
    emit the raw site mean + per-image z so we can reconstruct the day-level series.
    Returns a client-side list of feature property dicts."""
    mean_count = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)
    mean_key, count_key = f"{band}_mean", f"{band}_count"
    degenerate = bg_std is None or bg_std <= 0

    def per_image(image):
        red = image.select(band).reduceRegion(
            reducer=mean_count, geometry=geom, scale=scale,
            bestEffort=True, maxPixels=int(1e9),
        )
        count = ee.Number(red.get(count_key, 0))
        is_valid = count.gt(0)
        site_mean = ee.Number(ee.Algorithms.If(is_valid, red.get(mean_key, 0.0), 0.0))
        if degenerate:
            z = ee.Number(0)
            is_hot = ee.Number(0)
        else:
            z = site_mean.subtract(bg_median).divide(bg_std)
            is_hot = z.gte(z_threshold).And(is_valid)
        day_bucket = ee.Number(image.get("system:time_start")).divide(MS_PER_UTC_DAY).floor()
        return ee.Feature(None, {
            "day_bucket": day_bucket,
            "count": count,
            "site_mean": site_mean,
            "z": z,
            "is_valid": is_valid,
            "is_hot": is_hot,
        })

    fc = ic_window.map(per_image)
    feats = fc.getInfo()["features"]
    return [f["properties"] for f in feats]


def _firms_daily_counts(lat, lon, start, end, km):
    """Per-UTC-day FIRMS fire-pixel count in a `km`-radius buffer. Ground truth for fires.
    Returns {day_bucket: n_fire_pixels}."""
    region = site_buffer({"lat": lat, "lon": lon}, km)
    ic = ee.ImageCollection("FIRMS").filterDate(start, end).filterBounds(region.bounds())

    def per_image(image):
        # FIRMS 'T21' band present where a fire was detected; count non-masked pixels.
        n = image.select("T21").reduceRegion(
            reducer=ee.Reducer.count(), geometry=region, scale=1000,
            bestEffort=True, maxPixels=int(1e9),
        ).get("T21")
        day_bucket = ee.Number(image.get("system:time_start")).divide(MS_PER_UTC_DAY).floor()
        return ee.Feature(None, {"day_bucket": day_bucket, "n_fire": n})

    feats = ic.map(per_image).getInfo()["features"]
    out: dict[int, float] = {}
    for f in feats:
        p = f["properties"]
        db = int(p["day_bucket"])
        out[db] = out.get(db, 0.0) + float(p.get("n_fire") or 0.0)
    return out


def _day_bucket_to_iso(db: int) -> str:
    return _iso(date(1970, 1, 1) + timedelta(days=int(db)))


def extract_one(rec: dict, is_control: bool) -> tuple[list[dict], dict]:
    """Returns (per_day_rows, event_summary_row) for one event or control."""
    lat, lon = rec["lat"], rec["lon"]
    if is_control:
        start, end = rec["win_start"], rec["win_end"]
        kind = "control"
    else:
        start, end = _event_window(rec)
        kind = rec["kind"]
    aoi = _aoi(lat, lon)
    band, scale = CFG.band, CFG.scale_m

    r_bg = min(BACKGROUND_RING_RADIUS_MULTIPLE * RADIUS_KM, BACKGROUND_RING_MAX_KM)
    envelope = site_buffer(aoi["centre"], r_bg)
    ic = _build_image_collection(CFG)
    ic_window = ic.filterDate(start, end).filterBounds(envelope.bounds())
    geom = site_buffer(aoi["centre"], RADIUS_KM)

    summary = dict(
        id=rec["id"], kind=kind, label=rec["label"], lat=lat, lon=lon,
        window_start=start, window_end=end, radius_km=RADIUS_KM,
        control_for=rec.get("control_for", ""),
        source=rec["source"],
        bg_median=None, bg_std=None, n_valid_days=0, n_hot_days=0,
        recon_hf=None, engine_z=None, engine_hf=None, engine_n_obs=None,
        max_day_z=None, peak_aai=None, fired_in_window=False,
        # peak-window (event peak only, excludes the ±5d pad) — the brief's hit/miss:
        peak_start=rec.get("peak_start", ""), peak_end=rec.get("peak_end", ""),
        fired_in_peak=False, max_z_in_peak=None, peak_aai_in_peak=None,
        peak_firms_pixels=None, error="",
    )
    per_day: list[dict] = []

    # 1) Background baseline over the SAME window (engine-faithful).
    try:
        ring = background_ring(aoi["centre"], RADIUS_KM)
        bg_median, bg_std = background_value(
            aoi, ic_window, band, seasonal=True, scale=scale, ring=ring,
        )
    except IndicatorComputeError as e:
        summary["error"] = f"background: {type(e).__name__}: {e}"
        return per_day, summary
    summary["bg_median"], summary["bg_std"] = bg_median, bg_std

    # 2) Per-image → per-day reconstruction.
    feats = _per_image_features(ic_window, geom, band, scale, bg_median, bg_std,
                                ANOMALY_Z_THRESHOLD)
    df = pd.DataFrame(feats)
    if df.empty:
        summary["error"] = "no S5P granules in window"
        return per_day, summary

    # 3) FIRMS ground truth (fires only — dust has no fire signal).
    firms = {}
    if kind in ("fire",) or (is_control and rec.get("control_for", "").startswith(("quebec", "bayarea"))):
        try:
            firms = _firms_daily_counts(lat, lon, start, end, FIRMS_REGION_KM)
        except Exception as e:  # FIRMS is best-effort ground truth, never fatal
            summary["error"] = f"firms_warn: {type(e).__name__}"

    # 4) Aggregate per UTC day, matching engine semantics (day hot if ANY granule hot).
    valid_days, hot_days = set(), set()
    for db, g in df.groupby("day_bucket"):
        db = int(db)
        valid_g = g[g["is_valid"].astype(bool)]
        n_valid_imgs = len(valid_g)
        if n_valid_imgs:
            valid_days.add(db)
        day_site = float(valid_g["site_mean"].mean()) if n_valid_imgs else None
        day_z = (day_site - bg_median) / bg_std if (day_site is not None and bg_std) else None
        any_hot = bool(g["is_hot"].astype(bool).any())
        if any_hot:
            hot_days.add(db)
        per_day.append(dict(
            id=rec["id"], kind=kind, label=rec["label"],
            date=_day_bucket_to_iso(db),
            site_aai=day_site, bg_median=bg_median, bg_std=bg_std,
            z=day_z, is_hot=int(any_hot),
            n_granules=int(len(g)), n_valid_granules=n_valid_imgs,
            firms_fire_pixels=float(firms.get(db, 0.0)),
        ))

    per_day.sort(key=lambda r: r["date"])
    summary["n_valid_days"] = len(valid_days)
    summary["n_hot_days"] = len(hot_days)
    summary["recon_hf"] = (len(hot_days) / len(valid_days)) if valid_days else None
    zs = [r["z"] for r in per_day if r["z"] is not None]
    summary["max_day_z"] = max(zs) if zs else None
    aais = [r["site_aai"] for r in per_day if r["site_aai"] is not None]
    summary["peak_aai"] = max(aais) if aais else None
    summary["fired_in_window"] = bool(hot_days)

    # Peak-window hit/miss (the brief's question: did z fire DURING the event peak?).
    if not is_control:
        ps, pe = rec["peak_start"], rec["peak_end"]
        peak_rows = [r for r in per_day if ps <= r["date"] <= pe]
        pz = [r["z"] for r in peak_rows if r["z"] is not None]
        pa = [r["site_aai"] for r in peak_rows if r["site_aai"] is not None]
        summary["fired_in_peak"] = any(r["is_hot"] for r in peak_rows)
        summary["max_z_in_peak"] = max(pz) if pz else None
        summary["peak_aai_in_peak"] = max(pa) if pa else None
        summary["peak_firms_pixels"] = sum(r["firms_fire_pixels"] for r in peak_rows) or None

    # 5) Engine-official aggregate cross-check via the production entry point.
    try:
        snap = compute_pollutant_snapshot(aoi, "aai", (start, end), "screening", ee)
        summary["engine_z"] = snap.get("air.aai.z")
        summary["engine_hf"] = snap.get("air.aai.hf")
        prov = snap.get("_provenance.air.aai", {})
        summary["engine_n_obs"] = (prov.get("extra") or {}).get("n_valid_dates")
    except Exception as e:
        summary["error"] = (summary["error"] + f" | engine_snap: {type(e).__name__}: {e}").strip(" |")

    return per_day, summary


def main():
    ee.Initialize(project=os.environ["EE_PROJECT_ID"])
    all_rows: list[dict] = []
    summaries: list[dict] = []
    items = [(e, False) for e in EVENTS] + [(c, True) for c in CONTROLS]
    for rec, is_ctrl in items:
        tag = "CTRL" if is_ctrl else rec["kind"].upper()
        print(f"[{tag:5}] {rec['id']:20} … ", end="", flush=True)
        try:
            rows, summ = extract_one(rec, is_ctrl)
        except Exception as e:
            print(f"FAILED: {type(e).__name__}: {e}")
            summaries.append(dict(id=rec["id"], kind=("control" if is_ctrl else rec["kind"]),
                                  label=rec["label"], error=f"{type(e).__name__}: {e}"))
            continue
        all_rows.extend(rows)
        summaries.append(summ)
        z = summ.get("max_day_z")
        print(f"days={summ['n_valid_days']:3} hot={summ['n_hot_days']:3} "
              f"recon_hf={summ['recon_hf']} engine_z={summ['engine_z']} "
              f"engine_hf={summ['engine_hf']} maxz={z if z is None else round(z,2)} "
              f"{'⚠ '+summ['error'] if summ['error'] else ''}")

    here = os.path.dirname(os.path.abspath(__file__))
    pd.DataFrame(all_rows).to_csv(os.path.join(here, "aai_firms_validation.csv"), index=False)
    pd.DataFrame(summaries).to_csv(os.path.join(here, "aai_firms_event_summary.csv"), index=False)
    print(f"\nWrote {len(all_rows)} per-day rows and {len(summaries)} event summaries.")


if __name__ == "__main__":
    main()
