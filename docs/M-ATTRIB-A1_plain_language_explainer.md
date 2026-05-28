# M-ATTRIB-A1 — Measurement quality vs attributability vs reference data

*Plain-language explainer. Audience: stakeholders, demo reviewers, auditors.
Date: 28 May 2026.*

## The one-sentence version

The tool now keeps three different questions clearly apart: **"how well did
we see it?"** (measurement quality), **"is it plausibly the supplier's?"**
(attributability), and **"what's the wider regional backdrop?"** (reference
data). Before this change, the Nature pillar quietly mixed the first two
together under one confusingly-named score.

## The three layers

### 1. Measurement quality — *"how well did we observe this site?"*

A 0–1 score combining things like valid-pixel coverage, cloud quality, and
how confidently the satellite classified the land cover. High means the
observation is trustworthy; low means thin or noisy data. It feeds the
headline scores and the confidence dots, exactly as before.

- Air: `air.measurement_quality_score` *(renamed from
  `air.attribution_confidence_score` — same number, honest name)*
- GHG: `ghg.data_quality_attribution` *(name kept for now; three sub-scores)*
- Nature: `nature.measurement_quality` *(renamed from
  `nature.quality_attribution`; four sub-scores)*

### 2. Attributability — *"is the detected change plausibly the supplier's?"*

This is **not** a quality score and **not** part of the headline. It's a
**category** — High / Moderate / Low / Sparse — that surfaces visually (a
coloured marker on the map, a badge in the drill-down) and in a short
disclaimer. It deliberately does **not** move the composite score, because
"we're not sure this is the supplier's doing" is a caveat to show the user,
not a number to fold into a verdict.

In v1.x the only indicator with attributability is **habitat conversion**.
We compute the centroid (the geographic "centre of mass") of the detected
natural→non-natural change pixels and measure how far that centroid sits
from the supplier coordinate:

- **High** — changes centred ≤ 1 km from the supplier (close → plausibly theirs)
- **Moderate** — 1–3 km
- **Low** — > 3 km (the change is concentrated far away → maybe a different actor)
- **Sparse** — too little change to locate a centroid (we don't guess)

Worked example: a supplier shows habitat conversion 4.2 km to the NW, over
47 change pixels → **Low** attributability. The map draws a red marker at the
centroid with a line back to the supplier; the drill-down explains the
detected change is concentrated away from the supplier coordinate.

### 3. Reference data — *"what's the wider regional backdrop?"*

Context layers that are shown but never scored. Hansen forest loss and ODIAC
CO₂ were already treated this way. M-ATTRIB-A1 adds **regional loss evidence**
to this layer: a ring-vs-buffer Hansen ratio shown on the Hansen card —
*"ring loss is 1.8× buffer loss over 2019–2023"*. A ratio above 1 means the
surrounding area was deforesting faster than the supplier's own buffer (a
broad regional pattern); below 1 means the buffer was a relatively active
pocket. It's context for interpreting the headline, not part of it.

## What changed, and why it might shift a score

Two signals left the Nature headline's measurement-quality aggregate:
`supplier_spatial_link` (now attributability) and `external_driver_screening`
(now the regional-loss reference ratio). Because both used to nudge the
Nature follow-up priority, **some suppliers' Nature scores will shift** after
this change. That shift is intentional and correct: the new
`nature.measurement_quality` reflects observation quality only, and
attribution caveats now live where a reviewer can see them rather than
silently moving a number.

The GHG `nearby_source_isolation` placeholder (a fixed 1.0) was likewise
removed from the GHG data-quality aggregate — it was inflating that score —
and is reserved for a future GHG attributability surface.

## Why this matters for the demo

When a reviewer asks *"is this the supplier's fault?"*, the honest answer is
often "the data shows change nearby, but attribution is uncertain." The old
design buried that uncertainty inside a quality score. Now it's a visible,
categorical, on-the-map statement — which is both more honest and more useful
for triage.

## Pointers

- Engine: `engine/core/attributability.py`,
  `engine.nature.compute_supplier_spatial_link`,
  `engine.nature.compute_regional_loss_evidence`
- Method spec: `docs/Indicators_Computation_v4.md` §3.3 / §7.5
- UI: C5 habitat panel + Hansen card (`ui/components/c5_drilldown.py`),
  map overlay (`ui/components/c4a_indicator_map.py`)
- Calibration of the 1 km / 3 km thresholds is a flagged follow-up
  (M-ATTRIB-A1 Q-AT-1).
