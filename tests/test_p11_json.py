"""Tests for ui.components.p11_json (M-P11.4).

Pure-Python — no Streamlit. Pins the top-level shape (`report` +
`sources` keys), the metadata fields (title / template / timestamp /
notes / source_count), and the per-source payload shape (screening vs
prioritisation).
"""

# M-P11.4
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from ui.components.p11_json import render_json


def _state(title="Q2 demo", notes="", template_id="policy_audit"):
    return SimpleNamespace(title=title, notes=notes, template_id=template_id)


def _template(display_name="Policy audit report"):
    return SimpleNamespace(display_name=display_name)


def _screening_source(name="Screen A"):
    return {
        "id":              "src-1",
        "name":            name,
        "type":            "screening",
        "date_saved":      "2025-04-01T12:00:00+00:00",
        "screening_setup": {"radius_km": 10},
        "payload":         {"composite.overall_screening": 0.42},
    }


def _prioritisation_source(name="Prio A"):
    return {
        "id":                   "prio-1",
        "name":                 name,
        "type":                 "prioritisation",
        "date_saved":           "2025-04-02T12:00:00+00:00",
        "prioritisation_setup": {"indicators": ["air.no2.score"]},
        "supplier_results":     [
            {"name": "S0", "status": "success", "result": {"x": 1}},
        ],
        "summary":              {"n_total": 1},
    }


# ---------------------------------------------------------------------------
# 5h. top-level keys
# ---------------------------------------------------------------------------

def test_json_top_level_has_report_and_sources_keys():
    out = render_json(_state(), [_screening_source()], _template())
    parsed = json.loads(out)
    assert set(parsed.keys()) == {"report", "sources"}


# ---------------------------------------------------------------------------
# 5i. report metadata
# ---------------------------------------------------------------------------

def test_json_report_metadata_has_all_fields():
    out = render_json(
        _state(title="Q2 demo", notes="audit kickoff"),
        [_screening_source(), _screening_source("Screen B")],
        _template("Policy audit report"),
    )
    report = json.loads(out)["report"]
    assert report["title"]         == "Q2 demo"
    assert report["template_id"]   == "policy_audit"
    assert report["template_name"] == "Policy audit report"
    assert report["notes"]         == "audit kickoff"
    assert report["source_count"]  == 2
    # generated_at is ISO 8601; trivially parse-able.
    from datetime import datetime
    datetime.fromisoformat(report["generated_at"])


def test_json_template_name_is_none_when_template_missing():
    out = render_json(_state(), [_screening_source()], None)
    parsed = json.loads(out)
    assert parsed["report"]["template_name"] is None


# ---------------------------------------------------------------------------
# 5j. screening source payload shape
# ---------------------------------------------------------------------------

def test_json_screening_source_unpacks_setup_and_payload():
    out = render_json(_state(), [_screening_source()], _template())
    src = json.loads(out)["sources"][0]
    assert src["id"]   == "src-1"
    assert src["type"] == "screening"
    assert "screening_setup" in src["payload"]
    assert "payload"          in src["payload"]
    assert src["payload"]["screening_setup"]["radius_km"] == 10
    assert src["payload"]["payload"]["composite.overall_screening"] == 0.42


# ---------------------------------------------------------------------------
# 5k. prioritisation source payload shape
# ---------------------------------------------------------------------------

def test_json_prioritisation_source_unpacks_to_setup_results_summary():
    out = render_json(_state(), [_prioritisation_source()], _template())
    src = json.loads(out)["sources"][0]
    assert src["type"] == "prioritisation"
    payload = src["payload"]
    assert set(payload.keys()) == {
        "prioritisation_setup", "supplier_results", "summary",
    }
    assert payload["summary"]["n_total"]            == 1
    assert payload["supplier_results"][0]["name"]   == "S0"


# ---------------------------------------------------------------------------
# 5l. empty notes → None, not empty string
# ---------------------------------------------------------------------------

def test_json_empty_notes_becomes_none():
    out = render_json(_state(notes=""), [_screening_source()], _template())
    parsed = json.loads(out)
    assert parsed["report"]["notes"] is None


def test_json_empty_title_falls_back_to_untitled_report():
    out = render_json(_state(title=""), [_screening_source()], _template())
    parsed = json.loads(out)
    assert parsed["report"]["title"] == "Untitled report"


# ---------------------------------------------------------------------------
# Defensive: render_json returns a valid JSON string
# ---------------------------------------------------------------------------

def test_json_output_is_valid_json_string():
    out = render_json(_state(), [_screening_source()], _template())
    # No exception → valid JSON.
    parsed = json.loads(out)
    assert isinstance(parsed, dict)


def test_json_output_is_indented_for_readability():
    out = render_json(_state(), [_screening_source()], _template())
    # render_json uses indent=2 — output should contain a newline.
    assert "\n" in out
