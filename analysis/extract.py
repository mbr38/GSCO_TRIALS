"""Step C — AOD<->PM2.5 extraction.

For each locked location over the window 2025-11-01 .. 2026-04-30:
  PM2.5  (OpenAQ /v3/sensors/{id}/days): per-day mean + per-day max, window mean.
  AOD    (MODIS/061/MCD19A2_GRANULES, Optical_Depth_055, AOD_QA bits 8-11 mask):
         per-day mean at the STATION'S EXACT COORDINATES (1 km ~ MAIAC pixel),
         recorded as raw DN (engine convention, scale_factor=1.0) and physical
         AOD (xptr 0.001). Window mean.
  ENGINE severity: engine.air.compute_aod over a 5 km facility AOI centred on the
         station -> site/background/anomaly/z/confidence, mapped to the engine's
         z-score severity band (ui.components.severity.severity_zscore).

Writes:
  analysis/aod_pm25_validation.csv  — one row per location (the headline table)
  analysis/aod_pm25_daily.csv       — long format (location, date, pm25, aod) for
                                      the daily-correlation analysis in Step D.

Alignment choice (Step A.4): AOD sampled at the station's exact coordinates, NOT
the AOI centre, so AOD<->PM2.5 is directly comparable. The engine-severity column
uses the 5 km facility AOI (the screening default) because the engine's band is an
anomaly z-score that requires the site buffer + background ring.

NOT production code. Reads OPENAQ_API_KEY + EE_PROJECT_ID from env.
"""
import os, sys, json, time, csv, math, datetime as dt
import urllib.parse, urllib.request
from collections import defaultdict

# repo root on path (script lives in analysis/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KEY = os.environ.get("OPENAQ_API_KEY")
PROJ = os.environ.get("EE_PROJECT_ID")
WIN_FROM, WIN_TO = "2025-11-01", "2026-05-01"   # to is exclusive upper bound
AOD_SCALE = 0.001                                # MAIAC Optical_Depth_055 DN -> AOD
AOD_QA_VALID_BIT_MASK = 0xF00                    # engine.constants
FACILITY_RADIUS_KM = 5.0                         # PLFS P-04 single-supplier default
if not KEY or not PROJ:
    print("FATAL: need OPENAQ_API_KEY and EE_PROJECT_ID"); sys.exit(1)

LOCS = json.load(open("analysis/locked_locations.json"))

# ---------------- OpenAQ PM2.5 ----------------
def oaq(path, params):
    url = f"https://api.openaq.org/v3{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"X-API-Key": KEY})
    for _ in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(10); continue
            return {"error": f"HTTP {e.code}"}
        except Exception:
            time.sleep(3)
    return {"error": "retries"}


def pm25_daily(sensor_id):
    """Return {date(str) -> (mean, max)} of daily PM2.5 over the window."""
    r = oaq(f"/sensors/{sensor_id}/days",
            {"date_from": WIN_FROM, "date_to": WIN_TO, "limit": 400})
    time.sleep(1.0)
    out = {}
    if "error" in r:
        return out, r["error"]
    for d in r.get("results", []):
        v = d.get("value")
        if v is None:
            continue
        day = d["period"]["datetimeFrom"]["utc"][:10]
        mx = (d.get("summary") or {}).get("max")
        out[day] = (float(v), float(mx) if mx is not None else None)
    return out, None


# ---------------- Earth Engine AOD ----------------
import ee
ee.Initialize(project=PROJ)
from engine.air import compute_aod
from ui.components.severity import severity_zscore


def aod_qa_mask(img):
    qa = img.select("AOD_QA")
    return img.updateMask(qa.bitwiseAnd(AOD_QA_VALID_BIT_MASK).eq(0))


def aod_daily_at_point(lat, lon):
    """Per-UTC-day mean AOD DN at the exact station point. Monthly getRegion
    chunks keep the element count bounded."""
    pt = ee.Geometry.Point([lon, lat])
    base = (ee.ImageCollection("MODIS/061/MCD19A2_GRANULES")
            .map(aod_qa_mask).select("Optical_Depth_055"))
    months = [("2025-11-01", "2025-12-01"), ("2025-12-01", "2026-01-01"),
              ("2026-01-01", "2026-02-01"), ("2026-02-01", "2026-03-01"),
              ("2026-03-01", "2026-04-01"), ("2026-04-01", "2026-05-01")]
    by_day = defaultdict(list)
    for a, b in months:
        col = base.filterDate(a, b).filterBounds(pt)
        try:
            rows = col.getRegion(pt, 1000).getInfo()
        except Exception as e:
            if "No bands" in str(e) or "empty" in str(e).lower():
                continue
            raise
        if not rows or len(rows) < 2:
            continue
        hdr = rows[0]
        ti, vi = hdr.index("time"), hdr.index("Optical_Depth_055")
        for row in rows[1:]:
            val = row[vi]
            if val is None:
                continue
            day = dt.datetime.utcfromtimestamp(row[ti] / 1000.0).strftime("%Y-%m-%d")
            by_day[day].append(val)
    return {day: sum(v) / len(v) for day, v in by_day.items()}


def engine_severity(lat, lon):
    """Run the engine's AOD snapshot over a 5 km AOI; return its emitted band."""
    aoi = {"centre": {"lat": lat, "lon": lon}, "radius_km": FACILITY_RADIUS_KM}
    try:
        res = compute_aod(aoi, (WIN_FROM, WIN_TO), "screening", ee_client=None)
    except Exception as e:
        return {"engine_error": str(e)[:160]}
    prov = (res.get("_provenance") or {}).get("air", {}).get("aod")
    g = lambda k: res.get(f"air.aod.{k}")
    z, conf = g("z"), g("confidence")
    band = severity_zscore(z, conf, prov)
    return {"engine_site_dn": g("site"), "engine_background_dn": g("background"),
            "engine_anomaly": g("anomaly"), "engine_z": z,
            "engine_confidence": conf, "engine_severity": band}


# ---------------- main ----------------
summary_rows, daily_rows = [], []
print(f"Extracting {len(LOCS)} locations | window {WIN_FROM}..{WIN_TO}\n", flush=True)

for loc in LOCS:
    i, name, regime = loc["loc_index"], loc["candidate"], loc["regime"]
    slat, slon = loc["station_lat"], loc["station_lon"]
    print(f"[{i:>2}/{len(LOCS)}] {regime:<11} {name:<22} ...", end="", flush=True)

    pm, pm_err = pm25_daily(loc["sensor_id"])
    aod = aod_daily_at_point(slat, slon)
    eng = engine_severity(slat, slon)

    # daily long rows (union of days with either signal)
    for day in sorted(set(pm) | set(aod)):
        pm_mean = pm.get(day, (None, None))[0]
        pm_max = pm.get(day, (None, None))[1]
        aod_dn = aod.get(day)
        daily_rows.append({
            "loc_index": i, "regime": regime, "location": name, "date": day,
            "pm25_ugm3": round(pm_mean, 2) if pm_mean is not None else "",
            "pm25_max_ugm3": round(pm_max, 2) if pm_max is not None else "",
            "aod_dn": round(aod_dn, 2) if aod_dn is not None else "",
            "aod_scaled": round(aod_dn * AOD_SCALE, 4) if aod_dn is not None else "",
        })

    pm_vals = [v[0] for v in pm.values()]
    pm_maxes = [v[1] for v in pm.values() if v[1] is not None]
    aod_vals = list(aod.values())
    row = {
        "loc_index": i, "regime": regime, "location": name,
        "station": loc["station"], "sensor_id": loc["sensor_id"],
        "station_lat": slat, "station_lon": slon, "dist_km": loc["dist_km"],
        "completeness_pct": loc["pct"], "origin": loc["origin"],
        "pm25_n_days": len(pm_vals),
        "pm25_mean_ugm3": round(sum(pm_vals) / len(pm_vals), 2) if pm_vals else None,
        "pm25_p_max_daily_ugm3": round(max(pm_maxes), 2) if pm_maxes else None,
        "aod_n_days": len(aod_vals),
        "aod_mean_dn": round(sum(aod_vals) / len(aod_vals), 2) if aod_vals else None,
        "aod_mean_scaled": round(sum(aod_vals) / len(aod_vals) * AOD_SCALE, 4) if aod_vals else None,
    }
    row.update(eng)
    if pm_err:
        row["pm_error"] = pm_err
    summary_rows.append(row)
    print(f" pm25={row['pm25_mean_ugm3']} ugm3 ({row['pm25_n_days']}d) | "
          f"aod={row['aod_mean_scaled']} ({row['aod_n_days']}d) | "
          f"engine={eng.get('engine_severity', eng.get('engine_error'))}", flush=True)

# write CSVs
sum_cols = ["loc_index", "regime", "location", "station", "sensor_id",
            "station_lat", "station_lon", "dist_km", "completeness_pct", "origin",
            "pm25_n_days", "pm25_mean_ugm3", "pm25_p_max_daily_ugm3",
            "aod_n_days", "aod_mean_dn", "aod_mean_scaled",
            "engine_site_dn", "engine_background_dn", "engine_anomaly",
            "engine_z", "engine_confidence", "engine_severity",
            "engine_error", "pm_error"]
with open("analysis/aod_pm25_validation.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=sum_cols)
    w.writeheader()
    for r in summary_rows:
        w.writerow({k: r.get(k, "") for k in sum_cols})

with open("analysis/aod_pm25_daily.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["loc_index", "regime", "location", "date",
                                      "pm25_ugm3", "pm25_max_ugm3", "aod_dn", "aod_scaled"])
    w.writeheader()
    w.writerows(daily_rows)

print(f"\nwrote analysis/aod_pm25_validation.csv ({len(summary_rows)} rows)")
print(f"wrote analysis/aod_pm25_daily.csv ({len(daily_rows)} rows)")
