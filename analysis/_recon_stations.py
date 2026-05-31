"""Step A station reconnaissance for the AOD<->PM2.5 validation (v2 — corrected).

For each candidate location: enumerate OpenAQ PM2.5 stations within 25 km,
keep only those still reporting through the window (datetimeLast >= 2026-04-01),
and for the nearest live stations measure in-window daily completeness via the
/v3/sensors/{id}/days endpoint (date_from/date_to — NOT datetime_*; the API is
inconsistent across endpoints). Pick the nearest station with >50% completeness.

NOT production code — one-shot recon. Reads OPENAQ_API_KEY from env.
"""
import os, sys, time, json, math, urllib.parse, urllib.request

API = "https://api.openaq.org/v3"
KEY = os.environ.get("OPENAQ_API_KEY")
PM25 = 2
WIN_FROM, WIN_TO = "2025-11-01", "2026-05-01"   # to is exclusive-ish upper bound
WIN_DAYS = 181                                  # 1 Nov 2025 .. 30 Apr 2026 incl.
LIVE_CUTOFF = "2026-04-01"                       # station must report past this
MIN_PCT = 50.0
if not KEY:
    print("FATAL: OPENAQ_API_KEY not in env"); sys.exit(1)

CANDIDATES = [
    ("industrial", "Delhi, IN",            28.6139,  77.2090),
    ("industrial", "Beijing, CN",          39.9042, 116.4074),
    ("industrial", "Jakarta, ID",          -6.2088, 106.8456),
    ("industrial", "Mexico City, MX",      19.4326, -99.1332),
    ("industrial", "Lagos, NG",             6.5244,   3.3792),
    ("coal",       "eMalahleni (Mpumalanga), ZA", -25.877, 29.199),
    ("coal",       "Katowice (Silesia), PL", 50.2649, 19.0238),
    ("coal",       "Datong, CN",            40.0764, 113.3001),
    ("coal",       "Singrauli, IN",         24.1997,  82.6755),
    ("coal",       "Pittsburgh PA, US",     40.4406, -79.9959),
    ("biomass",    "Manaus (Amazon), BR",   -3.1190, -60.0217),
    ("biomass",    "Pekanbaru (Sumatra), ID", 0.5071, 101.4478),
    ("biomass",    "Abuja, NG",              9.0765,   7.3986),
    ("biomass",    "Chico CA, US",          39.7285, -121.8375),
    ("biomass",    "Athens, GR",            37.9838,  23.7275),
    ("dust",       "Cairo, EG",             30.0444,  31.2357),
    ("dust",       "Dubai, AE",             25.2048,  55.2708),
    ("dust",       "Lanzhou, CN",           36.0611, 103.8343),
    ("dust",       "Phoenix AZ, US",        33.4484, -112.0740),
    ("dust",       "Kano, NG",              12.0022,   8.5919),
    ("clean",      "Reykjavik, IS",         64.1466, -21.9426),
    ("clean",      "Hobart, AU",           -42.8821, 147.3272),
    ("clean",      "Christchurch, NZ",     -43.5321, 172.6362),
    ("clean",      "Wellington, NZ",       -41.2865, 174.7762),
    ("clean",      "Tromso, NO",            69.6492,  18.9553),
]


def get(path, params):
    url = f"{API}{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"X-API-Key": KEY})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(10); continue
            return {"error": f"HTTP {e.code}"}
        except Exception:
            time.sleep(3)
    return {"error": "retries exhausted"}


def hav(a, b, c, d):
    p = math.radians
    dlat, dlon = p(c - a), p(d - b)
    x = math.sin(dlat/2)**2 + math.cos(p(a))*math.cos(p(c))*math.sin(dlon/2)**2
    return 2 * 6371 * math.asin(math.sqrt(x))


def live_stations(lat, lon):
    """All pm25 stations <=25km reporting past LIVE_CUTOFF, nearest first."""
    out = []
    for page in (1, 2, 3):
        r = get("/locations", {"coordinates": f"{lat},{lon}", "radius": 25000,
                                "parameters_id": PM25, "limit": 100, "page": page})
        time.sleep(1.2)
        if "error" in r:
            break
        res = r.get("results", [])
        for loc in res:
            dl = (loc.get("datetimeLast") or {}).get("utc", "") or ""
            if dl < LIVE_CUTOFF:
                continue
            pm = [s for s in loc.get("sensors", []) if s.get("parameter", {}).get("id") == PM25]
            if not pm:
                continue
            co = loc.get("coordinates") or {}
            if co.get("latitude") is None:
                continue
            d = hav(lat, lon, co["latitude"], co["longitude"])
            out.append({"dist": d, "loc_id": loc["id"], "name": loc.get("name", "?"),
                        "sensor_id": pm[0]["id"], "last": dl[:10],
                        "lat": co["latitude"], "lon": co["longitude"]})
        if len(res) < 100:
            break
    out.sort(key=lambda x: x["dist"])
    return out


def completeness(sensor_id):
    r = get(f"/sensors/{sensor_id}/days", {"date_from": WIN_FROM, "date_to": WIN_TO, "limit": 400})
    time.sleep(1.2)
    if "error" in r:
        return None
    return sum(1 for d in r.get("results", []) if d.get("value") is not None)


print(f"Window {WIN_FROM}..{WIN_TO} ({WIN_DAYS}d) | live>= {LIVE_CUTOFF} | keep nearest >{MIN_PCT:.0f}%\n")
print(f"{'regime':<11} {'candidate':<28} {'chosen station':<32} {'sensor':>9} {'km':>5} {'days':>5} {'pct':>5} {'flag'}")
print("-" * 108)

rows = []
for regime, name, lat, lon in CANDIDATES:
    stns = live_stations(lat, lon)
    if not stns:
        print(f"{regime:<11} {name:<28} {'<no live pm25 <=25km>':<32} {'':>9} {'':>5} {'':>5} {'':>5} SUBSTITUTE")
        rows.append({"regime": regime, "candidate": name, "lat": lat, "lon": lon,
                     "n_live": 0, "flag": "SUBSTITUTE", "reason": "no live pm25 within 25km"})
        continue
    chosen, best = None, None
    for s in stns[:8]:
        n = completeness(s["sensor_id"])
        if n is None:
            continue
        pct = 100.0 * n / WIN_DAYS
        s2 = {**s, "days": n, "pct": pct}
        if best is None or pct > best["pct"]:
            best = s2
        if pct >= MIN_PCT:
            chosen = s2
            break
    pick = chosen or best
    flag = "OK" if pick and pick["pct"] >= MIN_PCT else "SPARSE"
    print(f"{regime:<11} {name:<28} {pick['name'][:31]:<32} {pick['sensor_id']:>9} "
          f"{pick['dist']:>5.1f} {pick['days']:>5} {pick['pct']:>4.0f}% {flag}")
    rows.append({"regime": regime, "candidate": name, "lat": lat, "lon": lon,
                 "n_live": len(stns), "station": pick["name"], "loc_id": pick["loc_id"],
                 "sensor_id": pick["sensor_id"], "station_lat": pick["lat"],
                 "station_lon": pick["lon"], "dist_km": round(pick["dist"], 1),
                 "days": pick["days"], "pct": round(pick["pct"], 1),
                 "last": pick["last"], "flag": flag})

print("\n=== SUMMARY BY REGIME ===")
from collections import defaultdict
byreg = defaultdict(list)
for r in rows:
    byreg[r["regime"]].append(r)
for reg in ["industrial", "coal", "biomass", "dust", "clean"]:
    ok = sum(1 for r in byreg[reg] if r.get("flag") == "OK")
    print(f"  {reg:<11} {ok}/{len(byreg[reg])} OK (>{MIN_PCT:.0f}% coverage)")

with open("analysis/_recon_stations_result.json", "w") as f:
    json.dump(rows, f, indent=2)
print("\nwrote analysis/_recon_stations_result.json")
