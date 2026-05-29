# M-DIAG-A2 — Combined-Reducer Audit Report

*Date: 29 May 2026. Spec: `docs/M-DIAG-A2_spec.md` §4.4 / DGA6 / DGA13. Authority: this report verifies that every `combine()` reducer site in the engine has the right key-reading shape (the M-DIAG-A1 bug class).*

## Summary

**Two sites. One was the M-DIAG-A1 bug (fixed in that milestone). One was verified clean. No new bugs found.**

The audit was prompted by M-DIAG-A1's `_server_side_hf` key-naming bug: the legacy code read the bare-band key (`info.get(band)`) from a combined `Reducer.mean().combine(Reducer.count(), sharedInputs=True)` whose actual output key is suffixed `{band}_mean`. The bug class is broader than the single function — any combined reducer's consumer that reads bare-band keys could fail the same way. M-DIAG-A2 §4.4 / DGA6 broadened the audit to cover *all* `combine()` reducer patterns in the engine, not just `_server_side_hf`'s.

## Methodology

`grep -rn '\.combine(' engine/ --include="*.py"` returns the full inventory. Each hit was triaged by:

1. Identifying the reducer construction (which reducers are being combined)
2. Identifying the consumer code that reads the result dict
3. Checking whether the consumer reads bare-band keys or suffixed keys
4. If bare-band: confirming the bug exists (would EE actually emit the bare key, or the suffixed form?)
5. If suffixed: no bug — verified clean

## Inventory

`grep` returned exactly two non-test sites in `engine/`:

| # | Site | Reducer | Consumer | Verdict |
|---|---|---|---|---|
| 1 | [engine/core/repeatable_core.py:189](engine/core/repeatable_core.py#L189) — `_background_value_reduction` | `Reducer.median().combine(Reducer.stdDev(), sharedInputs=True)` | `info.get(f"{band}_median")` and `info.get(f"{band}_stdDev")` at [repeatable_core.py:260-261](engine/core/repeatable_core.py#L260-L261) | **VERIFIED CLEAN** — both `median()` and `stdDev()` naturally emit suffixed keys (no bare-band naming convention exists for these reducers), and the consumer reads the suffixed keys. The bug class doesn't apply. |
| 2 | [engine/core/repeatable_core.py:551](engine/core/repeatable_core.py#L551) — `_server_side_hf` | `Reducer.mean().combine(Reducer.count(), sharedInputs=True)` | `info.get(mean_key)` and `info.get(count_key)` at [repeatable_core.py:579-582](engine/core/repeatable_core.py#L579-L582) | **THE M-DIAG-A1 BUG — FIXED.** `mean_key = f"{band}_mean"` after M-DIAG-A1's fix; pre-fix it was `mean_key = band` (the bare-band form). Confirmed live in EE via the `/tmp/ee_reducer_key_probe.py` smoke run during M-DIAG-A1 Step A; the actual reducer dict keys are `{band}_mean` and `{band}_count`. |

## Why only two

`Reducer.X().combine(...)` with `sharedInputs=True` is the specific EE pattern that auto-suffixes outputs. The rest of the engine uses single (non-combined) reducers — `Reducer.mean()`, `Reducer.median()`, `Reducer.sum()`, `Reducer.frequencyHistogram()`, etc. — where the output naming follows each reducer's individual convention without the cross-reducer suffix dance.

Notably *not* in the inventory:

- Compositions on `ee.Image` like `image.reduce(reducer).combine(other_reducer)` — these aren't combined *reducers*, they're sequential operations on different image/value layers.
- Sequential `.combine()` calls on `ee.FeatureCollection` results (not reducer-level).
- DW categorical reductions in `engine/nature.py` — single `Reducer.frequencyHistogram()`, no `.combine()`.
- ODIAC reductions in `engine/ghg.py::compute_co2_snapshot` — `Reducer.mean()` standalone for the site/ring/total, batched via `ee.Dictionary` not via `Reducer.combine()`. Different batching mechanism; doesn't trigger the auto-suffix.

## Detection criteria for future combined-reducer additions

Anyone adding a new combined reducer should verify both sides of the contract:

1. **Output naming**: When you combine `Reducer.A()` with `Reducer.B()` via `sharedInputs=True`, EE auto-suffixes each output. The convention is `<input_band>_<reducer_name>` for each output. Confirm against `result.getInfo()` keys on a small EE probe — do not assume by reading docs alone (the M-DIAG-A1 bug existed for months despite docs being correct, because no one ran the probe).
2. **Consumer reads**: `info.get(key, default)` returns the default if the key is **absent**. EE's `reduceRegion` produces dicts where some keys may legitimately be `None` (band fully masked). Distinguish absent-key (bug shape) from `None` value (legitimate masked-band shape) — see the "Design note on null handling" docstring in `_server_side_hf` for the worked example.
3. **Test coverage**: Mock-based tests can replicate the same buggy key shape as the production code (M-DIAG-A1's mock fixture did exactly this), giving mutual-validation false-passes. Pair every combined-reducer site with an integration test that exercises the reducer against real or carefully-mocked EE — not just against a hand-authored result dict.

## Conclusion

**Audit closes with no new bugs.** The two `combine()` sites in the engine are verified — one was the M-DIAG-A1 bug now fixed, the other reads its suffixed keys correctly. The bug class doesn't have other instances in the engine as of 29 May 2026.

This audit is intentionally lightweight (per DGA13 — "Lightweight — not a full investigation report; a checked-list"). The integration test added at M-DIAG-A2 Step E.2 exercises the now-fixed site against realistic EE data, so any future regression of the M-DIAG-A1 fix would be caught at test time rather than rediscovered via diagnostic instrumentation.

A generic combined-reducer key-naming lint (a static check that flags `info.get(band)` reads paired with a combined `Reducer.X().combine(...)` construction in the same scope) was considered and deferred to v1.x per operator decision Q-DIAG-A2-3; see `docs/v1x_followups.md`.

---

*Audit performed against the engine at commit a6131e2 (M-DIAG-A1 close) + M-DIAG-A2's wind asymmetry fix and calibration. Findings recorded by M-DIAG-A2 Step E.1. Re-run the `grep` command above before the next milestone to refresh the inventory.*
