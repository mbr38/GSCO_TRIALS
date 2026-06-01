# M-REPORT-A1 — Step A Reconnaissance Findings

**Status.** Step A complete — resolved against live `ui/components/p11_*.py`, `ui/p11_state.py`, `ui/components/trend_record.py`, and `docs/`.
**Date.** 1 June 2026.
**Spec.** `M-REPORT-A1_spec.md` §8 (six open mechanical questions).
**Verdict.** Build is gated on two decisions that are the user's to make: **§8.1 section-model** (sizes the milestone) and **§8.4 ESRS datapoint reference** (external input, not in project docs).

---

## §8.1 — SECTION-MODEL (the load-bearing one)

**Confirmed: the shipped section model is flat & positional, exactly as the Handoff describes.**

- A `ReportTemplate` ([`p11_templates.py:19`](../ui/components/p11_templates.py#L19)) is a frozen dataclass whose `sections` field is a `tuple[str, ...]` of string keys — nothing else per section (no config, no nesting, no options).
- `get_section(key)` ([`p11_sections.py:34`](../ui/components/p11_sections.py#L34)) is a plain `dict` lookup into `_SECTION_REGISTRY` ([`p11_sections.py:1014`](../ui/components/p11_sections.py#L1014)), 11 keys → functions.
- Every section is `def _render_X(state, sources) -> str` returning a raw HTML string fragment.
- `build_report_html(state, sources, template)` ([`p11_assembler.py:28`](../ui/components/p11_assembler.py#L28)) loops `template.sections`, calls each fn, `"\n".join`s the fragments into `shell.html.j2`. Per-section exceptions are caught and inlined as an error fragment.

**Why all three locked features push against this flat model:**

| Feature | Pressure on the flat model |
|---|---|
| ESRS out-of-scope stubs (RT4) | Wants nesting / sub-sections under a topical header — flat keys give no hierarchy. |
| Dual-framed General report (RT8) | Same section body rendered under two framings. Flat model has no framing parameter — `_render_X(state, sources)` can't see `user_type` (it is **not** threaded into `build_report_html`; `ReportState` carries no `user_type` — see §8.6). |
| Content-aware glossary (RT13) | Wants each section to *declare the terms it uses*, or a post-render scan. Flat string fragments support only the scan path cleanly. |
| Trend report ordering (RT9) | Its own section order — already expressible as a new template tuple, so this one does **not** require a refactor. |

**The decision (sizes the milestone) — this is for the user, see questions below.** Two viable shapes:

- **Option A — minimal threading on the flat model.** Keep `_render_X(state, sources) -> str`. Thread `user_type` + a small `framing` context into the section signature (or onto `ReportState`). ESRS grouping/stubs become new section functions; glossary uses the **post-render fragment scan** (§8.5). Lowest risk, ships fastest, no churn to the 11 existing sections or their tests.
- **Option B — richer section objects.** Refactor sections to return a structured intermediate (dataclass: `id`, `html`, `terms_used`, `framing_opts`) rendered in one pass. Cleaner for per-section term declaration and central re-styling, but touches all 11 sections + `build_report_html` + every section test. Larger blast radius.

Recommendation: **Option A.** None of the three features strictly require the structured intermediate; the glossary's content-awareness is fully served by a fragment scan, and dual framing needs only `user_type` in scope. Option B is a "nice to have" refactor that does not buy a locked requirement.

---

## §8.2 — TEMPLATE-DISPOSITION

Current registry ([`p11_templates.py:29`](../ui/components/p11_templates.py#L29)): exactly two templates — `policy_audit` (policy_maker) and `supplier_audit` (mnc).

Readers of the template IDs (grep): `templates_for(user_type)` and `get_template(id)` are the only lookups; `_render_s1` ([`p11_renderer.py:53`](../ui/components/p11_renderer.py#L53)) drives selection off `templates_for`. Templates are keyed by `user_type`; **no code hard-codes the string `"policy_audit"`/`"supplier_audit"` outside the registry + tests** (`tests/test_p11_templates.py`).

**Resolution.** Under RT5/RT7/RT8:
- `policy_audit` → becomes the **policy-maker General variant** (RT8). Rename/repurpose; same body, ESRS layer disabled.
- `supplier_audit` → becomes the **MNC General variant** (E1+E2+E4) (RT8). Add the ESRS framing layer.
- Add three new MNC pillar templates (GHG/E1, Air/E2, Nature/E4) + one Trend template (both user types).
- Net registry: **5 distinct registrations** (General is one template, dual-framed by `user_type` at render time, not two IDs — RT8/§8.6).

Test `tests/test_p11_templates.py` asserts on the two IDs and will need updating in lockstep.

---

## §8.3 — TREND-RECORD-FIELDS

**Confirmed: every Option-A field is persisted on the saved-trend record.** `make_trend_entry` ([`trend_record.py:92`](../ui/components/trend_record.py#L92)) stores the **full** `compute_trend` result under `trend_result`, including the per-day `series`. The Option-A template needs, all present on `result`:

| Field | Key on `trend_result` | Reader |
|---|---|---|
| per-day series (graph) | `series` | `build_trend_svg` ([`trend_svg.py`](../ui/components/trend_svg.py)) |
| Theil-Sen slope | `trend` | `slope_display` ([`trend_record.py:69`](../ui/components/trend_record.py#L69)) |
| Mann-Kendall p-value | `trend_p` | `significance_text` ([`trend_record.py:56`](../ui/components/trend_record.py#L56)) |
| significance bucket | `significance_bucket` | `verdict_badge` ([`trend_record.py:19`](../ui/components/trend_record.py#L19)) |
| seasonal flag | `seasonal_flag` | `verdict_badge` / `seasonal_caveat` |
| confidence | `trend_confidence` | `trend_view.py:181` |
| coverage (N) | `coverage.n_valid_days` | `verdict_badge` |

Nothing is computed transiently in the view only. The presentation helpers (`verdict_badge`, `significance_text`, `slope_display`, `seasonal_caveat`) are already pure functions of `result`, reusable by the trend template with no recompute. `trend_graph` section ([`p11_sections.py:480`](../ui/components/p11_sections.py#L480)) already re-renders the SVG from the saved series — the trend *report* reorganises this into a per-indicator structured template.

---

## §8.4 — ESRS-DATAPOINTS  ⚠ external input gap

**Finding: specific ESRS datapoint codes are NOT in the project docs.** A repo-wide grep finds only **topical-standard-level** references:

- `Indicators_Computation_v4.md` ties indicators to ESRS topical standards at the framing level (NO₂ → "ESRS E2 / SASB convention"; ODIAC → "ESRS E1 / GHG Protocol"; KBA/Habitat → "ESRS E4 / TNFD"). These confirm the **pillar→topical-standard mapping (RT6)** but give no datapoint codes.
- `M-FALLBACK-A1_esg_alignment.md` cites **ESRS E1-6** and EFRAG IG 1/IG 2 — the only specific datapoint-level reference anywhere, and only for the GHG estimation-hierarchy argument.

There is **no** per-indicator → ESRS datapoint-code table (e.g. "NO₂ anomaly → E2-x §y") in any doc.

**Consequence (matches spec §4 item 2 / §8.4):**
- The **topical grouping** (E1/E2/E4 headers) and **scope-honesty out-of-scope stubs** parts of §4 depend only on RT6, which is confirmed — **these can proceed now.**
- The **datapoint labelling** part (§4 item 2) is **blocked** on an external ESRS datapoint reference the project does not currently hold. This is the second build gate.

---

## §8.5 — GLOSSARY-WIRING

Two content-aware mechanisms (spec §6):

- **Per-section term declaration** — each section returns/declares the terms it used. Clean only under the **Option B** structured section model; on the flat model it means bolting a parallel return value onto every `_render_X`.
- **Post-render fragment scan** — after `build_report_html` joins fragments, scan the rendered HTML against the master term registry (§6) and emit definitions for matches. Works directly on the **flat model** with zero changes to existing sections.

**Resolution (conditional on §8.1):** if §8.1 = Option A (flat), use the **fragment scan** — it is the only mechanism that doesn't require touching all 11 sections. Risk to manage: scan must match on word boundaries / known surface forms to avoid false positives (e.g. "AOD" inside another token), and should match the *display* term, not the slug. If §8.1 = Option B, per-section declaration becomes the cleaner choice.

---

## §8.6 — USER-TYPE-FILTER

`templates_for(user_type)` ([`p11_templates.py:81`](../ui/components/p11_templates.py#L81)) filters the registry by the template's `user_type` field. `_render_s1` reads `user_type` from `st.session_state` and offers only matching templates. This already supports the target inventory: **policy maker → [General, Trend]; MNC → [General, GHG, Air, Nature, Trend]** — set each new template's `user_type` accordingly (Trend registered for both — needs either two registrations or a `user_type` sentinel meaning "both"; the current field is a single string, so a small change is required here).

**Dual framing keys off `user_type` (RT8):** confirmed feasible, but note the plumbing gap — `build_report_html(state, sources, template)` and the section functions **do not currently receive `user_type`**. `ReportState` ([`p11_state.py`](../ui/p11_state.py)) carries `kind, template_id, source_ids, title, notes, error` — no `user_type`. To frame off `user_type` at render time we must thread it in (add to `ReportState` at S1, or pass into `build_report_html`). This is the single concrete code change the dual-framing decision (RT8) forces, regardless of §8.1 option.

Two sub-decisions for the registry: (a) how Trend registers for both roles (sentinel vs. two entries); (b) whether the General template ID is shared across roles with framing chosen at render, or one ID with a render-time branch. Both are mechanical once §8.1 is locked.

---

## Summary — what's ready vs. gated

| Item | Status |
|---|---|
| §8.1 section-model | **GATING DECISION** — recommend Option A (flat + threading). User's call; sizes the milestone. |
| §8.2 template-disposition | Resolved — repurpose 2 existing, add 3, total 5 registrations. |
| §8.3 trend-record-fields | Resolved — all fields persisted; no recompute needed. |
| §8.4 ESRS datapoints | **GATING / EXTERNAL INPUT** — codes not in docs. Topical grouping + stubs can proceed; datapoint labelling blocked. |
| §8.5 glossary-wiring | Resolved conditionally — fragment scan if §8.1=A; per-section if §8.1=B. |
| §8.6 user-type-filter | Resolved — filter supports inventory; must thread `user_type` into the section path + decide Trend's both-roles registration. |

*Step A findings v1.0 — 1 June 2026. Build proceeds once §8.1 and §8.4 are answered.*
