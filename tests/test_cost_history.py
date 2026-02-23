#!/usr/bin/env python3
"""Tests for scripts/ops/cost_history.py — cost-history feedback loop.

Tests cover:
  - Happy path: load, add entries, recalculate averages, estimate costs
  - Error path: missing file, malformed JSON, no matching entries
  - Edge cases: empty entries, single entry, rolling window cap at 20
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Make scripts importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_ENTRY = {
    "ticket_id": "BUG-001",
    "ticket_type": "BUG",
    "complexity": "simple",
    "pipeline": "fast",
    "files_modified": 2,
    "files_created": 0,
    "tests_added": 3,
    "total_tokens": 45000,
    "cost_usd": 0.28,
    "model_breakdown": {"sonnet": 1},
    "review_rounds": 1,
    "gates_passed_first_try": 5,
    "date": "2026-02-23",
}

SAMPLE_ENTRY_FEAT = {
    "ticket_id": "FEAT-010",
    "ticket_type": "FEAT",
    "complexity": "complex",
    "pipeline": "full",
    "files_modified": 8,
    "files_created": 3,
    "tests_added": 12,
    "total_tokens": 180000,
    "cost_usd": 1.50,
    "model_breakdown": {"sonnet": 2, "opus": 1},
    "review_rounds": 3,
    "gates_passed_first_try": 3,
    "date": "2026-02-22",
}


# ---------------------------------------------------------------------------
# Tests: load_history
# ---------------------------------------------------------------------------


class TestLoadHistory:
    """Test loading cost history from JSON file."""

    def test_returns_default_when_file_missing(self, tmp_path):
        from scripts.ops.cost_history import load_history

        path = str(tmp_path / "nonexistent" / "cost-history.json")
        result = load_history(path)

        assert result["version"] == "1.0"
        assert result["entries"] == []
        assert result["averages"] == {"by_type": {}, "by_complexity": {}, "by_pipeline": {}}

    def test_loads_existing_file(self, tmp_path):
        from scripts.ops.cost_history import load_history

        data = {"version": "1.0", "entries": [SAMPLE_ENTRY], "averages": {"by_type": {}, "by_complexity": {}, "by_pipeline": {}}}
        path = tmp_path / "cost-history.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        result = load_history(str(path))
        assert len(result["entries"]) == 1
        assert result["entries"][0]["ticket_id"] == "BUG-001"

    def test_handles_malformed_json(self, tmp_path):
        from scripts.ops.cost_history import load_history

        path = tmp_path / "cost-history.json"
        path.write_text("{bad json", encoding="utf-8")

        result = load_history(str(path))
        assert result["version"] == "1.0"
        assert result["entries"] == []


# ---------------------------------------------------------------------------
# Tests: add_entry
# ---------------------------------------------------------------------------


class TestAddEntry:
    """Test appending entries and recalculating averages."""

    def test_adds_entry_to_empty_history(self, tmp_path):
        from scripts.ops.cost_history import add_entry, load_history

        path = str(tmp_path / "cost-history.json")
        add_entry(path, SAMPLE_ENTRY)

        data = load_history(path)
        assert len(data["entries"]) == 1
        assert data["entries"][0]["ticket_id"] == "BUG-001"
        assert data["averages"]["by_type"]["BUG"]["avg_cost"] == 0.28

    def test_creates_parent_directory(self, tmp_path):
        from scripts.ops.cost_history import add_entry

        path = str(tmp_path / "deep" / "nested" / "cost-history.json")
        add_entry(path, SAMPLE_ENTRY)

        assert Path(path).exists()

    def test_adds_multiple_entries(self, tmp_path):
        from scripts.ops.cost_history import add_entry, load_history

        path = str(tmp_path / "cost-history.json")
        add_entry(path, SAMPLE_ENTRY)
        add_entry(path, SAMPLE_ENTRY_FEAT)

        data = load_history(path)
        assert len(data["entries"]) == 2


# ---------------------------------------------------------------------------
# Tests: recalculate_averages
# ---------------------------------------------------------------------------


class TestRecalculateAverages:
    """Test rolling average computation."""

    def test_computes_by_type_averages(self):
        from scripts.ops.cost_history import recalculate_averages

        data = {
            "version": "1.0",
            "entries": [
                {**SAMPLE_ENTRY, "ticket_id": "BUG-001", "cost_usd": 0.20, "total_tokens": 40000, "files_modified": 2},
                {**SAMPLE_ENTRY, "ticket_id": "BUG-002", "cost_usd": 0.40, "total_tokens": 60000, "files_modified": 4},
            ],
            "averages": {"by_type": {}, "by_complexity": {}, "by_pipeline": {}},
        }
        result = recalculate_averages(data)

        bug_avg = result["averages"]["by_type"]["BUG"]
        assert bug_avg["avg_cost"] == pytest.approx(0.30)
        assert bug_avg["avg_tokens"] == pytest.approx(50000.0)
        assert bug_avg["avg_files"] == pytest.approx(3.0)
        assert bug_avg["sample_size"] == 2

    def test_computes_by_complexity_averages(self):
        from scripts.ops.cost_history import recalculate_averages

        data = {
            "version": "1.0",
            "entries": [SAMPLE_ENTRY, SAMPLE_ENTRY_FEAT],
            "averages": {"by_type": {}, "by_complexity": {}, "by_pipeline": {}},
        }
        result = recalculate_averages(data)

        simple = result["averages"]["by_complexity"]["simple"]
        assert simple["avg_cost"] == pytest.approx(0.28)
        assert simple["sample_size"] == 1

        cpx = result["averages"]["by_complexity"]["complex"]
        assert cpx["avg_cost"] == pytest.approx(1.50)

    def test_computes_by_pipeline_success_rate(self):
        from scripts.ops.cost_history import recalculate_averages

        entry_pass = {**SAMPLE_ENTRY, "pipeline": "fast", "gates_passed_first_try": 5}
        entry_fail = {**SAMPLE_ENTRY, "ticket_id": "BUG-002", "pipeline": "fast", "gates_passed_first_try": 3}

        data = {
            "version": "1.0",
            "entries": [entry_pass, entry_fail],
            "averages": {"by_type": {}, "by_complexity": {}, "by_pipeline": {}},
        }
        result = recalculate_averages(data)

        fast = result["averages"]["by_pipeline"]["fast"]
        assert fast["avg_cost"] == pytest.approx(0.28)
        assert fast["success_rate"] == pytest.approx(0.5)

    def test_rolling_window_caps_at_20(self):
        from scripts.ops.cost_history import recalculate_averages

        # Create 25 entries: first 5 cost 10.0, last 20 cost 1.0
        entries = []
        for i in range(25):
            cost = 10.0 if i < 5 else 1.0
            entries.append({**SAMPLE_ENTRY, "ticket_id": f"BUG-{i:03d}", "cost_usd": cost})

        data = {
            "version": "1.0",
            "entries": entries,
            "averages": {"by_type": {}, "by_complexity": {}, "by_pipeline": {}},
        }
        result = recalculate_averages(data)

        bug_avg = result["averages"]["by_type"]["BUG"]
        # Last 20 entries: 1.0 each, avg should be 1.0
        assert bug_avg["avg_cost"] == pytest.approx(1.0)
        assert bug_avg["sample_size"] == 20

    def test_empty_entries_returns_empty_averages(self):
        from scripts.ops.cost_history import recalculate_averages

        data = {
            "version": "1.0",
            "entries": [],
            "averages": {"by_type": {}, "by_complexity": {}, "by_pipeline": {}},
        }
        result = recalculate_averages(data)

        assert result["averages"]["by_type"] == {}
        assert result["averages"]["by_complexity"] == {}
        assert result["averages"]["by_pipeline"] == {}


# ---------------------------------------------------------------------------
# Tests: estimate_cost
# ---------------------------------------------------------------------------


class TestEstimateCost:
    """Test cost estimation from historical data."""

    def test_returns_none_when_no_matching_entries(self, tmp_path):
        from scripts.ops.cost_history import estimate_cost

        path = str(tmp_path / "cost-history.json")
        Path(path).write_text(json.dumps({
            "version": "1.0", "entries": [], "averages": {"by_type": {}, "by_complexity": {}, "by_pipeline": {}}
        }), encoding="utf-8")

        result = estimate_cost(path, "FEAT", "complex", 5)
        assert result["estimate"] is None
        assert result["confidence"] == "none"
        assert result["sample_size"] == 0

    def test_scales_estimate_by_file_count(self, tmp_path):
        from scripts.ops.cost_history import add_entry, estimate_cost

        path = str(tmp_path / "cost-history.json")
        # Add entry: BUG, simple, 2 files, $0.28
        add_entry(path, SAMPLE_ENTRY)

        # Estimate for 4 files (2x the average)
        result = estimate_cost(path, "BUG", "simple", 4)
        assert result["estimate"] == pytest.approx(0.56)
        assert result["confidence"] == "low"  # sample_size=1 < 5
        assert result["sample_size"] == 1

    def test_confidence_medium_at_5_entries(self, tmp_path):
        from scripts.ops.cost_history import add_entry, estimate_cost

        path = str(tmp_path / "cost-history.json")
        for i in range(5):
            add_entry(path, {**SAMPLE_ENTRY, "ticket_id": f"BUG-{i:03d}"})

        result = estimate_cost(path, "BUG", "simple", 2)
        assert result["confidence"] == "medium"
        assert result["sample_size"] == 5

    def test_confidence_high_at_20_entries(self, tmp_path):
        from scripts.ops.cost_history import add_entry, estimate_cost

        path = str(tmp_path / "cost-history.json")
        for i in range(20):
            add_entry(path, {**SAMPLE_ENTRY, "ticket_id": f"BUG-{i:03d}"})

        result = estimate_cost(path, "BUG", "simple", 2)
        assert result["confidence"] == "high"
        assert result["sample_size"] == 20


# ---------------------------------------------------------------------------
# Tests: get_classifier_accuracy
# ---------------------------------------------------------------------------


class TestGetClassifierAccuracy:
    """Test pipeline classifier accuracy measurement."""

    def test_returns_zero_for_empty_history(self, tmp_path):
        from scripts.ops.cost_history import get_classifier_accuracy

        path = str(tmp_path / "cost-history.json")
        Path(path).write_text(json.dumps({
            "version": "1.0", "entries": [], "averages": {"by_type": {}, "by_complexity": {}, "by_pipeline": {}}
        }), encoding="utf-8")

        result = get_classifier_accuracy(path)
        assert result["total"] == 0
        assert result["escalations"] == 0
        assert result["accuracy"] == 0.0

    def test_counts_escalations(self, tmp_path):
        from scripts.ops.cost_history import add_entry, get_classifier_accuracy

        path = str(tmp_path / "cost-history.json")
        # Normal: simple + fast (no escalation)
        add_entry(path, SAMPLE_ENTRY)
        # Escalation: simple + full
        add_entry(path, {**SAMPLE_ENTRY, "ticket_id": "BUG-002", "complexity": "simple", "pipeline": "full"})
        # Normal: complex + full (not an escalation)
        add_entry(path, SAMPLE_ENTRY_FEAT)

        result = get_classifier_accuracy(path)
        assert result["total"] == 3
        assert result["escalations"] == 1
        assert result["accuracy"] == pytest.approx(0.6667)

    def test_trivial_escalation_counted(self, tmp_path):
        from scripts.ops.cost_history import add_entry, get_classifier_accuracy

        path = str(tmp_path / "cost-history.json")
        add_entry(path, {**SAMPLE_ENTRY, "ticket_id": "TASK-001", "complexity": "trivial", "pipeline": "full"})

        result = get_classifier_accuracy(path)
        assert result["escalations"] == 1
        assert result["accuracy"] == pytest.approx(0.0)

    def test_pipeline_counts(self, tmp_path):
        from scripts.ops.cost_history import add_entry, get_classifier_accuracy

        path = str(tmp_path / "cost-history.json")
        add_entry(path, SAMPLE_ENTRY)  # fast
        add_entry(path, SAMPLE_ENTRY_FEAT)  # full

        result = get_classifier_accuracy(path)
        assert result["total"] == 2
        assert result["fast_count"] == 1
        assert result["full_count"] == 1
