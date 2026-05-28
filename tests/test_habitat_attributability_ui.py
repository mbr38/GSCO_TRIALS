"""Tests for the M-ATTRIB-A1 C5 habitat-attributability surface (§5.3/§5.4).

The `_render_habitat_attributability` function writes to Streamlit, so we
spy on `st.*` calls (the established C5 test convention — see
tests/test_coastal_handling_surfaces.py) rather than running a real session.
The nested habitat measurement-quality expander is stubbed to a no-op so
each test isolates the attributability rows + the Low-only expander.
"""

from __future__ import annotations

import pytest

from ui.components import c5_drilldown


class _Expander:
    def __init__(self, label: str, spy: "_Spy"):
        self._label, self._spy = label, spy
    def __enter__(self):
        self._spy.expander_labels.append(self._label)
        return self
    def __exit__(self, *_a):
        return False


class _Spy:
    def __init__(self) -> None:
        self.captions: list[str] = []
        self.markdowns: list[str] = []
        self.expander_labels: list[str] = []
    def caption(self, s, **_kw) -> None:
        self.captions.append(s)
    def markdown(self, s, **_kw) -> None:
        self.markdowns.append(s)
    def expander(self, label, **_kw):
        return _Expander(label, self)

    @property
    def all_text(self) -> str:
        return " || ".join(self.captions + self.markdowns + self.expander_labels)


@pytest.fixture
def spy(monkeypatch):
    s = _Spy()
    monkeypatch.setattr(c5_drilldown, "st", s)
    # Isolate: stub the habitat measurement-quality terms expander.
    monkeypatch.setattr(
        c5_drilldown, "_render_confidence_terms_expander", lambda *a, **k: None,
    )
    return s


def _payload(state, *, offset=None, n_change=0, direction=None, mq=0.955):
    return {
        "nature.habitat.confidence": mq,
        "nature.habitat.attributability_state": state,
        "nature.supplier_spatial_link.centroid_offset_km": offset,
        "nature.supplier_spatial_link.n_change_pixels": n_change,
        "_provenance.nature.supplier_spatial_link": {
            "extra": {"spatial_link_terms": {"direction": direction}},
        },
    }


class TestHabitatAttributabilityRows:
    def test_measurement_quality_row_always_renders(self, spy):
        c5_drilldown._render_habitat_attributability(_payload("high", offset=0.8, n_change=40))
        assert any("Measurement quality" in c for c in spy.captions)

    def test_high_attributability_badge(self, spy):
        c5_drilldown._render_habitat_attributability(_payload("high", offset=0.8, n_change=40))
        text = spy.all_text
        assert "Attributability" in text
        assert "High" in text
        assert "#16a34a" in text                 # green (AT9)
        assert "0.8 km from supplier" in text

    def test_low_attributability_opens_expander(self, spy):
        c5_drilldown._render_habitat_attributability(
            _payload("low", offset=4.2, n_change=47, direction="NW")
        )
        assert "What's behind this attributability?" in spy.expander_labels
        text = spy.all_text
        assert "4.2 km" in text
        assert "NW" in text
        assert "47" in text

    def test_moderate_does_not_open_low_expander(self, spy):
        c5_drilldown._render_habitat_attributability(
            _payload("moderate", offset=2.0, n_change=30)
        )
        assert "What's behind this attributability?" not in spy.expander_labels

    def test_sparse_renders_sparse_caption_no_badge(self, spy):
        c5_drilldown._render_habitat_attributability(_payload("sparse", n_change=4))
        assert any("Sparse" in c for c in spy.captions)
        # No coloured attributability badge markdown when sparse.
        assert all("#16a34a" not in m for m in spy.markdowns)

    def test_legacy_reference_confidence_rows_not_rendered(self, spy):
        # Regression (§5.4): forest_loss + regional_loss_evidence confidence
        # rows must NOT appear in the habitat panel anymore.
        c5_drilldown._render_habitat_attributability(_payload("high", offset=0.8, n_change=40))
        text = spy.all_text.lower()
        assert "forest loss" not in text
        assert "regional loss evidence" not in text
