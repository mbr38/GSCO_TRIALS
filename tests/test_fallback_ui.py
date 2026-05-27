"""UI-side tests for M-FALLBACK-A1 (Steps G/I/J/H/K).

Covers the pure/­testable surfaces:
- map-tile cache invalidation (multi_map_state.invalidate_indicator),
- the single-supplier retry helper (fallback_retry),
- the C5 drilldown fallback sub-sections (spy on st),
- the large-AOI setup warning (spy on st),
- the P-11 PDF "Fallback applied" appendix (pure HTML),
- the P-07 strict-audit toggle threading into the batch executor.
"""

from __future__ import annotations

import types

import pytest

from ui.components import fallback_retry as fr
from ui.components import multi_map_state as mms


# ---------------------------------------------------------------------------
# Cache invalidation (FB18 / Q-FB-3 — only the patched indicator's tile)
# ---------------------------------------------------------------------------

class TestInvalidateIndicator:
    def test_removes_only_matching_indicator(self) -> None:
        store = {
            mms.CACHE_KEY: {
                "air.no2": {"tile_url": "x"},
                "air.no2.score": {"tile_url": "y"},
                "air.so2": {"tile_url": "z"},
            },
        }
        removed = mms.invalidate_indicator(store, "air.no2")
        assert removed == 2
        assert "air.no2" not in store[mms.CACHE_KEY]
        assert "air.no2.score" not in store[mms.CACHE_KEY]
        assert "air.so2" in store[mms.CACHE_KEY]  # other indicator untouched

    def test_noop_when_no_cache(self) -> None:
        assert mms.invalidate_indicator({}, "air.no2") == 0


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

class TestIsRetryable:
    @pytest.mark.parametrize("ind", ["air.no2", "air.aod", "ghg.ch4", "ghg.viirs", "nature.ndvi"])
    def test_six_step_indicators_are_retryable(self, ind) -> None:
        assert fr.is_retryable(ind) is True

    @pytest.mark.parametrize("ind", ["ghg.co2", "nature.kba", "nature.forest_loss", "nature.dw"])
    def test_non_six_step_indicators_not_retryable(self, ind) -> None:
        assert fr.is_retryable(ind) is False


class TestReasonIsRetryable:
    @pytest.mark.parametrize("reason", [
        "no_s5p_pixels", "no_cams_pixels", "no_maiac_pixels",
        "no_viirs_pixels", "background_ring_no_data",
    ])
    def test_sparse_coverage_reasons_retryable(self, reason) -> None:
        assert fr.reason_is_retryable(reason) is True

    @pytest.mark.parametrize("reason", ["out_of_coverage", None, "buffer_too_small"])
    def test_coverage_gaps_not_retryable(self, reason) -> None:
        assert fr.reason_is_retryable(reason) is False


class TestPatchResult:
    def test_noop_without_meta(self) -> None:
        result = {"air.so2.score": None}  # no _meta
        assert fr.patch_result(result, "air.so2", "sppy") is result

    def test_calls_patch_indicators_with_meta(self, monkeypatch) -> None:
        captured = {}

        def _fake_patch(payload, *, aoi, indicator_ids, selected_indicators,
                        time_range, ee_client, strategy):
            captured.update(
                aoi=aoi, indicator_ids=indicator_ids,
                selected_indicators=selected_indicators,
                time_range=time_range, strategy=strategy,
            )
            return {"patched": True}

        monkeypatch.setattr(fr, "patch_indicators", _fake_patch)
        result = {
            "air.so2.score": None,
            "_meta": {
                "aoi": {"centre": {"lat": 1.0, "lon": 2.0}, "radius_km": 50},
                "time_range": ["2026-03-01", "2026-05-30"],
                "selected_indicators": ["air.no2.score", "air.so2.score"],
            },
        }
        out = fr.patch_result(result, "air.so2", "sliding_lookback")
        assert out == {"patched": True}
        assert captured["indicator_ids"] == {"air.so2"}
        assert captured["strategy"] == "sliding_lookback"
        assert captured["time_range"] == ("2026-03-01", "2026-05-30")
        assert captured["selected_indicators"] == {"air.no2.score", "air.so2.score"}


class TestApplyRetry:
    def test_patches_state_and_invalidates_cache(self, monkeypatch) -> None:
        page_state = types.SimpleNamespace(result={
            "air.so2.score": None,
            "_meta": {
                "aoi": {"centre": {"lat": 1.0, "lon": 2.0}, "radius_km": 50},
                "time_range": ["2026-03-01", "2026-05-30"],
                "selected_indicators": ["air.so2.score"],
            },
        })
        fake_session = {
            "page_state": page_state,
            mms.CACHE_KEY: {"air.so2.score": {"tile_url": "stale"}},
        }
        monkeypatch.setattr(
            fr, "st", types.SimpleNamespace(session_state=fake_session),
        )
        monkeypatch.setattr(
            fr, "patch_indicators",
            lambda payload, **kw: {**payload, "air.so2.score": 0.5, "_meta": payload["_meta"]},
        )
        assert fr.apply_retry("air.so2", "sppy") is True
        assert page_state.result["air.so2.score"] == 0.5
        # Patched indicator's stale tile dropped.
        assert "air.so2.score" not in fake_session[mms.CACHE_KEY]

    def test_returns_false_without_screening(self, monkeypatch) -> None:
        monkeypatch.setattr(
            fr, "st", types.SimpleNamespace(session_state={}),
        )
        assert fr.apply_retry("air.so2", "sppy") is False


# ---------------------------------------------------------------------------
# Spy for Streamlit render-path functions
# ---------------------------------------------------------------------------

class _StSpy:
    """Records the rendering calls the fallback UI makes."""

    def __init__(self):
        self.markdown_calls: list[str] = []
        self.warning_calls: list[str] = []
        self.caption_calls: list[str] = []
        self.dividers = 0

    def markdown(self, text, *a, **k):
        self.markdown_calls.append(text)

    def warning(self, text, *a, **k):
        self.warning_calls.append(text)

    def caption(self, text, *a, **k):
        self.caption_calls.append(text)

    def divider(self):
        self.dividers += 1


# ---------------------------------------------------------------------------
# C5 drilldown fallback sub-sections (§5.2)
# ---------------------------------------------------------------------------

class TestC5FallbackSection:
    def _render(self, monkeypatch, extra):
        from ui.components import c5_drilldown as c5
        spy = _StSpy()
        monkeypatch.setattr(c5, "st", spy)
        c5._render_fallback_section(extra)
        return spy

    def test_no_fallback_renders_nothing(self, monkeypatch) -> None:
        spy = self._render(monkeypatch, {"aoi_scale_class": "site"})
        assert spy.markdown_calls == [] and spy.dividers == 0

    def test_temporal_fallback_sppy_copy(self, monkeypatch) -> None:
        spy = self._render(monkeypatch, {
            "temporal_fallback_used": True,
            "temporal_fallback_strategy": "sppy",
            "temporal_fallback_source_window": "2025-03-01/2025-05-31",
        })
        joined = "\n".join(spy.markdown_calls)
        assert "Fallback applied" in joined
        assert "same-period-previous-year" in joined
        assert "2025-03-01 to 2025-05-31" in joined

    def test_climatology_fallback_copy(self, monkeypatch) -> None:
        spy = self._render(monkeypatch, {
            "climatology_fallback_used": True,
            "climatology_fallback_vintage": "2026",
        })
        joined = "\n".join(spy.markdown_calls)
        assert "Regional baseline" in joined
        assert "2026 vintage" in joined

    def test_both_fallbacks_render_two_sections(self, monkeypatch) -> None:
        spy = self._render(monkeypatch, {
            "temporal_fallback_used": True,
            "temporal_fallback_strategy": "sliding_lookback",
            "temporal_fallback_source_window": "2025-12-01/2026-03-01",
            "climatology_fallback_used": True,
            "climatology_fallback_vintage": "2026",
        })
        joined = "\n".join(spy.markdown_calls)
        assert "earlier-window" in joined or "earlier window" in joined
        assert "Regional baseline" in joined
        assert spy.dividers == 2


# ---------------------------------------------------------------------------
# Large-AOI warning (§5.4)
# ---------------------------------------------------------------------------

class TestLargeAoiWarning:
    def _warn(self, monkeypatch, radius):
        from ui.components import aoi_scale
        spy = _StSpy()
        monkeypatch.setattr(aoi_scale, "st", spy)
        aoi_scale.render_large_aoi_warning(radius)
        return spy

    @pytest.mark.parametrize("radius", [None, 5, 100])
    def test_no_warning_at_or_below_100km(self, monkeypatch, radius) -> None:
        assert self._warn(monkeypatch, radius).warning_calls == []

    def test_warning_above_100km_mentions_biome(self, monkeypatch) -> None:
        spy = self._warn(monkeypatch, 150)
        assert len(spy.warning_calls) == 1
        assert "biome" in spy.warning_calls[0]


# ---------------------------------------------------------------------------
# P-11 PDF "Fallback applied" appendix (§5.5) — pure HTML
# ---------------------------------------------------------------------------

class TestPdfFallbackAppendix:
    def test_omitted_when_no_fallback(self) -> None:
        from ui.components.p11_sections import _render_fallback_appendix
        prov_blocks = [("air.no2", {"extra": {"aoi_scale_class": "site"}})]
        assert _render_fallback_appendix(prov_blocks) == ""

    def test_lists_temporal_and_climatology(self) -> None:
        from ui.components.p11_sections import _render_fallback_appendix
        prov_blocks = [
            ("air.no2", {"extra": {
                "temporal_fallback_used": True,
                "temporal_fallback_strategy": "sppy",
                "temporal_fallback_source_window": "2025-03-01/2025-05-31",
                "aoi_scale_class": "regional",
            }}),
            ("air.o3", {"extra": {
                "climatology_fallback_used": True,
                "climatology_fallback_vintage": "2026",
            }}),
        ]
        html = _render_fallback_appendix(prov_blocks)
        assert "Fallback methodology applied" in html
        assert "air.no2" in html and "same-period-previous-year" in html
        assert "air.o3" in html and "2026 vintage" in html
        assert "regional" in html  # AOI scale class line


# ---------------------------------------------------------------------------
# P-07 strict-audit toggle threading (§5.1)
# ---------------------------------------------------------------------------

class TestStrictAuditThreading:
    def test_executor_reads_strict_audit_flag(self, monkeypatch) -> None:
        # The batch executor must pass strict_audit_mode into ScreeningRun.
        import engine.prioritisation_executor as pe

        captured = {}

        class _FakeRun:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def run(self):
                # Complete enough for _classify_per_supplier to run.
                return {
                    "air.audit_followup_priority": 0.5,
                    "ghg.audit_followup_priority": 0.5,
                    "nature.followup_priority": 0.5,
                    "composite.overall_screening": 0.5,
                    "air.no2.score": 0.5,
                }

        monkeypatch.setattr(pe, "ScreeningRun", _FakeRun)
        # Minimal state + setup with one supplier.
        from ui.prioritisation_state import (
            PrioritisationState,
            PrioritisationStateKind,
        )
        state = PrioritisationState(kind=PrioritisationStateKind.S2_RUNNING, setup={})
        setup = {
            "suppliers": [{"id": "s1", "name": "n", "lat": 0.0, "lon": 0.0, "source": "x"}],
            "radius_km": 25,
            "time_range": ["2026-03-01", "2026-05-30"],
            "indicators": ["air.no2.score"],
            "strict_audit_mode": True,
        }
        pe.run_batch(state, setup, on_progress=lambda *a, **k: None)
        assert captured.get("strict_audit_mode") is True
