# GSCO Environmental Tool — Verbal Summary Templates (v1)

**Purpose.** Deterministic rule-based generator for the one-paragraph "verbal summary" rendered on P-05 (Screening — component C7), reused on P-06 in v1 and seeded into the report templates on P-11.

**Authority.** Built from `Indicators_Computation_v3.md` (sub-score names, formulas, weights), `Indicator_ID_Schema_v1.md` (canonical IDs), and `Wireframes_All_v4.md` Appendix C (the tertile thresholds used here are the same thresholds the traffic-light bands use, so the prose and the chip colour never disagree).

**Date.** 13 May 2026.

**Design principles.**
1. **Deterministic** — no LLM calls, no probabilistic reasoning. Same input → same output.
2. **Defensible** — never invents indicator values; never speculates about causes; never claims significance unless the slot provides a p-value or Z-statistic; never implies facility-level attribution.
3. **Auditable** — the template-selection logic is one short function; every rendered sentence traces back to a template ID and a slot-resolution rule.
4. **Aligned with the UI** — the priority and confidence bucketing matches Wireframes Appendix C.1–C.2 exactly. Tunable as `TRAFFIC_LIGHT_THRESHOLDS = (0.33, 0.66)` in code.

---

## 1. Bucketing

Single tertile-based bucketing function, applied to every 0–1 score the generator reads:

```python
def bucket(score):
    if score >= 0.66:    return "high"
    elif score >= 0.33:  return "moderate"
    else:                return "low"
```

A score of exactly 0.33 or 0.66 lands in the higher-severity band (matches Wireframes Appendix C.1).

The generator buckets:
- Each pillar's Follow-Up Priority Score
- Each pillar's Quality / Attribution Confidence Score
- The composite (cross-pillar) score
- The composite confidence (= min of the three pillar confidences per `Indicators_Computation_v3.md` §4)

---

## 2. Slot grammar

Every per-pillar template can use up to seven slots:

| Slot | Source | Example |
|---|---|---|
| `{pillar_label}` | constant per pillar | `"Air Pollution"` |
| `{dominant_indicator}` | dominant-contributor display name (§3) | `"NO₂"` |
| `{dominant_value}` | pillar-specific formatter (§4) | `"42 µmol m⁻²"` |
| `{dominant_z}` | pillar-specific formatter (§4) | `"2.3σ"` |
| `{dominant_direction}` | sign of `<id>.anomaly` — `"above"` / `"at"` / sometimes `None` | `"above"` |
| `{limiting_factor}` | lowest-scoring quality sub-component display name (§5) | `"weak retrieval quality for SO₂ at these concentrations"` |
| `{limiting_factor_score}` | numeric value of that limiting factor | `0.31` — **not rendered in prose**; carried in the CSV / JSON export only |

Some templates omit slots (low-priority templates have no dominant indicator; high-confidence templates have no limiting factor).

Formatting is applied by the rendering layer:
- Raw values use the display units from `Indicators_Computation_v3.md` §1.1 (µmol m⁻² for NO₂/SO₂/HCHO; mmol m⁻² for CO; DU for O₃; ppb for CH₄; µg m⁻³ for PM; t CO₂ yr⁻¹ for fossil CO₂; nW cm⁻² sr⁻¹ for VIIRS).
- Z-statistic: 1 decimal place + "σ".
- Scores: 2 decimal places.
- Hectares: integers below 100; 1 decimal between 100 and 1000; integers above.

---

## 3. Dominant-contributor lookup (per pillar)

The dominant contributor is the term with the largest `weight × sub_score` contribution to the pillar's Follow-Up Priority Score. **If the top contributor's share of the total is below 0.40, the fallback ("no single dominant driver") template fires instead.** The 0.40 threshold is tunable as `DOMINANT_CONTRIBUTOR_SHARE_THRESHOLD = 0.40`.

### 3.1 Air Pollution candidates

From `Air_Pollution_Proxy_Score` (Indicators_Computation §1.3):

| Term ID | Weight | Display name |
|---|---|---|
| `air.no2.score` | 0.30 | NO₂ |
| `air.so2.score` | 0.20 | SO₂ |
| `air.co.score` | 0.15 | CO |
| `air.hcho.score` | 0.15 | HCHO (formaldehyde) |
| `air.pm_or_aerosol` | 0.10 | PM₂.₅ / aerosols |
| `air.o3.score` | 0.10 | ozone (context) |

### 3.2 GHG candidates

From `Core_GHG_Audit_Support` v1-rescaled (Indicators_Computation §2.3):

| Term ID | Weight | Display name |
|---|---|---|
| `ghg.co2_context` | 0.39 | fossil CO₂ context (ODIAC) |
| `ghg.ch4_context_adjusted` | 0.28 | atmospheric methane |
| `ghg.combustion_proxy` | 0.22 | combustion proxy (NO₂ + CO) |
| `ghg.activity_score` | 0.11 | nighttime-light activity |

### 3.3 Nature/Land candidates

From `Nature_FollowUp_Priority` (Indicators_Computation §3.3), excluding the quality-attribution term:

| Term ID | Weight | Display name |
|---|---|---|
| `nature.biodiversity_exposure` | 0.30 | proximity to Key Biodiversity Areas |
| `nature.habitat.conversion_score` | 0.30 | habitat conversion |
| `nature.vegetation_condition` | 0.25 | vegetation condition |

Tie-break: descending natural weight, then alphabetical display name.

---

## 4. Pillar-specific `{dominant_value}` and `{dominant_z}` formatters

Air's dominant value is always a Z-comparable concentration. GHG and Nature are heterogeneous, so they need small renderer helpers.

### 4.1 Air Pollution

Direct read from the dominant indicator's `.site` (with unit conversion to the display unit), `.z`, and the sign of `.anomaly`. `{dominant_direction}` is always set ("above" or "at") — never None.

### 4.2 GHG helper

```python
def format_ghg_dominant(dominant_id, payload):
    if dominant_id == "ghg.co2_context":
        ratio = payload["ghg.co2.total"] / payload["ghg.co2.background_median"]
        return {
            "value":     f"{payload['ghg.co2.total']:,.0f} t CO₂ yr⁻¹",
            "z":         f"{ratio:.1f}× the regional median",
            "direction": "above",
        }
    elif dominant_id == "ghg.ch4_context_adjusted":
        return {
            "value":     f"{payload['ghg.ch4.site']:.0f} ppb",
            "z":         f"{payload['ghg.ch4.anomaly']:.2f} ppb above background",
            "direction": None,    # z field already names the comparison; renderer drops the trailing phrase
        }
    elif dominant_id == "ghg.combustion_proxy":
        return {
            "value":     f"score {payload['ghg.combustion_proxy']:.2f}",
            "z":         "combined NO₂ + CO signal",
            "direction": None,    # combined proxy has no anomaly comparison
        }
    elif dominant_id == "ghg.activity_score":
        return {
            "value":     f"median radiance {payload['ghg.viirs.site']:.1f} nW cm⁻² sr⁻¹",
            "z":         f"{payload['ghg.viirs.z']:.1f}σ above background",
            "direction": None,    # z field already names the comparison
        }
```

When `direction` is `None`, the renderer strips the trailing "{dominant_direction} background" phrase from the template so the sentence reads naturally.

### 4.3 Nature/Land helper

Nature templates don't use `{dominant_z}` or `{dominant_direction}` — habitat / biodiversity findings are absolute exposures, not anomalies relative to a background ring.

```python
def format_nature_dominant(dominant_id, payload):
    if dominant_id == "nature.biodiversity_exposure":
        if payload["nature.kba.overlap_pct"] > 0:
            return {"value": f"{payload['nature.kba.overlap_pct']:.0f}% of buffer overlaps a Key Biodiversity Area"}
        else:
            return {"value": f"nearest Key Biodiversity Area is {payload['nature.kba.dist_km']:.1f} km away"}
    elif dominant_id == "nature.habitat.conversion_score":
        loss_ha  = payload["nature.habitat.natural_loss_ha"]
        loss_pct = payload["nature.habitat.natural_loss_pct"]
        rate     = payload["nature.habitat.annualised_rate"]
        return {"value": f"{loss_ha:.1f} ha of natural cover lost — {loss_pct:.1f}% of buffer — {rate:.1f} ha yr⁻¹"}
    elif dominant_id == "nature.vegetation_condition":
        return {"value": f"NDVI {payload['nature.ndvi.anomaly']:+.2f} relative to background, with {payload['nature.low_ndvi.pct']:.0f}% of natural-cover pixels degraded"}
```

Em-dashes inside the habitat phrasing (rather than nested parens) keep the sentence readable.

---

## 5. Limiting-factor lookup (per pillar)

Picks `{limiting_factor}` — the lowest-scoring sub-component of the pillar's quality-attribution aggregate. Quality sub-scores are 0–1 where higher = better, so the limiting factor is the minimum.

### 5.1 Air Pollution

Air's quality side is the mean of per-indicator `.confidence` values across selected pollutants. The limiting factor is the **pollutant with the lowest individual confidence**:

| Lowest-confidence pollutant | Display name |
|---|---|
| NO₂ | low valid-pixel coverage for NO₂ in this buffer |
| SO₂ | weak retrieval quality for SO₂ at these concentrations |
| CO | low valid-pixel coverage for CO |
| HCHO | low valid-pixel coverage for HCHO |
| PM₂.₅ | the coarse spatial resolution of CAMS PM₂.₅ (~44 km) |
| O₃ | low valid-pixel coverage for O₃ |
| AAI | low valid-pixel coverage for absorbing aerosols |

### 5.2 GHG

From `GHG_Data_Quality_Attribution` v1-rescaled (Indicators_Computation §2.3):

| Sub-score | Weight | Display name |
|---|---|---|
| `Temporal_Coverage` | 0.30 | sparse temporal coverage over the analysis window |
| `Spatial_Resolution_Suitability` | 0.24 | the coarse spatial resolution of methane retrievals relative to the buffer |
| `Retrieval_or_Inventory_Quality` | 0.24 | weak retrieval quality flags |
| `Nearby_Source_Isolation` | 0.12 | background contamination from nearby industrial activity |

### 5.3 Nature/Land

From `Nature_Quality_Attribution` (Indicators_Computation §3.3):

| Sub-score | Weight | Display name |
|---|---|---|
| `Valid_Pixel_Coverage` | 0.20 | low valid-pixel coverage (cloud cover or no-data) |
| `Cloud_or_Observation_Quality` | 0.20 | high cloud contamination in Sentinel-2 observations |
| `DynamicWorld_Class_Confidence` | 0.20 | ambiguous land-cover classification (no dominant class) |
| `Seasonal_Comparability` | 0.15 | seasonal mismatch between the baseline and current composites |
| `Supplier_Spatial_Link` | 0.15 | the observed change is not concentrated near the supplier point |
| `External_Driver_Screening` | 0.10 | an external driver (fire, drought, or regional loss) appears to explain the change |

---

## 6. The 45 pillar templates

Three pillars × (9 main + 6 fallback) = 45 templates. Keyed by `(pillar, priority_bucket, confidence_bucket, dominant_path)`.

### 6.1 Air Pollution — 9 main templates

| Key | Template |
|---|---|
| (air, high, high, main) | Air pollution is elevated at this location, driven primarily by {dominant_indicator} ({dominant_value}, {dominant_z} {dominant_direction} background). Data quality is high. |
| (air, high, moderate, main) | Air pollution is elevated at this location, driven primarily by {dominant_indicator} ({dominant_value}, {dominant_z} {dominant_direction} background). Confidence is moderate — interpretation is limited by {limiting_factor}. |
| (air, high, low, main) | Air pollution may be elevated at this location based on {dominant_indicator} ({dominant_value}, {dominant_z} {dominant_direction} background), but data quality is poor — {limiting_factor} limits the reliability of this score. Investigate before acting. |
| (air, moderate, high, main) | Air pollution shows moderate elevation at this location, with {dominant_indicator} as the main contributor ({dominant_value}, {dominant_z} {dominant_direction} background). The signal is within typical regional variability. Data quality is high. |
| (air, moderate, moderate, main) | Air pollution shows moderate elevation at this location, with {dominant_indicator} contributing most ({dominant_value}, {dominant_z} {dominant_direction} background). Confidence is mixed — {limiting_factor} is a limiting factor. |
| (air, moderate, low, main) | A moderate air-pollution signal is present at this location, with {dominant_indicator} ({dominant_value}, {dominant_z} {dominant_direction} background) as the largest contributor, but data quality is poor — {limiting_factor} limits the reliability of this read. |
| (air, low, high, main) | Air pollution is at background levels across the monitored pollutants at this location. Data quality is high. |
| (air, low, moderate, main) | Air pollution appears at background levels across the monitored pollutants at this location. Confidence is moderate — {limiting_factor} is a limiting factor. |
| (air, low, low, main) | Air pollution appears at background levels across the monitored pollutants at this location, but data is sparse — {limiting_factor} limits the reliability of this conclusion. A 'low priority' read here should not be taken as a clear negative. |

### 6.2 Air Pollution — 6 fallback templates

| Key | Template |
|---|---|
| (air, high, high, fallback) | Air pollution is elevated at this location across multiple gases, with no single dominant driver. Data quality is high. |
| (air, high, moderate, fallback) | Air pollution is elevated at this location across multiple gases, with no single dominant driver. Confidence is moderate — interpretation is limited by {limiting_factor}. |
| (air, high, low, fallback) | Air pollution may be elevated at this location across multiple gases, but data quality is poor — {limiting_factor} limits the reliability of this score. Investigate before acting. |
| (air, moderate, high, fallback) | Air pollution shows moderate elevation across multiple gases at this location, with no single dominant driver. Data quality is high. |
| (air, moderate, moderate, fallback) | Air pollution shows moderate elevation across multiple gases at this location. Confidence is mixed — {limiting_factor} is a limiting factor. |
| (air, moderate, low, fallback) | A moderate air-pollution signal is present at this location across multiple gases, but data quality is poor — {limiting_factor} limits the reliability of this read. |

Low-priority cells have no fallback variant — when priority is low, there's no driver to attribute regardless of share.

### 6.3 GHG — 9 main templates

| Key | Template |
|---|---|
| (ghg, high, high, main) | Greenhouse gases are elevated at this location, driven primarily by {dominant_indicator} ({dominant_value}, {dominant_z} {dominant_direction} background). Data quality is high. |
| (ghg, high, moderate, main) | Greenhouse gases are elevated at this location, driven primarily by {dominant_indicator} ({dominant_value}, {dominant_z} {dominant_direction} background). Confidence is moderate — interpretation is limited by {limiting_factor}. |
| (ghg, high, low, main) | Greenhouse gases may be elevated at this location based on {dominant_indicator} ({dominant_value}, {dominant_z} {dominant_direction} background), but data quality is poor — {limiting_factor} limits the reliability of this score. Investigate before acting. |
| (ghg, moderate, high, main) | Greenhouse gases show moderate elevation at this location, with {dominant_indicator} as the main contributor ({dominant_value}, {dominant_z} {dominant_direction} background). The signal is within typical regional variability. Data quality is high. |
| (ghg, moderate, moderate, main) | Greenhouse gases show moderate elevation at this location, with {dominant_indicator} contributing most ({dominant_value}, {dominant_z} {dominant_direction} background). Confidence is mixed — {limiting_factor} is a limiting factor. |
| (ghg, moderate, low, main) | A moderate GHG signal is present at this location, with {dominant_indicator} ({dominant_value}, {dominant_z} {dominant_direction} background) as the largest contributor, but data quality is poor — {limiting_factor} limits the reliability of this read. |
| (ghg, low, high, main) | Greenhouse gases are at background levels across the monitored GHG indicators at this location. Data quality is high. |
| (ghg, low, moderate, main) | Greenhouse gases appear at background levels across the monitored indicators at this location. Confidence is moderate — {limiting_factor} is a limiting factor. |
| (ghg, low, low, main) | Greenhouse gases appear at background levels at this location, but data is sparse — {limiting_factor} limits the reliability of this conclusion. A 'low priority' read here should not be taken as a clear negative. |

### 6.4 GHG — 6 fallback templates

| Key | Template |
|---|---|
| (ghg, high, high, fallback) | Greenhouse gases are elevated at this location across multiple indicators, with no single dominant driver. Data quality is high. |
| (ghg, high, moderate, fallback) | Greenhouse gases are elevated at this location across multiple indicators, with no single dominant driver. Confidence is moderate — interpretation is limited by {limiting_factor}. |
| (ghg, high, low, fallback) | Greenhouse gases may be elevated at this location across multiple indicators, but data quality is poor — {limiting_factor} limits the reliability of this score. Investigate before acting. |
| (ghg, moderate, high, fallback) | Greenhouse gases show moderate elevation across multiple indicators at this location, with no single dominant driver. Data quality is high. |
| (ghg, moderate, moderate, fallback) | Greenhouse gases show moderate elevation across multiple indicators at this location. Confidence is mixed — {limiting_factor} is a limiting factor. |
| (ghg, moderate, low, fallback) | A moderate GHG signal is present at this location across multiple indicators, but data quality is poor — {limiting_factor} limits the reliability of this read. |

### 6.5 Nature/Land — 9 main templates

Nature templates use "exposure" instead of "elevation", "concern" instead of "driver", "at baseline" instead of "at background levels". `{dominant_z}` and `{dominant_direction}` are unused (the formatter for this pillar never emits them).

| Key | Template |
|---|---|
| (nature, high, high, main) | Nature/Land shows significant exposure at this location, with {dominant_indicator} as the main concern ({dominant_value}). Data quality is high. |
| (nature, high, moderate, main) | Nature/Land shows significant exposure at this location, with {dominant_indicator} as the main concern ({dominant_value}). Confidence is moderate — interpretation is limited by {limiting_factor}. |
| (nature, high, low, main) | Nature/Land exposure may be significant at this location based on {dominant_indicator} ({dominant_value}), but data quality is poor — {limiting_factor} limits the reliability of this score. Investigate before acting. |
| (nature, moderate, high, main) | Nature/Land shows moderate exposure at this location, with {dominant_indicator} as the main contributor ({dominant_value}). Data quality is high. |
| (nature, moderate, moderate, main) | Nature/Land shows moderate exposure at this location, with {dominant_indicator} contributing most ({dominant_value}). Confidence is mixed — {limiting_factor} is a limiting factor. |
| (nature, moderate, low, main) | A moderate Nature/Land exposure is present at this location, with {dominant_indicator} ({dominant_value}) as the largest contributor, but data quality is poor — {limiting_factor} limits the reliability of this read. |
| (nature, low, high, main) | Nature/Land is at baseline across the monitored land-cover indicators at this location. Data quality is high. |
| (nature, low, moderate, main) | Nature/Land appears at baseline across the monitored land-cover indicators at this location. Confidence is moderate — {limiting_factor} is a limiting factor. |
| (nature, low, low, main) | Nature/Land appears at baseline at this location, but data is sparse — {limiting_factor} limits the reliability of this conclusion. A 'low priority' read here should not be taken as a clear negative. |

### 6.6 Nature/Land — 6 fallback templates

| Key | Template |
|---|---|
| (nature, high, high, fallback) | Nature/Land shows significant exposure at this location across multiple aspects, with no single dominant concern. Data quality is high. |
| (nature, high, moderate, fallback) | Nature/Land shows significant exposure at this location across multiple aspects, with no single dominant concern. Confidence is moderate — interpretation is limited by {limiting_factor}. |
| (nature, high, low, fallback) | Nature/Land exposure may be significant at this location across multiple aspects, but data quality is poor — {limiting_factor} limits the reliability of this score. Investigate before acting. |
| (nature, moderate, high, fallback) | Nature/Land shows moderate exposure across multiple aspects at this location, with no single dominant concern. Data quality is high. |
| (nature, moderate, moderate, fallback) | Nature/Land shows moderate exposure across multiple aspects at this location. Confidence is mixed — {limiting_factor} is a limiting factor. |
| (nature, moderate, low, fallback) | A moderate Nature/Land exposure is present across multiple aspects at this location, but data quality is poor — {limiting_factor} limits the reliability of this read. |

---

## 7. The 15 overview templates

The first sentence of the verbal summary. Keyed by `(composite_shape, composite_confidence_bucket)`.

### 7.1 Shape helper

```python
def composite_shape(pillar_priority_buckets):
    high     = sum(1 for b in pillar_priority_buckets.values() if b == "high")
    moderate = sum(1 for b in pillar_priority_buckets.values() if b == "moderate")
    if   high == 3: return "3"
    elif high == 2: return "2"
    elif high == 1: return "1"
    elif moderate >= 1: return "M"
    else: return "0"
```

### 7.2 Pillar display names in the overview

| Pillar | Display |
|---|---|
| air | Air Pollution |
| ghg | GHG emissions |
| nature | Nature/Land |

Display order for the `{high_pillar_a}` / `{high_pillar_b}` slots is fixed (Air → GHG → Nature) regardless of which scored highest, so two summaries are visually comparable.

### 7.3 Moderate-pillar list phrase helper

```python
def moderate_pillar_list_phrase(moderate_pillars_ordered):
    n = len(moderate_pillars_ordered)
    if   n == 1: return f"Concern centres on {moderate_pillars_ordered[0]}"
    elif n == 2: return f"Concern centres on {moderate_pillars_ordered[0]} and {moderate_pillars_ordered[1]}"
    elif n == 3: return "Concern is spread across all three pillars"
```

### 7.4 The 15 overview templates

| Key | Template |
|---|---|
| (0, high) | All three pillars are at background levels (composite {composite_score}). Data quality is high. |
| (0, moderate) | All three pillars appear at background levels (composite {composite_score}). Composite confidence is moderate. |
| (0, low) | All three pillars appear at background levels (composite {composite_score}), but composite confidence is low — at least one pillar has significant data-quality limitations. Treat the 'all clear' read with caution. |
| (1, high) | Overall priority is {composite_bucket} (composite {composite_score}), driven by {high_pillar}. Data quality is high. |
| (1, moderate) | Overall priority is {composite_bucket} (composite {composite_score}), driven by {high_pillar}. Composite confidence is moderate. |
| (1, low) | Overall priority appears {composite_bucket} (composite {composite_score}), driven by {high_pillar}, but composite confidence is low — read the pillar detail before acting. |
| (2, high) | Overall priority is high (composite {composite_score}), with elevated signals in {high_pillar_a} and {high_pillar_b}. Data quality is high. |
| (2, moderate) | Overall priority is high (composite {composite_score}), with elevated signals in {high_pillar_a} and {high_pillar_b}. Composite confidence is moderate. |
| (2, low) | Overall priority appears high (composite {composite_score}), with elevated signals in {high_pillar_a} and {high_pillar_b}, but composite confidence is low — read the pillar detail before acting. |
| (3, high) | Overall priority is high across all three pillars (composite {composite_score}). Data quality is high. This is a clear flag for follow-up. |
| (3, moderate) | Overall priority is high across all three pillars (composite {composite_score}). Composite confidence is moderate. This is a clear flag for follow-up. |
| (3, low) | Overall priority appears high across all three pillars (composite {composite_score}), but composite confidence is low — read the pillar detail before acting. |
| (M, high) | Overall priority is moderate (composite {composite_score}). {moderate_pillar_list_phrase}. Data quality is high. |
| (M, moderate) | Overall priority is moderate (composite {composite_score}). {moderate_pillar_list_phrase}. Composite confidence is moderate. |
| (M, low) | Overall priority appears moderate (composite {composite_score}). {moderate_pillar_list_phrase}. Composite confidence is low — read the pillar detail before acting. |

---

## 8. The end-to-end generator

```python
def generate_verbal_summary(payload):
    # STEP 1 — bucket
    composite_priority   = bucket(payload["composite.overall_screening"])
    composite_confidence = bucket(payload["composite.confidence"])
    pillar_priority   = {p: bucket(payload[f"{p}.followup_priority"]) for p in PILLARS}
    pillar_confidence = {p: bucket(payload[CONFIDENCE_FIELD[p]])      for p in PILLARS}

    # STEP 2 — dominant contributor per pillar
    dominant = {}
    for p in PILLARS:
        contribs = {term: w * payload[term] for term, w in PILLAR_TERMS[p].items()}
        top_term, top_val = max(contribs.items(), key=lambda kv: kv[1])
        total = sum(contribs.values())
        share = top_val / total if total else 0
        if share >= DOMINANT_CONTRIBUTOR_SHARE_THRESHOLD:
            slots = PILLAR_FORMATTER[p](top_term, payload)
            dominant[p] = {"path": "main", "term": top_term, **slots,
                           "indicator_display": DISPLAY_NAME[top_term]}
        else:
            dominant[p] = {"path": "fallback"}

    # STEP 3 — limiting factor per pillar
    limiting = {p: pick_limiting_factor(p, payload) for p in PILLARS}

    # STEP 4 — per-pillar sentence
    pillar_sentence = {}
    for p in PILLARS:
        key = (p, pillar_priority[p], pillar_confidence[p], dominant[p]["path"])
        tmpl = TEMPLATES[key]
        s = render(tmpl, pillar=p, dominant=dominant[p], limiting=limiting[p])
        if dominant[p].get("direction") is None:
            s = strip_trailing_direction(s)
        pillar_sentence[p] = s

    # STEP 5 — overview
    shape = composite_shape(pillar_priority)
    overview_tmpl = OVERVIEW_TEMPLATES[(shape, composite_confidence)]
    high_pillars     = [DISPLAY_NAME_OVERVIEW[p] for p in PILLAR_ORDER if pillar_priority[p] == "high"]
    moderate_pillars = [DISPLAY_NAME_OVERVIEW[p] for p in PILLAR_ORDER if pillar_priority[p] == "moderate"]
    overview = render(overview_tmpl,
                      composite_score=f"{payload['composite.overall_screening']:.2f}",
                      composite_bucket=composite_priority,
                      high_pillar=high_pillars[0] if high_pillars else None,
                      high_pillar_a=high_pillars[0] if len(high_pillars) >= 2 else None,
                      high_pillar_b=high_pillars[1] if len(high_pillars) >= 2 else None,
                      moderate_pillar_list_phrase=moderate_pillar_list_phrase(moderate_pillars))

    # STEP 6 — compose
    return "\n\n".join([overview,
                        pillar_sentence["air"],
                        pillar_sentence["ghg"],
                        pillar_sentence["nature"]])
```

`PILLARS = ["air", "ghg", "nature"]` and `PILLAR_ORDER = ["air", "ghg", "nature"]` (the body sentences always render in this order regardless of priority).

The `strip_trailing_direction` helper removes the trailing ` {dominant_direction} background` phrase from the rendered string when the pillar formatter returned `direction=None`.

---

## 9. Worked end-to-end example

Fictional Po Valley supplier; composite moderate, Air high, GHG moderate, Nature low.

Inputs:

```
composite.overall_screening = 0.58 → moderate
composite.confidence        = 0.51 → moderate

air.audit_followup_priority    = 0.72 (high), confidence 0.41 (moderate)
  dominant: NO₂ (share 0.55)
  air.no2.site = 4.2e-5 mol m⁻² → "42 µmol m⁻²"; z 2.3; direction "above"
  lowest air sub-confidence: SO₂ (0.31) → "weak retrieval quality for SO₂ at these concentrations"

ghg.audit_followup_priority    = 0.48 (moderate), confidence 0.62 (moderate)
  dominant: atmospheric methane (share 0.49)
  ghg.ch4.site 1888 ppb; ghg.ch4.anomaly 0.42 ppb; direction None
  lowest ghg quality sub-score: Spatial_Resolution_Suitability (0.34) → "the coarse spatial resolution of methane retrievals relative to the buffer"

nature.followup_priority       = 0.21 (low), confidence 0.71 (high)
```

Output:

> Overall priority is moderate (composite 0.58), driven by Air Pollution. Composite confidence is moderate.
>
> Air pollution is elevated at this location, driven primarily by NO₂ (42 µmol m⁻², 2.3σ above background). Confidence is moderate — interpretation is limited by weak retrieval quality for SO₂ at these concentrations.
>
> Greenhouse gases show moderate elevation at this location, with atmospheric methane contributing most (1888 ppb, 0.42 ppb above background). Confidence is mixed — the coarse spatial resolution of methane retrievals relative to the buffer is a limiting factor.
>
> Nature/Land is at baseline across the monitored land-cover indicators at this location. Data quality is high.

---

## 10. Future v1.x extensions

- **Trend-mode template grid.** P-06 currently reuses the screening templates. A v1.x grid would describe time-evolution: "Air pollution has worsened over the last 24 months, with NO₂ trending up at +1.2 × 10⁻⁵ mol m⁻² yr⁻¹ (p=0.03)." Same 9-cell grid per pillar; new templates.
- **Sub-aggregate sentences.** Currently the verbal summary only names the top pillar-aggregate contributor (e.g. "habitat conversion"). A v1.x extension could drill one level deeper for high-priority cases ("habitat conversion — specifically 8.2 ha of natural-to-built transition").
- **Sector-aware framing.** Once `node.sector` is available, the overview line could note when a finding is sector-typical vs surprising: "This is the expected pattern for a cement plant; the anomaly is the elevated CH₄, not the CO₂."
- **Localisation.** The templates are currently English-only. The grammar (slot grammar + bucketing) is language-agnostic; the templates themselves would need translation.
- **Multi-target reports.** When a P-11 audit report aggregates multiple suppliers, an aggregated overview line is needed: "Across 12 suppliers, 3 are high-priority, 4 moderate, 5 at baseline."

---

*Document version 1.0 — May 2026. Anchored to `Indicators_Computation_v3.md`, `Indicator_ID_Schema_v1.md`, `Wireframes_All_v4.md` Appendix C, `PLFS_v4.md`.*
