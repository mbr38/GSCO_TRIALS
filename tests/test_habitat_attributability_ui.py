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
        self.button_labels: list[str] = []
    def caption(self, s, **_kw) -> None:
        self.captions.append(s)
    def markdown(self, s, **_kw) -> None:
        self.markdowns.append(s)
    def expander(self, label, **_kw):
        return _Expander(label, self)
    def button(self, label, **_kw) -> bool:
        # Record the click affordance; return False so the click-handler
        # body doesn't fire (we test the click side-effect separately).
        self.button_labels.append(label)
        return False

    @property
    def all_text(self) -> str:
        return " || ".join(
            self.captions + self.markdowns + self.expander_labels + self.button_labels,
        )


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


class TestHabitatViewOnMapLink:
    """The 'View on map →' affordance is the only UI entry point for the
    habitat attributability overlay (habitat conversion isn't in C4b)."""

    def test_link_renders_when_state_computed(self, spy):
        c5_drilldown._render_habitat_attributability(_payload("high", offset=0.8, n_change=40))
        assert "View on map →" in spy.button_labels

    def test_link_renders_for_sparse_too(self, spy):
        # Sparse → no centroid, but the base map (supplier + buffer) is still
        # useful context. Link should still render.
        c5_drilldown._render_habitat_attributability(_payload("sparse", n_change=4))
        assert "View on map →" in spy.button_labels

    def test_link_absent_when_state_absent(self, spy):
        # Old payload from a saved analysis pre-M-ATTRIB-A1 has no state →
        # nothing to view on the map. Don't render a dead link.
        c5_drilldown._render_habitat_attributability(
            {"nature.habitat.confidence": 0.9}
        )
        assert "View on map →" not in spy.button_labels

    def test_click_sets_active_indicator_to_habitat_conversion_score(
        self, monkeypatch,
    ):
        # Spy on the side-effects: set_active_indicator + request_scroll +
        # st.rerun must all fire when the button is clicked.
        calls = {"active": None, "scrolled": False, "reran": False}

        def _set_active(ind_id):
            calls["active"] = ind_id

        def _scroll():
            calls["scrolled"] = True

        # Streamlit spy with a button that returns True (i.e. "user clicked").
        class _ClickSpy:
            captions: list = []
            markdowns: list = []
            button_labels: list = []
            def caption(self, *a, **k): pass
            def markdown(self, *a, **k): pass
            def expander(self, label, **_kw):
                return _Expander(label, type("_S", (), {"expander_labels": []})())
            def button(self, label, **_kw):
                self.button_labels.append(label)
                return True               # simulate the click
            def rerun(self):
                calls["reran"] = True

        spy = _ClickSpy()
        monkeypatch.setattr(c5_drilldown, "st", spy)
        monkeypatch.setattr(c5_drilldown, "_render_confidence_terms_expander", lambda *a, **k: None)
        monkeypatch.setattr(c5_drilldown, "set_active_indicator", _set_active)
        monkeypatch.setattr(c5_drilldown, "request_scroll", _scroll)

        c5_drilldown._render_habitat_attributability(_payload("high", offset=0.8, n_change=40))

        assert calls["active"] == "nature.habitat.conversion_score"
        assert calls["scrolled"] is True
        assert calls["reran"] is True
