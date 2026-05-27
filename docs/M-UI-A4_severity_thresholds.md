# M-UI-A4 — Severity Thresholds (calibration artefact)

**Status.** v1.0 defaults shipped (27 May 2026). Tunable fixture constants.
**Authority.** `ui/components/severity.py::SEVERITY_BANDS` is the code source of
truth; this doc is the human-readable rationale + calibration agenda.
**Scope.** The four severity grammars on the C4b indicator snapshot (P-05).
Severity thresholds are uniform across sectors in v1.x (sector-aware severity
is Tier C2, out of scope).

> **Spec v1.1 amendment (27 May 2026).** Hansen forest loss and ODIAC CO₂
> were removed from the headline grid as reference datasets (SR4/SR7/SR13).
> The **loss-fraction grammar** (Hansen) and the **ODIAC percentile** scheme
> are no longer implemented — three grammars remain: z-score, DW-categorical,
> distance/overlap. Hansen and ODIAC live in C5 (their treatment is M-UI-A6).

The C4b snapshot classifies every indicator into one of four severity states
— **High**, **Concern**, **Normal**, **Sparse data** — computed *locally* in
the UI from existing payload fields (no engine flag; SR3). Each of the three
grammars owns one severity function. The canonical thresholds below live in
`SEVERITY_BANDS` and are asserted by `tests/test_severity.py`.

---

## 1. Z-score grammar (Air + GHG CH₄/VIIRS + NDVI deviation)

Reads the spatiotemporal-anomaly z-score (`<indicator>.z`).

| `|z|` | Severity | Rationale |
|---|---|---|
| `≥ 2.0` | **High** | ~2σ above/below the regional baseline — a strong, decision-relevant anomaly. |
| `1.0 – 2.0` | **Concern** | 1–2σ — worth surfacing but not extreme. |
| `< 1.0` | **Normal** | Within one standard deviation of the surrounding-area baseline. |

**Sign convention.** Severity is driven by the **magnitude** `|z|`. Direction
(positive vs negative z) drives the tile's ▲/▼/● icon and the plain-language
framing line ("above/below regional baseline") — *not* the severity word
(SR1). This is the resolution of an ambiguity in the spec §4.1 text: the
band table is on `|z|` and the locked decision is "direction drives the icon
without changing severity." A consequence worth noting for calibration: a
reading strongly in the "good" direction (e.g. a site far *below* the
pollutant baseline, or far *greener* than baseline NDVI) still shows a
high-magnitude severity word. The direction icon contextualises it; flagged
below as a calibration question.

**VIIRS.** `ghg.viirs.z` was surfaced by M-UI-A4 (added to the VIIRS emitted
set; the value was always computed by the repeatable core, just filtered out).
See `Indicator_ID_Schema_v2.md` §3.1 footnote.

**ODIAC CO₂ is NOT z-score grammar** — it uses categorical (§2) because ODIAC
is inventory-allocated emissions, not an atmospheric column anomaly.

---

## 2. DW-categorical grammar (Dynamic World dominant class)

> **v1.1.** This section originally also covered ODIAC CO₂ via global
> percentile bands. ODIAC was removed from the headline grid as a reference
> dataset; the ODIAC scheme and its placeholder percentile constants
> (`ODIAC_MEAN_P75/P95`) are gone. The grammar is DW-only.

| Dominant class | Severity |
|---|---|
| `Built` or `Bare` | **Concern** |
| `Crops` / anything else | **Normal** |

DW alone **never fires High** — the categorical signal is deliberately
conservative and needs corroborating context (Hansen loss, NDVI trend). The
"Crops with class_confidence ≥ 0.60 → Normal with informational note" framing
from the spec is a render-time note, not a severity change.

---

## 3. Distance/overlap grammar (KBA proximity)

Driven by `nature.kba.dist_km` OR `nature.kba.overlap_pct`, whichever fires
more severely.

| Condition | Severity |
|---|---|
| `overlap_pct > 0` OR `dist_km < 1.0 km` | **High** |
| `1.0 ≤ dist_km < 10.0 km` | **Concern** |
| `dist_km ≥ 10.0 km` | **Normal** |

Buffer overlap is the clearest "this matters" signal — the supplier footprint
touches a designated biodiversity area. The 10 km Normal threshold is the
typical buffer-extent assumption.

---

## 4. (Removed in v1.1) Loss-fraction grammar (Hansen forest loss)

**Removed.** Hansen forest loss was removed from the headline grid as a
reference dataset (SR4/SR7 v1.1). No loss-fraction severity grammar is
implemented. Hansen's display lives in C5 with **no severity reading** — it
shows the cumulative loss percentage as context, not a scored signal (the
reference-dataset treatment is M-UI-A6's job). Hansen remains, per audit §9.3
v1.4, a "standing exposure" dataset outside the live composite.

---

## 5. Sparse-data override (all grammars)

A fourth state distinct from Normal (SR8). Fires — overriding whatever the
grammar band would say — when:

1. The indicator was **skipped** (`_provenance.<…>.skipped_reason` set).
2. An explicit `extra.fallback_used` flag is true (best-effort; not all
   indicators emit one today).
3. A valid-pixel fraction `< 0.30` (`extra.valid_pixel_pct`, when present).
4. **Confidence is None or `< 0.40`** — the primary, dependable driver,
   mirroring the reference dot logic in `traffic_light.confidence_glyph`.

> **Recon note (A.2).** The spec §4.1 `valid_pixel_pct` / `fallback_used`
> keys don't exist as named on every indicator today. The checks are
> defensive (they activate automatically if the engine adds them); confidence
> is the reliable signal for v1.x. No engine change was required (SR3 / §2.2).

Sparse counts as **non-critical** for the snapshot filter (it doesn't render
in the default critical view) and renders as a muted tile with a grey dot.
Failure tiles count as Sparse for filter purposes (SR12).

**Confidence and severity stay orthogonal (SR14).** A high-magnitude z at low
confidence reads as "High" severity *and* a Sparse confidence dot — the two
signals are not collapsed. (Note: the Sparse *override* will still bucket a
genuinely low-confidence indicator as Sparse; SR14's orthogonality is about
the confidence-dot glyph remaining an independent affordance, which it does.)

---

## 6. Calibration agenda (deferred — supervisor review, §4.6)

These thresholds shipped as v1.0 defaults per the supervisor's "ship defaults,
proceed" decision (27 May 2026). After the v1.1 amendment, the open
calibration questions narrow to two (Q3–Q5 were dropped with Hansen/ODIAC):

- **Q1.** Is `|z| ≥ 2.0` the right High threshold? Literature uses 1.96 (95%
  CI); 2.5 / 3.0 would be more conservative.
- **Q2.** Should KBA overlap fire High at *any* overlap > 0, or require a
  meaningful overlap (e.g. > 1%)?

Both are cheap to change: edit `SEVERITY_BANDS` and the assertions in
`tests/test_severity.py`.

*(Dropped with the v1.1 amendment: the ODIAC percentile-constant calibration
(no longer needed — ODIAC isn't on the grid), the Hansen 5%-threshold question
(loss-fraction grammar removed), and the z-score "good-direction" question.
The amended spec §4.6 lists only Q1–Q2. The sign convention is still
documented in §1 for reference.)*
