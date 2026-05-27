# M-FALLBACK-A1 — ESG Framework Alignment (Verification Spike Output)

**Status.** Step B verification spike output (per M-FALLBACK-A1 spec §4.4).
**Date.** 28 May 2026.
**Purpose.** Provide the citable footnote behind the FB7 claim that
same-period-previous-year (SPPY) temporal extrapolation is the *preferred*
secondary method over per-country regional climatology, before that claim
hardens into a defensibility argument.

> **Confidence of this spike: MODERATE, not HIGH.** The frameworks below
> endorse the *general principle* — fill gaps with the closest-to-primary
> proxy, prefer entity-specific data extrapolated over time to coarse
> regional averages, and disclose the substitution. They do **not** publish
> a single numbered rule literally stating "use last year's data before a
> regional average." The FB7 lock should therefore be framed as **"supported
> by the data-hierarchy logic of GHG Protocol / ESRS / SBTi"** rather than
> "mandated by a specific clause." This matches spec Risk R5's anticipated
> outcome.

---

## 1. The citable footnote (drop-in)

> Where current-period satellite coverage is insufficient to compute an
> indicator, the tool substitutes the same calendar period of the prior year
> (SPPY) in preference to a regional climatological baseline. This ordering
> follows the data-quality hierarchy common to the GHG Protocol Scope 3
> Technical Guidance (Ch. 7, *Collecting Data* — proxy data may be
> extrapolated/scaled from the most representative available source, and
> entity-specific data is preferred over secondary/average data) [1]; ESRS
> E1 / EFRAG IG (estimation permitted where direct data is unavailable
> without undue cost, with disclosure of the estimation and a commitment to
> improve coverage in future periods) [2]; and the SBTi's reliance on
> transparent, documented proxy assumptions where granular data is absent
> [3]. SPPY keeps the *supplier-specific spatial footprint* intact and varies
> only the time axis, so it sits one rung closer to primary data than a
> per-country median, which discards the site-specific signal entirely. Both
> substitutions are flagged in provenance and reduce the indicator's
> confidence score.

---

## 2. What each framework actually says (and the gap)

### GHG Protocol Scope 3 Technical Guidance — Ch. 7 *Collecting Data* [1]
- Confirmed: §7.3-adjacent guidance directs companies to assess data quality
  and, where sufficient-quality data is unavailable, to **use proxy data to
  fill gaps**, which "**may be extrapolated, scaled up, or customized to be
  more representative of the given activity**" (the worked example: a company
  with 80 of 100 facilities extrapolates to the missing 20).
- Confirmed direction: the standard's data-quality indicators reward
  **technological, temporal, geographical, and completeness representativeness**
  — a prior-year reading of the *same site* scores higher on geographical/
  technological representativeness than a country average, trading only on
  the temporal axis.
- **Gap:** the text frames extrapolation generically; it does not rank
  "prior-year same-entity" above "regional average" in a single sentence. The
  ranking is *inferred* from the representativeness scoring, not quoted.

### ESRS E1-6 / EFRAG Implementation Guidance [2]
- Confirmed: ESRS permits estimation when direct data is unavailable "without
  undue cost and effort," requires the undertaking to **disclose that the
  metric is partially estimated**, to **state the actions taken to improve
  coverage and quality in future periods**, and to **reassess at each
  reporting date whether reliable data has become available** and adjust.
- This maps cleanly onto our design: provenance flags = the disclosure;
  the retry mechanism + annual fixture refresh = the improvement commitment.
- **Gap:** ESRS is method-agnostic about *which* estimate to prefer; it
  governs disclosure of the estimate, not the SPPY-vs-climatology ordering.

### SBTi sectoral pathways [3]
- Confirmed: SBTi sector standards (e.g. the copper/SDA work) rely on
  **"explicit and transparent assumptions … and the use of proxy sectoral
  pathways where [sector]-specific ones do not exist"** — i.e. proxy only
  where the specific signal is absent, and document it.
- **Gap:** this is about emission-factor/pathway proxies, not satellite
  temporal substitution. Supports the *transparency* principle, weakly
  supports the *specific-before-generic* ordering, says nothing about SPPY.

---

## 3. Recommendation for the FB7 lock

Keep SPPY-first, but **reframe FB7** from a strong assertion to:

> *"SPPY is preferred over regional climatology because it preserves the
> supplier-specific spatial signal and varies only the temporal axis,
> consistent with the representativeness-based data-quality hierarchies of
> the GHG Protocol, ESRS, and SBTi. No framework mandates this ordering by a
> numbered clause; it follows from their shared logic."*

This is defensible in front of an auditor and does not overclaim.

---

## Sources

- [1] GHG Protocol, *Technical Guidance for Calculating Scope 3 Emissions*,
  Ch. 7 *Collecting Data* — [chapter PDF](https://ghgprotocol.org/sites/default/files/2022-12/Chapter7.pdf),
  [full guidance](https://ghgprotocol.org/sites/default/files/standards/Scope3_Calculation_Guidance_0.pdf).
- [2] EFRAG, *ESRS implementation guidance documents* (IG 1 / IG 2) and
  ESRS E1 Delegated Act Annex —
  [EFRAG IG index](https://www.efrag.org/en/projects/esrs-implementation-guidance-documents),
  [ESRS E1 Annex](https://www.efrag.org/sites/default/files/media/document/2024-08/ESRS%20E1%20Delegated-act-2023-5303-annex-1_en.pdf).
- [3] Science Based Targets initiative, *Standards and guidance* —
  [sciencebasedtargets.org/standards-and-guidance](https://sciencebasedtargets.org/standards-and-guidance).

*Spike performed via web research 28 May 2026. PDFs of the GHG Protocol
chapter could not be machine-extracted in full; the confirmations above rely
on the official-source search excerpts and should be re-verified against the
primary text before any external publication.*
