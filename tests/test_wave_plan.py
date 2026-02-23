#!/usr/bin/env python3
"""Tests for scripts/implementer/wave_plan.py -- graph-based wave planner."""
import json
import sys
from pathlib import Path

import pytest

# Add scripts/implementer to path so we can import wave_plan
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "implementer"))

from wave_plan import plan_wave, route_subagent


# ---------------------------------------------------------------------------
# 1. Happy path: No file conflict -- same wave
# ---------------------------------------------------------------------------

def test_no_conflict_same_wave():
    """Two tickets with different files should land in the same wave."""
    tickets = [
        {"id": "TASK-001", "priority": 0, "affected_files": ["src/a.py"], "depends_on": []},
        {"id": "TASK-002", "priority": 0, "affected_files": ["src/b.py"], "depends_on": []},
    ]
    result = plan_wave(tickets)
    assert len(result["waves"]) == 1
    wave_ids = [t["id"] for t in result["waves"][0]["tickets"]]
    assert "TASK-001" in wave_ids
    assert "TASK-002" in wave_ids
    assert result["waves"][0]["wave"] == 1
    assert result["skipped"] == []


# ---------------------------------------------------------------------------
# 2. File conflict: shared file -- different waves
# ---------------------------------------------------------------------------

def test_file_conflict_different_waves():
    """Two tickets sharing a file must be in different waves."""
    tickets = [
        {"id": "BUG-001", "priority": 0, "affected_files": ["src/shared.py"], "depends_on": []},
        {"id": "BUG-002", "priority": 1, "affected_files": ["src/shared.py"], "depends_on": []},
    ]
    result = plan_wave(tickets)
    assert len(result["waves"]) >= 2
    wave1_ids = [t["id"] for t in result["waves"][0]["tickets"]]
    wave2_ids = [t["id"] for t in result["waves"][1]["tickets"]]
    assert "BUG-001" in wave1_ids
    assert "BUG-002" in wave2_ids


# ---------------------------------------------------------------------------
# 3. Dependency ordering: B depends on A -- A goes first
# ---------------------------------------------------------------------------

def test_dependency_ordering():
    """Ticket B depends on A, so A must be in an earlier wave."""
    tickets = [
        {"id": "FEAT-002", "priority": 0, "affected_files": ["src/b.py"], "depends_on": ["FEAT-001"]},
        {"id": "FEAT-001", "priority": 1, "affected_files": ["src/a.py"], "depends_on": []},
    ]
    result = plan_wave(tickets)

    # Find which wave each ticket is in
    wave_of = {}
    for wave in result["waves"]:
        for t in wave["tickets"]:
            wave_of[t["id"]] = wave["wave"]

    assert wave_of["FEAT-001"] < wave_of["FEAT-002"]


# ---------------------------------------------------------------------------
# 4. Max slots respected: 10 tickets, max 3 per wave
# ---------------------------------------------------------------------------

def test_max_slots_respected():
    """With 10 non-conflicting tickets and max_slots=3, no wave has more than 3."""
    tickets = [
        {"id": f"TASK-{i:03d}", "priority": 0, "affected_files": [f"src/file_{i}.py"], "depends_on": []}
        for i in range(10)
    ]
    result = plan_wave(tickets, max_slots=3)
    for wave in result["waves"]:
        assert len(wave["tickets"]) <= 3
    # All 10 tickets should be assigned
    total = sum(len(w["tickets"]) for w in result["waves"])
    assert total == 10


# ---------------------------------------------------------------------------
# 5. Subagent routing: file extension mapping
# ---------------------------------------------------------------------------

def test_subagent_route_frontend():
    """.tsx files route to frontend."""
    assert route_subagent(["src/App.tsx", "src/Button.tsx"]) == "frontend"


def test_subagent_route_backend():
    """.py files route to backend."""
    assert route_subagent(["src/api/handler.py", "src/api/models.py"]) == "backend"


def test_subagent_route_devops():
    """Dockerfile and .yaml route to devops."""
    assert route_subagent(["Dockerfile", "k8s/deploy.yaml"]) == "devops"


def test_subagent_route_ml():
    """.ipynb files route to ml-engineer."""
    assert route_subagent(["notebooks/train.ipynb"]) == "ml-engineer"


def test_subagent_route_ml_by_name():
    """Files containing 'train' or 'model' in name route to ml-engineer."""
    assert route_subagent(["scripts/train_model.py", "scripts/model_utils.py"]) == "ml-engineer"


def test_subagent_route_general():
    """Unrecognized extensions default to general-purpose."""
    assert route_subagent(["README.md", "LICENSE"]) == "general-purpose"


def test_subagent_route_majority_vote():
    """Mixed extensions use majority vote."""
    # 2 frontend, 1 backend => frontend
    assert route_subagent(["src/App.tsx", "src/Button.jsx", "src/api.py"]) == "frontend"


# ---------------------------------------------------------------------------
# 6. Priority ordering: P0 scheduled before P3 in same wave
# ---------------------------------------------------------------------------

def test_priority_ordering():
    """Higher priority (lower number) tickets are placed first."""
    tickets = [
        {"id": "TASK-LOW", "priority": 3, "affected_files": ["src/low.py"], "depends_on": []},
        {"id": "TASK-HIGH", "priority": 0, "affected_files": ["src/high.py"], "depends_on": []},
    ]
    result = plan_wave(tickets)
    # Both should be in wave 1 (no conflict), but high-priority listed first
    wave1_ids = [t["id"] for t in result["waves"][0]["tickets"]]
    assert wave1_ids[0] == "TASK-HIGH"
    assert wave1_ids[1] == "TASK-LOW"


# ---------------------------------------------------------------------------
# 7. Empty input: returns empty waves and skipped
# ---------------------------------------------------------------------------

def test_empty_input():
    """Empty ticket list returns empty waves and skipped."""
    result = plan_wave([])
    assert result["waves"] == []
    assert result["skipped"] == []


# ---------------------------------------------------------------------------
# 8. Circular dependency: handled gracefully (skip circular tickets)
# ---------------------------------------------------------------------------

def test_circular_dependency_skipped():
    """Tickets in a dependency cycle should be placed in skipped."""
    tickets = [
        {"id": "TASK-A", "priority": 0, "affected_files": ["src/a.py"], "depends_on": ["TASK-B"]},
        {"id": "TASK-B", "priority": 0, "affected_files": ["src/b.py"], "depends_on": ["TASK-A"]},
    ]
    result = plan_wave(tickets)
    skipped_ids = [t["id"] for t in result["skipped"]]
    assert "TASK-A" in skipped_ids
    assert "TASK-B" in skipped_ids


def test_circular_with_non_circular():
    """Non-circular tickets still get planned even when circular ones exist."""
    tickets = [
        {"id": "TASK-A", "priority": 0, "affected_files": ["src/a.py"], "depends_on": ["TASK-B"]},
        {"id": "TASK-B", "priority": 0, "affected_files": ["src/b.py"], "depends_on": ["TASK-A"]},
        {"id": "TASK-C", "priority": 0, "affected_files": ["src/c.py"], "depends_on": []},
    ]
    result = plan_wave(tickets)
    skipped_ids = [t["id"] for t in result["skipped"]]
    assert "TASK-A" in skipped_ids
    assert "TASK-B" in skipped_ids
    # TASK-C should be planned
    all_wave_ids = []
    for w in result["waves"]:
        for t in w["tickets"]:
            all_wave_ids.append(t["id"])
    assert "TASK-C" in all_wave_ids


# ---------------------------------------------------------------------------
# 9. Output format: each ticket in wave has subagent_type and rationale
# ---------------------------------------------------------------------------

def test_output_format_has_required_fields():
    """Each ticket entry in a wave must have id, subagent_type, rationale."""
    tickets = [
        {"id": "BUG-001", "priority": 0, "affected_files": ["src/handler.py"], "depends_on": []},
    ]
    result = plan_wave(tickets)
    wave_ticket = result["waves"][0]["tickets"][0]
    assert "id" in wave_ticket
    assert "subagent_type" in wave_ticket
    assert "rationale" in wave_ticket
    assert wave_ticket["subagent_type"] == "backend"


# ---------------------------------------------------------------------------
# 10. Dependency on unknown ticket is ignored (not in input)
# ---------------------------------------------------------------------------

def test_unknown_dependency_ignored():
    """If depends_on references a ticket not in the input, treat as satisfied."""
    tickets = [
        {"id": "TASK-X", "priority": 0, "affected_files": ["src/x.py"], "depends_on": ["UNKNOWN-999"]},
    ]
    result = plan_wave(tickets)
    assert len(result["waves"]) == 1
    assert result["waves"][0]["tickets"][0]["id"] == "TASK-X"
    assert result["skipped"] == []


# ---------------------------------------------------------------------------
# 11. Complex multi-wave scenario
# ---------------------------------------------------------------------------

def test_complex_multi_wave():
    """Complex scenario: conflicts + dependencies + slots produce multiple waves."""
    tickets = [
        {"id": "T1", "priority": 0, "affected_files": ["src/shared.py", "src/a.py"], "depends_on": []},
        {"id": "T2", "priority": 1, "affected_files": ["src/shared.py", "src/b.py"], "depends_on": []},
        {"id": "T3", "priority": 0, "affected_files": ["src/c.py"], "depends_on": ["T1"]},
        {"id": "T4", "priority": 2, "affected_files": ["src/d.tsx"], "depends_on": []},
    ]
    result = plan_wave(tickets, max_slots=3)

    wave_of = {}
    for wave in result["waves"]:
        for t in wave["tickets"]:
            wave_of[t["id"]] = wave["wave"]

    # T1 and T2 conflict on shared.py, so different waves
    assert wave_of["T1"] != wave_of["T2"]
    # T3 depends on T1
    assert wave_of["T3"] > wave_of["T1"]
    # T4 has no conflicts with T1, could be wave 1
    assert wave_of["T4"] <= wave_of["T2"]
    # All tickets assigned
    assert len(wave_of) == 4
    assert result["skipped"] == []
