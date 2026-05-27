# What "reference dataset" means in the GSCO tool

*Stakeholder-facing explainer — M-UI-A6, 28 May 2026.*

## The short version

Two of the datasets you'll see in a screening result — **Hansen forest
loss** and **ODIAC CO₂** — are shown as **reference data**, not as scored
signals. They appear in the drill-down (P-05, section C5) under a clearly
labelled "Reference datasets" heading, with a badge that reads *"Reference
dataset — not used in composite score."* This page explains why.

## Why some data is "reference" and not "scored"

The tool's headline score is built from **live signals**: measurements that
describe the *current* state of a supplier site within the screening time
window you chose. Air-pollutant columns, methane, land-cover change, and
vegetation condition are all read for that window and compared against the
surrounding area. That comparison is what produces a severity reading and a
composite score.

Hansen and ODIAC don't fit that mould:

- **Hansen forest loss** is a *cumulative tally*. It counts forest-cover
  loss year by year going back to 2000. A number like "2.3% of the buffer
  area lost" describes change accumulated over many years — not what is
  happening in your screening window. Mixing a cumulative-since-2000 number
  into a present-window score would distort the comparison.
- **ODIAC CO₂** is an *inventory allocation*, not a satellite measurement.
  It estimates fossil-fuel emissions by taking national totals and spreading
  them across a grid using proxies like nightlights. It's also published with
  a 1–2 year lag. It tells you about emissions *density* in an area, but it
  isn't an atmospheric observation of what's there now.

Both are genuinely useful — just useful as **context**, not as live
evidence. So we show them, label them honestly, and keep them out of the
number that drives audit prioritisation.

## "Not used in the score" is honesty, not hiding

We deliberately surface these datasets rather than dropping them. An auditor
or policymaker who wants to understand a site's longer-term trajectory should
be able to see the Hansen loss history and the ODIAC emissions estimate. The
badge and the section header exist so that nobody mistakes them for live
signals — the framing protects the integrity of the score *and* keeps the
underlying data visible.

The Hansen card also explains the one place Hansen *does* feed the analysis:
a behind-the-scenes "regional loss evidence" check that compares forest loss
right at the site against the wider surrounding ring. When loss is mostly in
the ring rather than at the site, that suggests a regional driver (a fire, a
drought, broad deforestation) rather than something specific to the supplier
— and that nuance feeds a confidence adjustment, not the score itself.

## Where to look

- **In the app:** P-05 screening results → "Drill-down by pillar" →
  scroll to **Reference datasets**. Each card has a "Why reference data?"
  expander and an "Open in Indicator Library" link for the full method.
- **In the verbal summary:** when Hansen shows meaningful cumulative loss,
  the summary may note whether it *agrees with* or *diverges from* the live
  nature signals. ODIAC is not discussed in the summary in this version.
- **In the PDF report:** a "Reference datasets" section appears after the
  scored indicators, marked as context.

## Related decisions

- The demotion of Hansen out of the live composite: audit
  `Indicators_Audit_and_v1x_Roadmap.md` §9.3 v1.4.
- The demotion of ODIAC out of the live composite: audit doc M5.5b.
- Removing both from the headline grid: M-UI-A4 v1.1.
- This reference-dataset display: M-UI-A6.
