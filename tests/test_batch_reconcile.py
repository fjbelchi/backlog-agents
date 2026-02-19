#!/usr/bin/env python3
"""Tests for scripts/ops/batch_reconcile.py — reconcile batch results into tickets."""

import json
import os
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SAMPLE_TICKET = textwrap.dedent("""\
    ---
    id: FEAT-001
    title: Add user authentication
    status: pending
    priority: high
    ---

    # FEAT-001: Add user authentication

    ## Description
    Implement JWT-based authentication.

    ## Acceptance Criteria
    - [ ] AC-1: Users can sign up
""")


def make_state(tmp_path, batch_id="batch_abc", ticket_path=None, status="in_progress"):
    """Create a batch-state.json and return its path."""
    state_path = tmp_path / ".backlog-ops" / "batch-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    ticket_path = ticket_path or str(tmp_path / "FEAT-001.md")
    state = {
        "batch_id": batch_id,
        "status": status,
        "submitted_at": "2026-02-19T10:00:00Z",
        "request_count": 1,
        "ticket_mapping": {"FEAT-001-plan": ticket_path},
        "review_templates": {"FEAT-001": "Review template here"},
    }
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state_path


class TestLoadState:
    def test_loads_valid_state(self, tmp_path):
        from scripts.ops.batch_reconcile import load_batch_state
        sp = make_state(tmp_path)
        state = load_batch_state(sp)
        assert state["batch_id"] == "batch_abc"
        assert state["status"] == "in_progress"

    def test_returns_none_for_missing_file(self, tmp_path):
        from scripts.ops.batch_reconcile import load_batch_state
        result = load_batch_state(tmp_path / "nope.json")
        assert result is None


class TestExtractPlanContent:
    def test_extracts_text_from_succeeded_result(self):
        from scripts.ops.batch_reconcile import extract_plan_content
        result = {
            "custom_id": "FEAT-001-plan",
            "response": {
                "status_code": 200,
                "body": {
                    "choices": [{
                        "message": {"content": "Step 1: Create auth module\nStep 2: Add tests"}
                    }]
                },
            },
        }
        text = extract_plan_content(result)
        assert "Step 1" in text
        assert "Step 2" in text

    def test_returns_none_for_failed_result(self):
        from scripts.ops.batch_reconcile import extract_plan_content
        result = {
            "custom_id": "FEAT-001-plan",
            "response": {"status_code": 500, "body": {"error": "server error"}},
        }
        text = extract_plan_content(result)
        assert text is None


class TestWritePlanToTicket:
    def test_appends_plan_section(self, tmp_path):
        from scripts.ops.batch_reconcile import write_plan_to_ticket
        ticket = tmp_path / "FEAT-001.md"
        ticket.write_text(SAMPLE_TICKET, encoding="utf-8")

        write_plan_to_ticket(str(ticket), "1. Create auth\n2. Add tests")

        content = ticket.read_text(encoding="utf-8")
        assert "## Implementation Plan" in content
        assert "1. Create auth" in content

    def test_replaces_existing_plan_section(self, tmp_path):
        from scripts.ops.batch_reconcile import write_plan_to_ticket
        ticket = tmp_path / "FEAT-001.md"
        ticket.write_text(
            SAMPLE_TICKET + "\n## Implementation Plan\nOld plan\n",
            encoding="utf-8",
        )
        write_plan_to_ticket(str(ticket), "New plan content")

        content = ticket.read_text(encoding="utf-8")
        assert "New plan content" in content
        assert "Old plan" not in content

    def test_skips_nonexistent_ticket(self, tmp_path):
        from scripts.ops.batch_reconcile import write_plan_to_ticket
        # Should not raise
        write_plan_to_ticket(str(tmp_path / "ghost.md"), "plan")


class TestMainReconcile:
    def test_completed_batch_writes_plans(self, tmp_path):
        from scripts.ops.batch_reconcile import main

        ticket = tmp_path / "FEAT-001.md"
        ticket.write_text(SAMPLE_TICKET, encoding="utf-8")
        sp = make_state(tmp_path, ticket_path=str(ticket))

        batch_response = {
            "id": "batch_abc",
            "status": "completed",
            "request_counts": {"total": 1, "completed": 1, "failed": 0},
        }
        results_response = [
            {
                "custom_id": "FEAT-001-plan",
                "response": {
                    "status_code": 200,
                    "body": {
                        "choices": [{"message": {"content": "Plan: create auth module"}}]
                    },
                },
            }
        ]

        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.json.return_value = batch_response

        mock_results = MagicMock()
        mock_results.status_code = 200
        mock_results.iter_lines.return_value = [
            json.dumps(r).encode() for r in results_response
        ]

        with patch("sys.argv", ["batch_reconcile.py"]):
            with patch.dict(os.environ, {"LITELLM_MASTER_KEY": "sk-test"}):
                with patch("scripts.ops.batch_reconcile.requests") as mock_req:
                    mock_req.get.side_effect = [mock_get, mock_results]
                    exit_code = main(state_path=sp)

        assert exit_code == 0
        content = ticket.read_text(encoding="utf-8")
        assert "## Implementation Plan" in content
        assert "Plan: create auth module" in content

    def test_pending_batch_prints_status(self, tmp_path, capsys):
        from scripts.ops.batch_reconcile import main

        sp = make_state(tmp_path)
        batch_response = {
            "id": "batch_abc",
            "status": "in_progress",
            "request_counts": {"total": 1, "completed": 0, "failed": 0},
        }

        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.json.return_value = batch_response

        with patch("sys.argv", ["batch_reconcile.py"]):
            with patch.dict(os.environ, {"LITELLM_MASTER_KEY": "sk-test"}):
                with patch("scripts.ops.batch_reconcile.requests") as mock_req:
                    mock_req.get.return_value = mock_get
                    exit_code = main(state_path=sp)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "pending" in captured.out.lower() or "in_progress" in captured.out.lower()

    def test_no_state_file_returns_cleanly(self, tmp_path, capsys):
        from scripts.ops.batch_reconcile import main

        sp = tmp_path / ".backlog-ops" / "batch-state.json"
        with patch("sys.argv", ["batch_reconcile.py"]):
            exit_code = main(state_path=sp)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "no batch" in captured.out.lower() or "not found" in captured.out.lower()
