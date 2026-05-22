# GSCO Environmental Decision-Support Demo

A Streamlit demo for the GSCO environmental monitoring tool. Built from
`PLFS_v4.md` and `Wireframes_All_v4.md`.

## Current scope

- ✅ **P-01 Landing** — user-type selection.
- ✅ **P-02 Scope set-up** — placeholder with geemap test (no EE).
- ⏳ Everything else (P-03 through P-11) — later iterations.

## Required setup

This demo uses pinned versions of geemap, setuptools, and ipython
because the latest releases drift apart and break each other. The exact pins
are in `requirements.txt`.

### Python version

**Use Python 3.11.** Python 3.12 dropped `distutils` and changed `setuptools`
defaults, which causes problems with the geospatial stack. Python 3.11 is the
sweet spot.

If you have multiple Python versions installed, check:

```bash
python3 --version
```

If it shows 3.12 or newer, install 3.11 via Homebrew:

```bash
brew install python@3.11
```

Then use `python3.11` (not `python3`) when creating the venv.

### System dependencies

PDF export on Reports (P-11) uses [weasyprint](https://weasyprint.org/),
which loads Pango, Cairo, and GLib at render time. Skipping this step
still lets the rest of the app run — the PDF export surfaces a friendly
install-instruction banner on first use (M-P11-FIX).

#### macOS

```bash
brew install pango cairo glib
```

If Generate PDF then fails with `cannot load library
'libgobject-2.0-0'`, the dyld search path doesn't include Homebrew's
lib directory. Add to `~/.zshrc`:

```bash
export DYLD_FALLBACK_LIBRARY_PATH=$(brew --prefix)/lib:$DYLD_FALLBACK_LIBRARY_PATH
```

Apply with `source ~/.zshrc`, then restart Streamlit.

#### Linux (Debian / Ubuntu)

```bash
apt-get install libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libglib2.0-0
```

Streamlit Cloud / Docker deployments: add the `apt-get` line to the
image's system-dependency layer.

#### Windows

See weasyprint's [Windows installation guide](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows).

## Quick start — fresh install from zero

If you've previously installed in a different venv, delete that venv first:

```bash
# Inside the project folder:
rm -rf .venv
```

### 1. Create the venv with Python 3.11

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

Confirm the venv uses Python 3.11:

```bash
python --version
# Should say: Python 3.11.x
```

### 2. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Takes 3–5 minutes. If you see any red errors, paste them and ask — don't proceed.

### 3. Verify the install

```bash
python -c "import leafmap.foliumap; import geemap.foliumap; print('OK')"
```

Should print `OK`. If it errors, the install failed silently.

### 4. Authenticate Earth Engine (one-off)

```bash
earthengine authenticate
```

If you get an SSL error, run:

```bash
/Applications/Python\ 3.11/Install\ Certificates.command
```

Then retry.

### 5. Set your Earth Engine project ID

Find your project ID at <https://console.cloud.google.com/>. If you don't have
one, create one at <https://console.cloud.google.com/projectcreate> and enable
the Earth Engine API at <https://console.cloud.google.com/apis/library/earthengine.googleapis.com>.

```bash
export EE_PROJECT_ID=your-project-id-here
```

To make it permanent:

```bash
echo 'export EE_PROJECT_ID=your-project-id-here' >> ~/.zprofile
```

Then close and reopen the terminal, or run `source ~/.zprofile`.

### 6. Run the app

```bash
streamlit run gsco_app.py
```

Browser opens at `http://localhost:8501`. (`gsco_app.py` is the Streamlit
entry point — it registers every page via `st.Page` / `st.navigation`
so the sidebar shows explicit titles like "Landing" instead of
filename-derived ones like "app". `app.py` itself is still the
landing page; it's just no longer run directly.)

## What to expect

1. Landing page with two role cards.
2. Click a role → routed to the scope-setup page.
3. Scope-setup shows a persistent header and a satellite map of Cambridge.

## Project structure

```
gsco-demo/
├── gsco_app.py                     # Streamlit entry point — registers pages via st.Page/st.navigation
├── app.py                          # P-01 Landing (rendered as the default page)
├── pages/
│   ├── 02_Scope_Setup.py           # P-02 + geemap test
│   └── 99_engine_scratch.py        # Dev scratch — engine debug UI (delete when P-05 lands)
├── utils/
│   ├── __init__.py
│   ├── state.py                    # Session state
│   └── ee_init.py                  # Cached EE initialiser
├── engine/                         # Indicator engine (M1+)
├── data/
├── tests/
├── requirements.txt
└── README.md
```

## Library strategy

- `geemap.foliumap` → all pages; call `require_earth_engine()` first.

## Common issues

| Symptom | Fix |
|---|---|
| `pkg_resources` not found | `pip install "setuptools<81"` |
| `No module named 'IPython.core.display'` | `pip install "ipython<9"` |
| `xyz_to_folium` not found | leafmap/geemap version drift — reinstall from `requirements.txt` |
| SSL `CERTIFICATE_VERIFY_FAILED` | `/Applications/Python\ 3.11/Install\ Certificates.command` |
| EE test page says "project ID not set" | Export `EE_PROJECT_ID` in the same terminal Streamlit runs from, then restart Streamlit |
| Port 8501 already in use | `streamlit run gsco_app.py --server.port 8502` |
