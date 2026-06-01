# M-ATTRIB-A2 — Step A Reconnaissance Findings

**Status.** COMPLETE — ready for Step B operator phrasing review.
**Date.** 31 May 2026.
**Author.** Claude Code (Step A recon per M-ATTRIB-A2 spec §5 Step A).
**Scope of this doc.** Investigation only. No engine, doc, or prose changes made. The one artifact written is a read-only numerical baseline (`tests/baselines/m_attrib_a2_prose_baseline.json`) for the Step D regression check.

> **Headline finding.** The spec's mental model of the verbal-summary work (§4.5: "~3 templates × 7 indicators = ~21 short paragraphs") **does not match the engine**. The verbal summary is **per-pillar, not per-indicator** — there is a single Air paragraph selected from a 15-cell template grid, not a per-indicator template set. This materially changes the Step B review surface and the Step C5 effort. Details in §A1 below. Everything else in the spec holds.

---

## A1 — Current verbal summary template wording

**File.** `engine/verbal_summary.py` (authority: `docs/Verbal_Summary_Templates_v1.md`).

**Structure (key correction to the spec).** The Air pillar produces **one paragraph**, selected by a 4-tuple key `(pillar, priority_bucket, confidence_bucket, dominant_path)`:
- `priority_bucket` ∈ {high, moderate, low} — the *severity* axis (maps to Normal/Concern/Severe).
- `confidence_bucket` ∈ {high, moderate, low}.
- `dominant_path` ∈ {main, fallback} — "main" names a single dominant pollutant; "fallback" fires when no pollutant clears the 0.40 contribution-share threshold.

That gives **15 Air templates** (9 main + 6 fallback; low-priority cells have no fallback variant) at `_PER_PILLAR_TEMPLATES`, lines 479–684. There is **no per-indicator prose**. Individual pollutants (NO₂, SO₂, …) only ever appear as the `{dominant_indicator}` slot inside the pillar paragraph — e.g. *"driven primarily by NO₂ (104 µmol m⁻², 3.3σ above background)"*. The buckets map to the spec's Normal/Concern/Severe as: **low = Normal, moderate = Concern, high = Severe** (× 3 confidence bands × 2 dominant paths).

**Implication for Step B/C.** The review surface is **15 Air pillar templates**, not 21 per-indicator paragraphs. The framing change is applied to ~6 distinct prose stems (the "elevated / moderate elevation / at background levels" clauses), not 7 × 3. This is *less* work than the spec estimated and keeps all 7 indicators automatically consistent (they share the templates).

**Current Air prose stems (verbatim), by priority bucket:**

| Priority (severity) | Current phrasing stem |
|---|---|
| high (Severe), main | "Air pollution is elevated at this location, driven primarily by {dominant_indicator} ({dominant_value}, {dominant_z} {dominant_direction} background)." |
| high, fallback | "Air pollution is elevated at this location across multiple gases, with no single dominant driver." |
| moderate (Concern), main | "Air pollution shows moderate elevation at this location, with {dominant_indicator} as the main contributor (…). The signal is within typical regional variability." |
| low (Normal) | "Air pollution is at background levels across the monitored pollutants at this location." |

**Where the framing is missing.** None of the current stems say "relative to its surroundings / nearby / regional context." "At background levels across the monitored pollutants" is the closest the Normal stem gets, but it reads as an absolute-level claim, not an explicit anomaly-vs-region claim. The Severe/Concern stems already lean attributable ("driven primarily by … above background") — they need only a light touch.

**Live baseline at the 5 production seeds** (proof the templates fire and what they currently say):

| Seed | Air template_id | Current Air paragraph (first clause) |
|---|---|---|
| sapezal  | air/low/high/main      | "Air pollution is at background levels across the monitored pollutants…" |
| brasilia | air/low/high/main      | "Air pollution is at background levels across the monitored pollutants…" |
| suape    | air/low/high/main      | "Air pollution is at background levels across the monitored pollutants…" |
| comodoro | air/moderate/high/main | "Air pollution shows moderate elevation… NO₂ as the main contributor (54 µmol m⁻², 1.8σ above background)…" |
| norilsk  | air/moderate/high/main | "Air pollution shows moderate elevation… NO₂ as the main contributor (104 µmol m⁻², 3.3σ above background)…" |

(Only `low` and `moderate` Air cells fire in the production seeds. No seed produces a `high` Air paragraph or the `fallback` path — Step B should still review those templates since they ship, but they won't show in the seed-string regression test.)

---

## A2 — P-09 indicator library entry structure

**Files.** Renderer `ui/components/p09_library.py`; content `demo/indicator_library.json`; loader `demo/indicator_library.py`.

**Structure.** All 9 Air entries (the 7 z-score indicators + `air.pm25.score`, `air.pm10.score`) share **one flat shape** in `indicator_library.json`: `display_name`, `sub_section`, `definition`, `decision_relevance`, `limitations`, `esg_alignment`, `tooltip_summary`. The dataclass `IndicatorCardContent` mirrors these fields; the renderer `_render_card` prints them in fixed order: Definition → Decision relevance → Limitations → [coastal block for ring-based] → Regulatory/ESG → (right column metadata) → confidence expander → parameters expander.

**There is no "What this measures" field today.** Cleanest insertion: add a new optional JSON field `what_this_measures` (string, Markdown) to each of the 7 entries, add the field to `IndicatorCardContent` (default `None`), and render it in `_render_card` as a new **"What this measures"** subsection placed right after **Definition** (before Decision relevance). When `None`, render nothing (silent-missing, matching the existing `tooltip_summary` convention). This is a small renderer + loader + JSON change; it touches no engine numerics.

**Note (test impact).** `tests/test_p09_library.py` and `tests/test_indicator_library.py` pin card shape/fields — they will need the new field threaded through. Not a blocker; flagged for Step C3/C4.

---

## A3 — P-11 report assembly structure

**File.** `ui/components/p11_sections.py`; templates `ui/components/p11_templates.py`.

**Air-pillar prose inherits from the verbal summary — confirmed.** `_render_pillar_findings` → `_render_source_pillar_block` (line 207) calls `generate_verbal_summary(payload)` and renders `verbal.overview / .air / .ghg / .nature` verbatim. So updating the verbal-summary templates (C5) propagates to P-11's pillar-findings section automatically (AT2-9 holds). **No per-section copy work needed there.**

**Independent copy that the spec's §4.6 "methodology paragraph" targets.** `_render_methodology` (lines 101–130) is a fixed source-agnostic block — it explains the 0–1 score and the red/amber/green bands but says nothing about anomaly-vs-region framing. This is the natural home for the spec's "small methodology paragraph near the top of the Air-pillar section so external PDF readers understand the framing." Recommendation: add a short framing sentence/paragraph to `_render_methodology` (applies pillar-wide, honest for the whole report). `_render_executive_summary` is purely tabular and needs no change.

**Caveat.** The verbal summary (and therefore the P-11 narrative) only renders for **full 19-indicator screenings**; partial-coverage sources fall back to a score table with no prose (lines 214–224). The framing in `_render_methodology` covers the partial case in prose-free form.

---

## A4 — Indicators_Computation_v4.md structure & framing-statement location

**File.** `docs/Indicators_Computation_v4.md` (v4.2).

**Layout.** §0 "Conventions used in every formula" already holds §0.1–§0.6 (raw-vs-score, the six-step repeatable core, trend, normalisation, time windows, seasonality). §1 is the Air pillar.

**Recommended location.** Add a new subsection **§0.7 "Severity framing"** at the end of §0 (after §0.6, before the `---` / §1 break). §0 is explicitly the "applies across all three pillars" block, which matches the spec's open question Q-AT2-A (framing extends architecturally to all z-score severities). Per-indicator/per-pillar sections then add a one-line back-reference "See §0.7 for the attributability framing." (Spec §4.7 left §0-vs-§1 for Step B; **§0.7 recommended.**)

**Conflicts check — none. The doc already supports the framing.** §1.5 "Column-to-surface uncertainty" already states: *"The repeatable core method (§0.2) compares the supplier site to its own background ring using the same retrieval… the Z-score is largely insensitive to this bias. The honesty layer is in the unit and the framing."* No per-indicator IC text claims severity = absolute pollution. §0.7 formalises what §1.5 already implies; §1.5 should cross-reference §0.7.

---

## A5 — CAMS PM2.5 / PM10 grammar (in or out of scope)

**Finding: PM2.5 and PM10 ARE z-score-based — same grammar as the other 7.**
- `engine/air.py`: all 9 pollutants (incl. `pm25`, `pm10`) run the identical `engine.core.six_step` pipeline (site vs background-ring z-score). PM differs only in data source (`ECMWF/CAMS/NRT`, `data_type="gridded_model_output"`, 44 km scale) — not in grammar.
- `Indicators_Computation_v4.md` §0.2 explicitly says the six steps run "for every Sentinel-5P pollutant **and for CAMS PM₂.₅**."

**Per the spec's own Step A rule** (§5.5: "if the former [z-score-based], add them to the scope"): **PM2.5/PM10 qualify for the framing.** They inherit the same anomaly-vs-region semantics.

**Recommendation for Step B.** Bring PM2.5/PM10 into the framing scope → **9 Air indicators**, not 7. Cost is near-zero: the verbal-summary templates are pillar-level (they already cover PM via the `air.pm_or_aerosol` dominant slot), and the P-09 work is just 2 more "What this measures" sections + IC back-references. Note PM2.5/PM10 are **not selected** in the 5 production seeds (all `None` in payloads), so they don't affect the Step D regression test. AT2-2 currently locks 7; this is the one scope decision Step B should explicitly confirm or override.

---

## A6 — Numerical regression baseline (Step D input)

**Captured.** `tests/baselines/m_attrib_a2_prose_baseline.json` — for each of the 5 production seeds:
- pillar/composite scores: `air.audit_followup_priority`, `ghg.audit_followup_priority`, `nature.followup_priority`, `composite.overall_screening`, `composite.confidence`, `air.measurement_quality_score`;
- per-Air-indicator severity inputs (`score`, `z`, `hf`, `confidence`) for all 9 indicators;
- the full verbal-summary output (`overview/air/ghg/nature` + `template_ids`).

This is the **pre-milestone** snapshot. Step D asserts these numbers are byte-identical after the prose changes (AT2-10 / R6) and that the Air prose changed to the new templates (string-match). Composite scores at the seeds for reference: sapezal 0.257, brasilia 0.308, suape 0.272, comodoro 0.582, norilsk 0.535.

---

## Decisions Step B must lock (load-bearing — AT2-13)

1. **Verbal-summary surface is 15 pillar-level Air templates, not 21 per-indicator paragraphs.** Confirm the framing is applied at the pillar-paragraph level (the engine has no per-indicator prose to edit). The per-*indicator* framing lives only in P-09 (A2).
2. **PM2.5/PM10 in scope?** Step A confirms they're z-score-based → recommend in (9 indicators). AT2-2 says confirm here.
3. **§0.7** as the IC framing-statement location (vs §0-intro or §1).
4. **"What this measures"** as a new P-09 JSON field rendered after Definition (A2).
5. The canonical framing wording (§4.1), the AOD anchor entry (§4.3), the 6/8 shorter sections (§4.4), the 15 verbal templates' reworded stems (§4.5), and the §0.7 text — the actual prose deliverables. Draft candidates can be prepared on request for this review.

## Notes on AOD validation report (C1 target, no change yet)

`docs/aod_pm25_validation.md` §5.3 ("The engine's anomaly severity is orthogonal to both axes") already contains the substance of the reframe ("the engine band tracks local spatial contrast") but under a heading that reads as a problem. Reframe + new §5.4 per spec §4.2 is a Step C1 task. `.docx` re-export pending (Q-AT2-B suggests same commit). §7 already lists "reframe AOD as context / spatial-contrast detector" as a calibration option — consistent with the milestone, no conflict.
