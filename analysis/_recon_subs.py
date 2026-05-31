"""Step A substitution recon — evaluate replacement candidates for the 10
locations that lacked a live PM2.5 station with >50% in-window coverage.
Same method as _recon_stations.py. Throwaway recon.
"""
import os, sys, time, json, math, urllib.parse, urllib.request

API = "https://api.openaq.org/v3"
KEY = os.environ.get("OPENAQ_API_KEY")
PM25 = 2
WIN_FROM, WIN_TO, WIN_DAYS = "2025-11-01", "2026-05-01", 181
LIVE_CUTOFF, MIN_PCT = "2026-04-01", 50.0
if not KEY:
    print("FATAL: no key"); sys.exit(1)

# Substitution pool — more than needed per regime; pick best passers.
POOL = [
    ("industrial", "Dhaka, BD",        23.8103, 90.4125),
    ("industrial", "Kolkata, IN",      22.5726, 88.3639),
    ("industrial", "Ulaanbaatar, MN",  47.8864, 106.9057),
    ("coal",       "Korba, IN",        22.3595, 82.7501),
    ("coal",       "Rybnik (Silesia), PL", 50.0972, 18.5463),
    ("coal",       "Ostrava, CZ",      49.8209, 18.2625),
    ("coal",       "Dhanbad, IN",      23.7957, 86.4304),
    ("coal",       "Nagpur (Koradi), IN", 21.1458, 79.0882),
    ("biomass",    "Chiang Mai, TH",   18.7883, 98.9853),
    ("biomass",    "Palangkaraya, ID", -2.2096, 113.9108),
    ("dust",       "Jaipur, IN",       26.9124, 75.7873),
    ("dust",       "Kuwait City, KW",  29.3759, 47.9774),
    ("dust",       "Doha, QA",         25.2854, 51.5310),
    ("dust",       "El Paso TX, US",   31.7619, -106.4850),
    ("dust",       "Tashkent, UZ",     41.2995, 69.2401),
    ("clean",      "Bergen, NO",       60.3913, 5.3221),
    ("clean",      "Invercargill, NZ", -46.4132, 168.3538),
    ("clean",      "Hilo HI, US",      19.7297, -155.0900),
    ("clean",      "Nelson, NZ",       -41.2706, 173.2840),
]


def get(path, params):
    url = f"{API}{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"X-API-Key": KEY})
    for _ in range(5):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(10); continue
            return {"error": f"HTTP {e.code}"}
        except Exception:
            time.sleep(3)
    return {"error": "retries"}


def hav(a, b, c, d):
    p = math.radians; dlat, dlon = p(c-a), p(d-b)
    x = math.sin(dlat/2)**2 + math.cos(p(a))*math.cos(p(c))*math.sin(dlon/2)**2
    return 2*6371*math.asin(math.sqrt(x))


def live_stations(lat, lon):
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
            co = loc.get("coordinates") or {}
            if not pm or co.get("latitude") is None:
                continue
            out.append({"dist": hav(lat, lon, co["latitude"], co["longitude"]),
                        "loc_id": loc["id"], "name": loc.get("name", "?"),
                        "sensor_id": pm[0]["id"], "last": dl[:10],
                        "lat": co["latitude"], "lon": co["longitude"]})
        if len(res) < 100:
            break
    out.sort(key=lambda x: x["dist"])
    return out


def completeness(sid):
    r = get(f"/sensors/{sid}/days", {"date_from": WIN_FROM, "date_to": WIN_TO, "limit": 400})
    time.sleep(1.2)
    if "error" in r:
        return None
    return sum(1 for d in r.get("results", []) if d.get("value") is not None)


print(f"{'regime':<11} {'sub candidate':<22} {'chosen station':<30} {'sensor':>9} {'km':>5} {'days':>5} {'pct':>5} flag")
print("-"*100)
rows = []
for regime, name, lat, lon in POOL:
    stns = live_stations(lat, lon)
    if not stns:
        print(f"{regime:<11} {name:<22} {'<no live pm25 <=25km>':<30}")
        rows.append({"regime": regime, "candidate": name, "lat": lat, "lon": lon, "flag": "FAIL"})
        continue
    chosen, best = None, None
    for s in stns[:8]:
        n = completeness(s["sensor_id"])
        if n is None:
            continue
        pct = 100.0*n/WIN_DAYS
        s2 = {**s, "days": n, "pct": pct}
        if best is None or pct > best["pct"]:
            best = s2
        if pct >= MIN_PCT:
            chosen = s2; break
    pick = chosen or best
    flag = "OK" if pick and pick["pct"] >= MIN_PCT else "SPARSE"
    print(f"{regime:<11} {name:<22} {pick['name'][:29]:<30} {pick['sensor_id']:>9} "
          f"{pick['dist']:>5.1f} {pick['days']:>5} {pick['pct']:>4.0f}% {flag}")
    rows.append({"regime": regime, "candidate": name, "lat": lat, "lon": lon,
                 "n_live": len(stns), "station": pick["name"], "loc_id": pick["loc_id"],
                 "sensor_id": pick["sensor_id"], "station_lat": pick["lat"],
                 "station_lon": pick["lon"], "dist_km": round(pick["dist"], 1),
                 "days": pick["days"], "pct": round(pick["pct"], 1),
                 "last": pick["last"], "flag": flag})
with open("analysis/_recon_subs_result.json", "w") as f:
    json.dump(rows, f, indent=2)
print("\nwrote analysis/_recon_subs_result.json")
