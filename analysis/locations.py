"""Shared definitions for the GHG ↔ ODIAC + OCO-2/OCO-3 validation analysis.

The 25 stratified validation locations (5 source-type regimes × 5), the
analysis windows, and the production AOI radius. Imported by the Part A
(ODIAC/CH4/VIIRS) and Part B (OCO XCO2) extraction scripts and the notebook.

LOCKED at Step B (30 May 2026, operator confirmation):
  - 25 locations kept as-is (rural sparsity is a documented finding).
  - CH4 + VIIRS window: 2025-06-01 → 2025-12-01 (production-style, recent).
  - ODIAC window: 2023 annual (latest vintage; ODIAC stops 2023).
  - OCO XCO2 window: 2025-06-01 → 2025-12-01 (aligned with CH4/VIIRS),
    25 km bbox (±0.25°), OCO-2 + OCO-3 combined, good-quality only.

See docs/ghg_odiac_validation.md §2 and the project brief.
"""
import os

# (regime, location, lat, lon)
LOCATIONS: list[tuple[str, str, float, float]] = [
    # Urban CO2-dominant — CH4 low, VIIRS high, ODIAC high, XCO2 elevated
    ("Urban",    "London",         51.5074,  -0.1278),
    ("Urban",    "Mexico City",    19.4326,  -99.1332),
    ("Urban",    "Mumbai",         19.0760,   72.8777),
    ("Urban",    "Lagos",           6.5244,    3.3792),
    ("Urban",    "Seoul",          37.5665,  126.9780),
    # Oil/gas CH4-dominant — CH4 high, VIIRS mod-high, ODIAC moderate
    ("Oil/Gas",  "Permian Basin",  31.9000, -102.1000),
    ("Oil/Gas",  "Bakken",         47.8000, -103.0000),
    ("Oil/Gas",  "Hassi Messaoud", 31.6800,    6.0700),
    ("Oil/Gas",  "Tengiz",         46.1300,   53.5000),
    ("Oil/Gas",  "Comodoro",      -45.8645,  -67.4969),  # existing engine seed
    # Coal-fired power — CH4 moderate, VIIRS high, ODIAC high, XCO2 high
    ("Coal",     "Belchatow",      51.2667,   19.3300),
    ("Coal",     "Tuoketuo",       40.2700,  111.2000),
    ("Coal",     "Vindhyachal",    24.1000,   82.6700),
    ("Coal",     "Mpumalanga",    -26.0500,   29.4500),
    ("Coal",     "Kendal",        -26.0800,   28.9700),
    # Landfills / waste — CH4 very high, VIIRS low-mod, ODIAC low (diagnostic)
    ("Landfill", "Sudokwon",       37.5800,  126.6200),
    ("Landfill", "Bordo Poniente", 19.4600,  -99.0200),
    ("Landfill", "Apex NV",        36.3000, -114.9300),
    ("Landfill", "Puente Hills",   34.0200, -118.0000),
    ("Landfill", "Olusosun",        6.5800,    3.3700),
    # Rural / clean — all-low
    ("Rural",    "Patagonia",     -46.0000,  -69.0000),
    ("Rural",    "C. Sahara",      23.0000,   12.0000),
    ("Rural",    "C. Australia",  -24.5000,  131.0000),
    ("Rural",    "Greenland Coast",69.2000,  -51.1000),
    ("Rural",    "Siberian Taiga", 62.0000,  100.0000),
]

RADIUS_KM: float = 5.0          # production screening radius
WINDOW_NOW = ("2025-06-01", "2025-12-01")   # CH4 + VIIRS + OCO XCO2
WINDOW_ODIAC = ("2023-01-01", "2023-12-31")  # ODIAC latest annual vintage
OCO_BBOX_HALFWIDTH_DEG: float = 0.25         # ±0.25° ≈ 25 km box

# Earthdata CMR concept IDs (latest vintages confirmed in Step A recon)
OCO2_CONCEPT_ID = "C2912085112-GES_DISC"  # OCO2_L2_Lite_FP v11.2r
OCO3_CONCEPT_ID = "C2910086168-GES_DISC"  # OCO3_L2_Lite_FP v11r

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "ghg_odiac_validation.csv")
