#!/usr/bin/env python3
"""Tests for scripts/implementer/wave_end.py — post-wave orchestrator."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts/implementer to path so we can import wave_end
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "implementer"))

from wave_end import run_wave_end


def _make_ticket(tmp_path, ticket_id, title="Test ticket"):
    """Helper: create a minimal ticket file in pending/."""
    pending_dir = tmp_path / "backlog" / "data" / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    ticket = pending_dir / f"{ticket_id}.md"
    ticket.write_text(
        f"---\n"
        f"id: {ticket_id}\n"
        f"title: {title}\n"
        f"status: in-progress\n"
        f"tags: []\n"
        f"---\n"
        f"## Description\n{title}\n"
    )
    return str(ticket)


def _base_wave_data(tmp_path, tickets=None):
    """Helper: build a base wave_data dict."""
    data_dir = str(tmp_path / "backlog" / "data")
    if tickets is None:
        tickets = []
    return {
        "wave": 1,
        "date": "2026-02-23",
        "tickets": tickets,
        "models_used": {"free": 0, "haiku": 2, "sonnet": 1, "opus": 0},
        "session_total_cost": 0.75,
        "waves_this_session": 2,
        "max_waves": 5,
        "bullets_used": [],
    }


# ---------------------------------------------------------------------------
# 1. Happy path: enrich + move + log + reflect
# ---------------------------------------------------------------------------

def test_full_happy_path(tmp_path):
    """Full wave end: enrich ticket, move to completed, write wave log, run reflect."""
    ticket_path = _make_ticket(tmp_path, "BUG-001", "Fix login crash")
    data_dir = str(tmp_path / "backlog" / "data")
    wave_log = tmp_path / ".backlog-ops" / "wave-log.md"

    wave_data = _base_wave_data(tmp_path, tickets=[
        {
            "id": "BUG-001",
            "path": ticket_path,
            "status": "completed",
            "commit": "abc123",
            "review_rounds": 1,
            "tests_added": 3,
            "cost_usd": 0.25,
            "model": "sonnet",
            "pipeline": "fast",
            "gates_failed": [],
        },
    ])
    wave_data["bullets_used"] = [{"id": "strat-00001", "ticket": "BUG-001"}]

    result = run_wave_end(
        wave_data=wave_data,
        data_dir=data_dir,
        wave_log_path=str(wave_log),
    )

    # Ticket was enriched
    assert result["enriched_count"] == 1
    # Ticket was moved to completed/
    assert result["moved_count"] == 1
    completed_dir = tmp_path / "backlog" / "data" / "completed"
    assert (completed_dir / "BUG-001.md").exists()
    assert not Path(ticket_path).exists()  # removed from pending
    # Completed ticket has enriched content
    completed_content = (completed_dir / "BUG-001.md").read_text(encoding="utf-8")
    assert "status: completed" in completed_content
    assert "## Actual Cost" in completed_content
    # Wave log was written
    assert result["wave_log_written"] is True
    assert wave_log.exists()
    log_content = wave_log.read_text(encoding="utf-8")
    assert "Wave 1" in log_content
    assert "BUG-001" in log_content
    # Micro reflect ran
    assert "micro_reflect" in result
    assert isinstance(result["micro_reflect"]["tags"], int)
    # Session limit not reached
    assert result["session_limit_reached"] is False


# ---------------------------------------------------------------------------
# 2. Empty wave: no tickets
# ---------------------------------------------------------------------------

def test_handles_empty_wave(tmp_path):
    """Empty wave (no tickets) produces zero counts and still writes log."""
    data_dir = str(tmp_path / "backlog" / "data")
    wave_log = tmp_path / ".backlog-ops" / "wave-log.md"
    (tmp_path / "backlog" / "data" / "pending").mkdir(parents=True, exist_ok=True)

    wave_data = _base_wave_data(tmp_path, tickets=[])

    result = run_wave_end(
        wave_data=wave_data,
        data_dir=data_dir,
        wave_log_path=str(wave_log),
    )

    assert result["enriched_count"] == 0
    assert result["moved_count"] == 0
    assert result["wave_log_written"] is True
    assert result["session_limit_reached"] is False


# ---------------------------------------------------------------------------
# 3. Creates completed/ directory if missing
# ---------------------------------------------------------------------------

def test_creates_completed_dir_if_missing(tmp_path):
    """completed/ directory is created automatically when it doesn't exist."""
    ticket_path = _make_ticket(tmp_path, "TASK-010", "Add feature")
    data_dir = str(tmp_path / "backlog" / "data")
    wave_log = tmp_path / ".backlog-ops" / "wave-log.md"

    # Verify completed/ doesn't exist yet
    completed_dir = tmp_path / "backlog" / "data" / "completed"
    assert not completed_dir.exists()

    wave_data = _base_wave_data(tmp_path, tickets=[
        {
            "id": "TASK-010",
            "path": ticket_path,
            "status": "completed",
            "commit": "xyz789",
            "review_rounds": 1,
            "tests_added": 2,
            "cost_usd": 0.10,
            "model": "haiku",
            "pipeline": "standard",
            "gates_failed": [],
        },
    ])

    result = run_wave_end(
        wave_data=wave_data,
        data_dir=data_dir,
        wave_log_path=str(wave_log),
    )

    # completed/ was created and file moved
    assert completed_dir.exists()
    assert (completed_dir / "TASK-010.md").exists()
    assert result["moved_count"] == 1


# ---------------------------------------------------------------------------
# 4. Session limit detection
# ---------------------------------------------------------------------------

def test_session_limit_detection(tmp_path):
    """When waves_this_session >= max_waves, session_limit_reached is True."""
    data_dir = str(tmp_path / "backlog" / "data")
    (tmp_path / "backlog" / "data" / "pending").mkdir(parents=True, exist_ok=True)
    wave_log = tmp_path / ".backlog-ops" / "wave-log.md"

    wave_data = _base_wave_data(tmp_path, tickets=[])
    wave_data["waves_this_session"] = 5
    wave_data["max_waves"] = 5

    result = run_wave_end(
        wave_data=wave_data,
        data_dir=data_dir,
        wave_log_path=str(wave_log),
    )

    assert result["session_limit_reached"] is True


def test_session_limit_not_reached(tmp_path):
    """When waves_this_session < max_waves, session_limit_reached is False."""
    data_dir = str(tmp_path / "backlog" / "data")
    (tmp_path / "backlog" / "data" / "pending").mkdir(parents=True, exist_ok=True)
    wave_log = tmp_path / ".backlog-ops" / "wave-log.md"

    wave_data = _base_wave_data(tmp_path, tickets=[])
    wave_data["waves_this_session"] = 3
    wave_data["max_waves"] = 5

    result = run_wave_end(
        wave_data=wave_data,
        data_dir=data_dir,
        wave_log_path=str(wave_log),
    )

    assert result["session_limit_reached"] is False


# ---------------------------------------------------------------------------
# 5. Skips micro_reflect when no playbook
# ---------------------------------------------------------------------------

def test_skips_reflect_when_no_playbook(tmp_path):
    """micro_reflect runs with empty bullets and no playbook gracefully."""
    ticket_path = _make_ticket(tmp_path, "FEAT-020", "New feature")
    data_dir = str(tmp_path / "backlog" / "data")
    wave_log = tmp_path / ".backlog-ops" / "wave-log.md"
    # No playbook created

    wave_data = _base_wave_data(tmp_path, tickets=[
        {
            "id": "FEAT-020",
            "path": ticket_path,
            "status": "completed",
            "commit": "fff000",
            "review_rounds": 2,
            "tests_added": 4,
            "cost_usd": 0.50,
            "model": "sonnet",
            "pipeline": "standard",
            "gates_failed": [],
        },
    ])

    result = run_wave_end(
        wave_data=wave_data,
        data_dir=data_dir,
        playbook_path=str(tmp_path / ".claude" / "nonexistent-playbook.md"),
        wave_log_path=str(wave_log),
    )

    # Should still work; micro_reflect returns tags but playbook update skipped
    assert result["enriched_count"] == 1
    assert result["moved_count"] == 1
    assert result["micro_reflect"]["tags"] >= 0


# ---------------------------------------------------------------------------
# 6. Counts remaining pending tickets
# ---------------------------------------------------------------------------

def test_counts_remaining_pending_tickets(tmp_path):
    """pending_remaining reflects tickets still in pending/ after moves."""
    # Create 3 tickets in pending
    _make_ticket(tmp_path, "TASK-001", "Task one")
    ticket2_path = _make_ticket(tmp_path, "TASK-002", "Task two")
    _make_ticket(tmp_path, "TASK-003", "Task three")

    data_dir = str(tmp_path / "backlog" / "data")
    wave_log = tmp_path / ".backlog-ops" / "wave-log.md"

    # Only complete TASK-002
    wave_data = _base_wave_data(tmp_path, tickets=[
        {
            "id": "TASK-002",
            "path": ticket2_path,
            "status": "completed",
            "commit": "ggg111",
            "review_rounds": 1,
            "tests_added": 1,
            "cost_usd": 0.05,
            "model": "haiku",
            "pipeline": "fast",
            "gates_failed": [],
        },
    ])

    result = run_wave_end(
        wave_data=wave_data,
        data_dir=data_dir,
        wave_log_path=str(wave_log),
    )

    # 2 tickets remain in pending (TASK-001 and TASK-003)
    assert result["pending_remaining"] == 2


# ---------------------------------------------------------------------------
# 7. Non-completed tickets are not enriched or moved
# ---------------------------------------------------------------------------

def test_non_completed_tickets_skipped(tmp_path):
    """Tickets with status != 'completed' are not enriched or moved."""
    ticket_path = _make_ticket(tmp_path, "BUG-050", "Blocked bug")
    data_dir = str(tmp_path / "backlog" / "data")
    wave_log = tmp_path / ".backlog-ops" / "wave-log.md"

    wave_data = _base_wave_data(tmp_path, tickets=[
        {
            "id": "BUG-050",
            "path": ticket_path,
            "status": "failed",
            "commit": "",
            "review_rounds": 1,
            "tests_added": 0,
            "cost_usd": 0.05,
            "model": "haiku",
            "pipeline": "fast",
            "gates_failed": ["tdd"],
        },
    ])

    result = run_wave_end(
        wave_data=wave_data,
        data_dir=data_dir,
        wave_log_path=str(wave_log),
    )

    # Not enriched or moved
    assert result["enriched_count"] == 0
    assert result["moved_count"] == 0
    # Original file still in pending
    assert Path(ticket_path).exists()
