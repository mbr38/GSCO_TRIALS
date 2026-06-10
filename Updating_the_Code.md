# Updating the Code — GSCO Maintenance Guide

**Date:** 10 June 2026
**Audience:** The GSCO team member responsible for keeping the tool relevant over time. **No prior knowledge of the codebase is assumed.** This guide tells you exactly which files to open, what to change, and how often.

---

## How to read this guide

The tool reads most of its data **live** from Google Earth Engine every time it runs, so the majority of it never needs manual updating. A handful of things, however, **do** drift out of date and need a human to refresh them. Those are listed below, ordered by how important and how frequent they are.

For each item you get: **where it lives** (the file), **what it looks like** (so you can find it), **when to change it**, and **how**.

> **Golden rules**
> 1. **Never edit anything in the `docs/` folder** — those are the authoritative specifications. This guide only ever touches code/data files.
> 2. **Change one thing, then run the tests** (`pytest` from the project folder). If tests fail, undo your change.
> 3. **When you change a dataset version or a stored data file, write down the date and the old value** in your commit message, so it can be traced.
> 4. **Editing a file means opening it in a text editor, changing the specific line, and saving.** Line numbers below are approximate — search for the quoted text to find the exact spot, because line numbers shift as the code changes.

---

##  The short version — what actually needs doing

If you only remember five things:

| # | Task | File | How often |
|---|------|------|-----------|
| 1 | Refresh the **climatology fallback data** | `demo/climatology.json` (via a tool) | **Once a year** |
| 2 | Bump the **Hansen forest-loss dataset** to the new annual version | `engine/nature.py` | **Once a year** |
| 3 | Upload & point to the new **ODIAC CO₂** vintage | `engine/ghg.py` | **When NASA/NIES publishes one** |
| 4 | Refresh the **KBA biodiversity** dataset snapshot | `engine/nature.py` | **~Every 6 months** |
| 5 | Make sure the **Earth Engine project** credential is set | environment (not a file) | **Once per machine** |

Everything else below is "review occasionally," not "must do on a schedule."

---

## 1. The Earth Engine credential (one-time setup, per machine)

The tool cannot fetch any satellite data without a Google Earth Engine project. This is **not stored in the code** — it's an environment variable, set once on each machine that runs the tool.

- **What it is:** a setting called `EE_PROJECT_ID`. The current project is **`supply-chain-observatory`**.
- **Where the tool reads it:** `utils/ee_init.py` (around line 28, the line `os.environ.get("EE_PROJECT_ID")`).
- **How to set it** (run once in a terminal, then restart the app):
  ```bash
  export EE_PROJECT_ID=supply-chain-observatory
  earthengine authenticate
  ```
- **When it needs attention:** only if the Google Cloud project changes, or on a brand-new computer. If the app shows "Earth Engine project ID not set," this is why.

> **Note:** This is the **only** credential needed to run the tool **locally** (on your own laptop). (You may see mentions of OpenAQ or Earthdata/Earthaccess in old research notes — those were for one-off validation experiments and are **not** part of the running tool. You do not need API keys for them.)
>
> The **hosted website** (the public `streamlit.app` link) authenticates a different way — through a *service account* instead of a personal Google login, because no human is sitting at the server to log in. See **§8 "The live website"** for what that is, why it exists, and how people access the site.

---

## 2. The climatology fallback data — refresh annually 

**What it is:** When the tool screens a site whose surroundings can't be measured (for example a coastal site whose comparison ring falls mostly over the ocean), it falls back to a stored **per-country average and spread** for each indicator. That stored table is a file. It is built from the last 3 years of satellite data, so it slowly goes stale.

- **The file:** `demo/climatology.json`
- **How to recognise it's due:** open the file and look at the very top (`_meta` section). Today it reads:
  - `"vintage": "2026"`
  - `"source_window": "2023-01-01/2025-12-31"` (a rolling 3-year window)
  - `"country_count": 267`
- **When to refresh:** **once a year.** Each year, slide the 3-year window forward by one year (drop the oldest year, add the newest).
- **How to refresh:** there is a dedicated tool. From the project folder, with the Earth Engine credential set:

  ```bash
  # Example for the end-of-2026 refresh (window becomes 2024–2026):
  EE_PROJECT_ID=supply-chain-observatory python tools/regen_climatology_fixtures.py \
      --vintage 2027 \
      --window-start 2024-01-01 \
      --window-end 2026-12-31 \
      --out demo/climatology.NEW.json
  ```

  Then **review** `demo/climatology.NEW.json` (check `_meta` shows the new window and `"complete": true`), and if it looks right, replace the old file with it (rename `climatology.NEW.json` → `climatology.json`).

  - The run takes roughly 30–60 minutes and talks to Earth Engine for all ~250 countries.
  - If it times out, add `--export` to run it as background jobs to Google Drive instead, then re-assemble — but for a normal refresh the command above is enough.
  - If it stops partway, re-run the same command with `--resume` added and it will skip the indicators it already finished.

- **What happens if you skip it:** the fallback numbers gradually reflect older conditions. The tool still records which `vintage` it used in every result's provenance, so nothing breaks silently — but the fallback becomes less representative over time.

---

## 3. Satellite/dataset versions inside the engine — review with each provider release ⭐

The tool names specific Earth Engine datasets. **Most update themselves** (Google keeps appending new days to Sentinel-5P, CAMS, Dynamic World, MODIS, VIIRS, ERA5 — you do nothing). But a few datasets publish as **dated, versioned editions**, and the tool is pinned to a specific edition that you must bump by hand when a newer one appears.

### 3a. Hansen Global Forest Change — bump annually ⭐
- **File:** `engine/nature.py` (around line 233).
- **Looks like:** `asset_id="UMD/hansen/global_forest_change_2023_v1_11",`
- **What to do:** when the University of Maryland publishes the next annual version (e.g. `global_forest_change_2024_v1_12`), change the version string in that line to match.
- **When:** roughly once a year, after the new version lands in the Earth Engine catalog.

### 3b. ODIAC CO₂ inventory — when a new vintage is published ⭐
- **Files:** `engine/ghg.py` — the dataset location (around line 241, `"projects/supply-chain-observatory/assets/odiac"`) and its coverage window (around line 260, `coverage_window=("2020-01-01", "2023-12-31")`).
- **Background:** ODIAC is **not** a public Earth Engine dataset. It is downloaded from its publisher and **uploaded into the GSCO Earth Engine project** by hand. It also lags real time by 2+ years, which is why CO₂ is shown only as background context, never as a live score.
- **What to do when a new ODIAC year is released:** (1) upload the new annual data into the GSCO Earth Engine assets, then (2) update the `coverage_window` line so its end date matches the newest year now available.

### 3c. KBA (Key Biodiversity Areas) — refresh the snapshot ~every 6 months ⭐
- **File:** `engine/nature.py` (around lines 115–116).
- **Looks like:** `"projects/supply-chain-observatory/assets/KBAsGlobal_2026_March_01_POL"`
- **Background:** like ODIAC, this is a dated snapshot uploaded into the GSCO project. The KBA database is revised about twice a year.
- **What to do:** when a newer KBA snapshot is uploaded, update this string to point at it.

### 3d. The "self-updating" datasets (no action needed, just monitor)
These keep flowing automatically; you only act if a provider **deprecates** one:
Sentinel-5P air pollutants (`COPERNICUS/S5P/...` in `engine/air.py` and `engine/ghg.py`), CAMS PM₂.₅/PM₁₀ (`ECMWF/CAMS/NRT`), MODIS AOD and NDVI (`MODIS/061/...`), Dynamic World land cover (`GOOGLE/DYNAMICWORLD/V1` in `engine/nature.py`), VIIRS night-lights (`NASA/VIIRS/002/VNP46A2`), ERA5 wind, and the GAUL country boundaries (`FAO/GAUL/2015/...`).
- **How to monitor:** Google publishes a dataset-status page (search "Earth Engine dataset status"). If a dataset there is marked deprecated, its replacement's ID must be swapped into the relevant config line. This is rare.

---

## 4. The "earliest date" floor — review if the satellite archive changes

- **File:** `engine/constants.py` (around line 1133).
- **Looks like:** `EARLIEST_SCREENING_DATE: str = "2019-01-01"`
- **What it is:** the oldest date a user is allowed to screen. It's set to early 2019 because that's when the Sentinel-5P air-quality archive became reliable.
- **When to change:** only if the underlying archives change their start — for example if an older backfill becomes available. Rare.

---

## 5. The tunable thresholds — review during v1.x calibration

The file `engine/constants.py` holds **every** adjustable number the engine uses (it is deliberately the *only* place numbers like this live). Many are locked methodology and should not be touched. A subset are marked **"first-pass"** — sensible starting values that are expected to be **calibrated** against real-world evidence during v1.x.

**How to tell which is which:** open `engine/constants.py` and look for the comment blocks that begin with `# @parameter`. Each one states a `tier:` (e.g. `first-pass`), a plain-language `rationale:`, the `source:` document, and when it was `last_reviewed:`. A companion file, `engine/parameter_registry.py`, lists these tunables in one place.

**The main first-pass values likely to be revisited** (all in `engine/constants.py`, find by name):

| Constant (search for this name) | Current | Controls |
|---|---|---|
| `VIIRS_FLARING_ABS_THRESHOLD_NW` | 100 | Brightness above which a VIIRS pixel counts as a flare/heavy source |
| `VIIRS_FLARING_SATURATION_FRAC` | 0.10 | Share of bright pixels that maxes out the GHG flaring score |
| `CONVERSION_SATURATION_PCT` | 0.10 | Habitat loss (as % of the area) that counts as "fully concerning" |
| `HANSEN_LOSS_RATIO_THRESHOLD` | 2.0 | How much higher surrounding forest loss must be to flag "this is regional, not the supplier" |
| `KBA_DISTANCE_DECAY_KM` | 10.0 | How fast biodiversity concern falls off with distance from a protected area |
| `WIND_SPEED_LOW_MIN_MS` | 3.5 | Wind speed above which a pollutant plume is treated as "blown in from elsewhere" |
| `HABITAT_BASELINE_YEARS` | 5 | How many years back the habitat-change comparison looks |
| `HANSEN_LOOKBACK_YEARS` | 5 | The window for the regional-forest-loss check |

> **Do not change these casually.** They affect scores everywhere. Change them only as part of a deliberate calibration exercise, ideally one constant at a time, re-running the tests afterward. The authority for *which* of these to calibrate and how is `docs/Indicators_Audit_and_v1x_Roadmap.md`. **Numbers prescribed by the specs** (the traffic-light cut-points, the 2σ anomaly gate, the `k=3` normalisation constant) must **not** be changed — those are fixed methodology.

---

## 6. Software version pins — do not bump without testing

- **File:** `requirements.txt`
- **The fragile pins** (and why they exist):
  - `setuptools>=68,<81` — newer setuptools removes a module the mapping library needs.
  - `ipython>=8,<9` — the mapping library uses the older IPython interface.
  - `geemap[extra]==0.34.4` and `folium>=0.16,<0.18` — a known-compatible pair; mismatching them breaks the maps.
- **Rule:** **do not raise these version limits** unless you fully re-test the geospatial stack end-to-end on Python 3.11. They are pinned precisely because newer versions have silently broken the maps before. If something needs a newer library, treat it as a deliberate upgrade project, not a quick edit.

---

## 7. Maintenance calendar at a glance

| When | Do this |
|------|---------|
| **Once per machine** | Set the `EE_PROJECT_ID` Earth Engine credential (§1). |
| **Every ~6 months** | Update the KBA biodiversity snapshot if a newer one exists (§3c). |
| **Once a year** | Refresh `demo/climatology.json` (slide the 3-year window) (§2). |
| **Once a year** | Bump the Hansen forest-loss dataset version (§3a). |
| **When the provider publishes** | Upload + repoint the new ODIAC CO₂ vintage (§3b). |
| **Occasionally / on alert** | Check the Earth Engine dataset-status page for deprecations (§3d); review the "first-pass" thresholds during v1.x calibration (§5). |
| **Only as a deliberate project** | Touch `requirements.txt` version pins (§6); change the earliest-date floor (§4). |
| **As needed (the hosted site)** | Share the link + password with a new user, change the password, or replace the service-account key (§8). The site re-deploys itself whenever you push to `main`. |

---

## 8. The live website (Streamlit Cloud) — the service account and how to reach it

Everything above is about running the tool **on your own computer**. There is also a **hosted version** — a public web link anyone you invite can open in a browser, with nothing to install. This section explains how it works, **why we created a "service account,"** and **how to give someone access.**

### Where it lives

- **The site:** <https://digitalauditing-gsco.streamlit.app/>
- **The host:** [Streamlit Community Cloud](https://share.streamlit.io) — a free hosting service for Streamlit apps.
- **What it runs:** the exact same code as this repository (`mbr38/GSCO_TRIALS`, `main` branch). Streamlit Cloud watches GitHub and **rebuilds the site automatically every time code is pushed to `main`.** So "deploying an update" just means pushing your change — there is no separate publish step.

### Why we created a service account 

On your laptop, a person proves they're allowed to use Earth Engine by running `earthengine authenticate` and logging in with their Google account in a browser (that's §1). **On a server, that doesn't work** — there's no browser and no person sitting there to log in, and we should never bake one employee's personal Google login into a public website.

The solution is a **service account**: a special, non-human Google account that *belongs to the project itself* and logs in automatically using a key file instead of a person. We created one in the `supply-chain-observatory` Google Cloud project and gave it two permissions ("roles"):

- **Earth Engine Resource Admin** — lets it use Earth Engine's data.
- **Service Usage Consumer** — lets it call the project's services at all.

That service account is what allows the hosted website to run screenings for visitors **without anyone logging in**. Creating and using it adds **no cost** (Earth Engine is free on the project's non-commercial tier; the account and the permissions themselves are free).

### The settings the website needs ("secrets")

The website needs a few private values that are deliberately **kept out of the code and out of GitHub** (so they never leak). They live in the Streamlit Cloud dashboard, under **Settings → Secrets**, and are pasted in as text:

| Secret | What it is |
|---|---|
| `EE_PROJECT_ID` | The Earth Engine project name (`supply-chain-observatory`). |
| `EE_SERVICE_ACCOUNT_JSON` | The service account's key — the whole key file, pasted in as one block. **This is the sensitive one; treat it like a password.** |
| `APP_PASSWORD` | The password visitors must type to enter the site (see below). |

The code that reads these is `utils/ee_init.py` (the service account) and `utils/auth.py` (the password). Both are written so that **on a laptop, where these secrets are absent, the tool behaves exactly as it always has** — personal Google login, no password prompt. The hosted behaviour only switches on because those secrets are present on the server.

### How someone accesses the site 

The site is **password-protected**. Anyone who opens the link is asked for a password before they can see anything.

**To give a colleague access, send them two things:**

1. The link: <https://digitalauditing-gsco.streamlit.app/>
2. The password (the `APP_PASSWORD` value) — ideally sent separately from the link.

They open the link, type the password, and they're in. **No Google account, no Streamlit account, nothing to install.**

Two things to expect:

- **The first visit after a quiet period takes ~30 seconds** while the site "wakes up." This is normal for the free hosting tier; anyone can wake it just by opening the link.
- **Everyone shares the project's Earth Engine quota.** Each screening a visitor runs uses the same free allowance. The password is what keeps that limited to people you've actually invited — so **don't post the password publicly.**

### Looking after it

- **To change the password:** edit `APP_PASSWORD` in the Streamlit Cloud **Settings → Secrets** box and reboot the app from the dashboard. (Do **not** put the password in the code.)
- **If the service account key is ever lost or leaked:** create a new key for the service account in Google Cloud (IAM & Admin → Service Accounts → the account → Keys → Add key → JSON), paste the new key into `EE_SERVICE_ACCOUNT_JSON`, and reboot. The old key can then be deleted.
- **If the site fails to start** with a permission error mentioning Earth Engine: the service account's two roles (above) may need re-granting, or a newly granted permission may still be propagating (give it a few minutes).
- **You never deploy by hand** — pushing to `main` on GitHub is the deploy.

### ⚠️ If you change the code: four things that behave differently on the server

The hosted site runs on a **fresh Linux machine with freshly installed libraries**, which is *not* identical to a laptop where things were installed gradually over time. Four traps caught us setting this up; if you edit the code, keep them in mind. **The danger with all four is that the code still works perfectly on your laptop, so the breakage only shows up after you push.**

1. **Adding a new map? You must write `ee_initialize=False`.** Every `geemap.Map(...)` call in the code passes `ee_initialize=False` (search the code to see the pattern). This tells the mapping library *not* to log in to Earth Engine by itself — our own code (`utils/ee_init.py`) already did that. If you add a new map and leave this off, **the map will work on your laptop but crash on the live site** with an error about `ee.data._credentials`. Always copy the existing pattern, including that argument.

2. **Don't pin `earthengine-api` to an old version.** In `requirements.txt`, the mapping library (`geemap`) requires `earthengine-api` version **1.0.0 or newer**. A previous attempt to pin it *lower* made the install impossible on the server. There's a comment in `requirements.txt` explaining this — leave that pin alone.

3. **`packages.txt` is fussy** (this file lists the system libraries the PDF export needs). Two rules: **(a)** one bare package name per line, **(b) no comment lines and no blank-line clutter** — the hosting platform tries to install *every* word in the file as a package, including words inside comments, so a `#` comment makes the whole install fail. Keep it to just the package names.

4. **The server must use Python 3.11.** This is chosen once, in the Streamlit Cloud dashboard under the app's **Advanced settings**, at the time the app is created. The whole library set is tuned for 3.11 (see §6); a newer Python breaks the maps. If the app ever has to be recreated from scratch, set Python to **3.11** before deploying.

> **The golden rule for any code change:** after the site redeploys, **open it and run one real screening end-to-end** (pick a site → Inspect → Results → try a PDF export). Passing tests on your laptop is necessary but not sufficient — the server's fresh library versions can differ, so always confirm on the live site too.

---

## 9. If you're unsure

- **A doc and the code disagree?** The `docs/` files are authoritative — but **do not edit them**; flag the mismatch to a developer.
- **For any indicator/threshold decision**, `docs/Indicators_Audit_and_v1x_Roadmap.md` is the master v1.x authority.
- **After any change**, run `pytest` from the project folder. Green tests are your safety net.
- **When in doubt, change nothing and ask.** Most of this tool updates itself; the manual items above are the rare exceptions, and each one is traceable through the provenance the engine records.
