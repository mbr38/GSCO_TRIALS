# M-UX-A1 — Closed-Entry Verification

**Milestone.** UX Polish: loader copy (2.6), saved-analyses search (2.7), parameter transparency (2.8).
**Status.** Shipped.
**Date.** 29 May 2026.
**Spec.** `M-UX-A1_spec.md` (document version 1.0, 28 May 2026).

Step B decisions locked with the user (29 May 2026):
- **Inventory scope:** 15 UX8-named thresholds + `TRAFFIC_LIGHT_THRESHOLDS` + `NORMALISATION_K` = **17**. The two first-pass additions (`NDVI_NEGATIVE_TREND_THRESHOLD`, `HANSEN_VERBAL_MENTION_THRESHOLD`) were dropped.
- **Search debounce:** match the P-09 filter-on-rerun pattern; UX6 satisfied structurally (small pure client-side filter, no per-keystroke cost), no custom JS component.
- **Loader copy:** spec UX3 wording verbatim.
- **Lint enforcement (Q-UX-2):** warning-only, not a hard CI gate.

> Note on the spec premise (A.1): the spec assumed the stale loader said "60-120s"; the actual current copy was `~30–60 seconds`. The change is the same single-line swap either way.

---

## Closed-entry checklist (§7)

- [x] **UX1** — Three items shipped, independently revertable. Commit boundaries: 2.6 = `ui/page_state.py` + `pages/05_Screening_Results.py`; 2.7 = `ui/components/p10_list.py`; 2.8 = `engine/parameter_registry.py` + annotations + `ui/components/p09_library.py`. 2.8 additionally guarded by the `_PARAMETERS_SECTION_ENABLED` feature flag.
- [x] **UX2** — Loader uses static copy. Constant `SCREENING_LOADER_COPY` in `ui/page_state.py`; consumed at `pages/05_Screening_Results.py` `_render_s1_computing`.
- [x] **UX3** — Exact wording locked. `tests/test_screening_loader_copy.py::test_exact_wording_locked`.
- [x] **UX4** — Search scope is name + supplier + location only. `ui/components/p10_list.py::_save_search_fields` reads `name`, `centre_metadata.node_name`, `centre_metadata.source`.
- [x] **UX5** — Case-insensitive substring, OR-combined. `_matches_search`; `tests/test_p10_search.py::test_case_insensitive`, `test_or_combined_across_fields`.
- [x] **UX6** — Live filter. Filter-on-rerun (no debounce machinery — satisfied structurally per Step B). `render_saved_analyses` calls `_filter_saves` each rerun.
- [x] **UX7** — Client-side filter; no backend query added. `_filter_saves` is a pure in-memory list comprehension over `st.session_state["saved_analyses"]`.
- [x] **UX8** — Inventory 17 (in 15-30 target). `engine/parameter_registry.py::_INVENTORY`; `tests/test_parameter_registry.py::test_inventory_size_in_target_range`, `test_step_b_locked_set`.
- [x] **UX9** — Rationale in docstrings, parsed at render time, no separate file. `_parse_annotation_block`; `tests/test_parameter_registry.py::test_live_value_read_from_module`.
- [x] **UX10** — Annotation format per §4.3. Example: `engine/constants.py::ANOMALY_Z_THRESHOLD`.
- [x] **UX11** — Three-tier system. `VALID_TIERS = {first-pass, calibrated, spec-mandated}`.
- [x] **UX12** — Lint enforces annotation (warning-only per Q-UX-2). `lint_inventory()`; `tests/test_parameter_registry.py::TestLint` — `test_lint_detects_missing_annotation` demonstrates detection, `test_inventory_is_fully_annotated_warns_only` shows it warns rather than fails.
- [x] **UX13** — Tier badge colours: first-pass amber `#b45309`, calibrated green `#15803d`, spec-mandated blue `#1d4ed8`. `ui/components/p09_library.py::_TIER_BADGE_COLOURS`; `tests/test_p09_parameters.py::test_badge_colours_match_ux13`.
- [x] **UX14** — Code-path format `module/path.py::CONSTANT_NAME`. `ParameterRecord.code_path`; `tests/test_parameter_registry.py::test_code_path_format`.
- [x] **UX15** — Last-reviewed optional. `_render_parameter_record` surfaces it only when present; `tests/test_parameter_registry.py::test_optional_last_reviewed_present` + `TestBlockExtraction::test_optional_fields_absent_is_fine`.
- [x] **UX16** — First-pass distribution honest. 15 first-pass / 2 spec-mandated / 0 calibrated. `tests/test_parameter_registry.py::test_honest_tier_distribution`.
- [x] **UX17** — P-09 section "⚙ Parameters & calibration", collapsible, below the confidence (methodology) block. `_render_parameters_section` called at the end of `_render_card`. Omitted when no parameters.
- [x] **UX18** — Read-only. The section renders values + code paths; no edit widgets. `tests/test_p09_parameters.py` exercises render helpers only.
- [x] **UX19** — Shared constants render under each indicator with a "(shared with N other)" note. `ParameterRecord.shared_count`; `_render_parameter_record`; `tests/test_parameter_registry.py::test_shared_constant_renders_under_each_indicator`, integration `test_shared_constant_appears_under_multiple_cards`.
- [x] **UX20** — Independent revertability. `_PARAMETERS_SECTION_ENABLED` feature flag in `ui/components/p09_library.py`; `tests/test_p09_parameters.py::test_feature_flag_default_enabled`.

---

## Test inventory

| File | Covers |
|---|---|
| `tests/test_screening_loader_copy.py` | 2.6 — wording, single-source, no stale estimate |
| `tests/test_p10_search.py` | 2.7 — filter logic (UX4/UX5/UX6), defensive on missing metadata |
| `tests/test_parameter_registry.py` | 2.8 — parser, lookup, code-path, lint (warning-only) |
| `tests/test_p09_parameters.py` | 2.8 — tier badge, value formatting, feature flag |
| `tests/test_m_ux_a1_integration.py` | §F — three surfaces coexist; search over real seeds; library coverage |

Pre-existing unrelated failure: `tests/test_repeatable_core.py::TestServerSideHfEEBugCoverage::test_server_side_hf_handles_zero_valid_pixels_with_missing_key` is part of the in-flight M-DIAG-A1 work (uncommitted before this milestone) and is untouched by M-UX-A1.

---

## Developer note — adding a new annotated constant (§2.1 deliverable)

To bring a new user-facing threshold under the P-09 parameter-transparency surface:

1. **Add the `# @parameter` block** immediately above the constant's definition (no blank line between the block and the constant — the parser walks backward over *contiguous* comment lines). Required fields: `tier`, `rationale`, `source`. Optional: `last_reviewed`, `applies_to`.

   ```python
   # @parameter
   # tier: first-pass            # one of: first-pass | calibrated | spec-mandated
   # rationale: Why this value. Continuation lines are indented and joined.
   # source: docs/...§X.Y; or "intuition"; or "calibration sweep YYYY-MM-DD"
   # last_reviewed: 2026-05-29
   # applies_to: [air.no2, ghg.ch4]   # base indicator IDs; matches full card IDs
   MY_THRESHOLD: float = 1.0
   ```

   - If several in-scope constants are defined consecutively, give **each** its own `# @parameter` block — the parser only attributes a block to the constant directly beneath it.
   - `applies_to` uses base IDs (`air.no2`); the registry matches them to the library's full card IDs (`air.no2.score`) by prefix / two-segment base.

2. **Register it** in `engine/parameter_registry.py::_INVENTORY` as `("MY_THRESHOLD", "engine.constants")` (or whichever module holds it — the registry spans `engine.constants` and `ui.components.severity`).

3. **Run the lint:** `pytest tests/test_parameter_registry.py`. A constant in `_INVENTORY` without a well-formed annotation is reported by `lint_inventory()` (a warning, not a hard failure — but `test_inventory_is_fully_annotated_warns_only` asserts the list is empty, so a gap is visible in CI output).

Scope rule (UX8): only **user-facing thresholds** belong in the inventory — values a user, auditor, or reviewer would want to see and understand. Internal decision-influencing constants (weight dicts, QA tables, normalisation factors, fallback multipliers) stay out.
