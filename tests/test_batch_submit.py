#!/usr/bin/env python3
"""Tests for scripts/ops/batch_submit.py — batch submission of ticket .md files.

Tests cover:
  - Happy path: ticket parsing, batch request construction, submission
  - Error path: missing files, API errors, no tickets
  - Edge cases: ticket without sections, multiple tickets, state file creation
"""

import json
import os
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Make scripts importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_TICKET = textwrap.dedent("""\
    ---
    id: FEAT-001
    title: Add user authentication
    status: pending
    priority: high
    ---

    # FEAT-001: Add user authentication

    ## Context
    We need authentication for the API.

    ## Description
    Implement JWT-based authentication with login and signup endpoints.

    ## Affected Files
    | File | Action | Description |
    |------|--------|-------------|
    | src/auth/login.ts | create | Login endpoint |
    | src/auth/signup.ts | create | Signup endpoint |

    ## Acceptance Criteria
    - [ ] AC-1: Users can sign up with email
    - [ ] AC-2: Users can log in with credentials
    - [ ] AC-3: JWT tokens are returned on success
""")

SAMPLE_TICKET_2 = textwrap.dedent("""\
    ---
    id: BUG-042
    title: Fix pagination offset
    status: pending
    priority: medium
    ---

    # BUG-042: Fix pagination offset

    ## Context
    Pagination returns duplicate items.

    ## Description
    Off-by-one error in the SQL OFFSET calculation.

    ## Affected Files
    | File | Action | Description |
    |------|--------|-------------|
    | src/db/queries.py | modify | Fix offset calc |

    ## Acceptance Criteria
    - [ ] AC-1: No duplicate items in paginated results
""")


def write_tickets(tmp_path, *contents):
    """Write ticket .md files and return their paths."""
    paths = []
    for i, content in enumerate(contents):
        p = tmp_path / f"ticket_{i}.md"
        p.write_text(content, encoding="utf-8")
        paths.append(str(p))
    return paths


# ---------------------------------------------------------------------------
# Tests: parse_ticket
# ---------------------------------------------------------------------------


class TestParseTicket:
    """Test ticket markdown parsing."""

    def test_parses_frontmatter_and_content(self, tmp_path):
        from scripts.ops.batch_submit import parse_ticket

        paths = write_tickets(tmp_path, SAMPLE_TICKET)
        result = parse_ticket(paths[0])

        assert result["id"] == "FEAT-001"
        assert result["title"] == "Add user authentication"
        assert "JWT-based authentication" in result["content"]

    def test_extracts_description_section(self, tmp_path):
        from scripts.ops.batch_submit import parse_ticket

        paths = write_tickets(tmp_path, SAMPLE_TICKET)
        result = parse_ticket(paths[0])

        assert "description" in result
        assert "JWT-based authentication" in result["description"]

    def test_returns_none_for_missing_file(self):
        from scripts.ops.batch_submit import parse_ticket

        result = parse_ticket("/nonexistent/path/ticket.md")
        assert result is None

    def test_handles_ticket_without_frontmatter(self, tmp_path):
        from scripts.ops.batch_submit import parse_ticket

        content = "# TASK-001: Simple task\n\n## Description\nDo the thing.\n"
        paths = write_tickets(tmp_path, content)
        result = parse_ticket(paths[0])

        # Should still parse, extracting what it can
        assert result is not None
        assert result["content"] == content


# ---------------------------------------------------------------------------
# Tests: build_batch_requests
# ---------------------------------------------------------------------------


class TestBuildBatchRequests:
    """Test batch request construction from parsed tickets."""

    def test_creates_plan_request_per_ticket(self, tmp_path):
        from scripts.ops.batch_submit import parse_ticket, build_batch_requests

        paths = write_tickets(tmp_path, SAMPLE_TICKET)
        tickets = [parse_ticket(p) for p in paths]
        requests = build_batch_requests(tickets)

        assert len(requests) == 1
        req = requests[0]
        assert req["custom_id"] == "FEAT-001-plan"
        assert req["params"]["model"] == "claude-sonnet-4-6"
        assert req["params"]["max_tokens"] == 8192
        assert len(req["params"]["messages"]) == 1
        assert req["params"]["messages"][0]["role"] == "user"

    def test_system_prompt_contains_ticket_content(self, tmp_path):
        from scripts.ops.batch_submit import parse_ticket, build_batch_requests

        paths = write_tickets(tmp_path, SAMPLE_TICKET)
        tickets = [parse_ticket(p) for p in paths]
        requests = build_batch_requests(tickets)

        system = requests[0]["params"].get("system", "")
        assert "implementation plan" in system.lower()

    def test_multiple_tickets_produce_multiple_requests(self, tmp_path):
        from scripts.ops.batch_submit import parse_ticket, build_batch_requests

        paths = write_tickets(tmp_path, SAMPLE_TICKET, SAMPLE_TICKET_2)
        tickets = [parse_ticket(p) for p in paths]
        requests = build_batch_requests(tickets)

        assert len(requests) == 2
        ids = {r["custom_id"] for r in requests}
        assert "FEAT-001-plan" in ids
        assert "BUG-042-plan" in ids

    def test_empty_tickets_list_returns_empty(self):
        from scripts.ops.batch_submit import build_batch_requests

        assert build_batch_requests([]) == []


# ---------------------------------------------------------------------------
# Tests: save_batch_state
# ---------------------------------------------------------------------------


class TestSaveBatchState:
    """Test state file persistence."""

    def test_creates_state_file(self, tmp_path):
        from scripts.ops.batch_submit import save_batch_state

        state_path = tmp_path / ".backlog-ops" / "batch-state.json"
        save_batch_state(
            batch_id="batch_abc123",
            ticket_mapping={"FEAT-001-plan": "/path/to/FEAT-001.md"},
            state_path=state_path,
        )

        assert state_path.exists()
        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert data["batch_id"] == "batch_abc123"
        assert data["ticket_mapping"]["FEAT-001-plan"] == "/path/to/FEAT-001.md"
        assert data["status"] == "in_progress"
        assert "submitted_at" in data

    def test_creates_parent_directories(self, tmp_path):
        from scripts.ops.batch_submit import save_batch_state

        state_path = tmp_path / "deep" / "nested" / "batch-state.json"
        save_batch_state(
            batch_id="batch_xyz",
            ticket_mapping={},
            state_path=state_path,
        )

        assert state_path.exists()


# ---------------------------------------------------------------------------
# Tests: main (integration)
# ---------------------------------------------------------------------------


class TestMainSubmit:
    """Integration tests for the main() entry point."""

    def test_dry_run_does_not_call_api(self, tmp_path):
        from scripts.ops.batch_submit import main

        paths = write_tickets(tmp_path, SAMPLE_TICKET)
        state_path = tmp_path / ".backlog-ops" / "batch-state.json"

        with patch("sys.argv", ["batch_submit.py", "--dry-run"] + paths):
            with patch.dict(os.environ, {}, clear=False):
                exit_code = main(state_path=state_path)

        assert exit_code == 0
        # No state file created in dry-run
        assert not state_path.exists()

    def test_submits_to_litellm_proxy(self, tmp_path):
        from scripts.ops.batch_submit import main

        paths = write_tickets(tmp_path, SAMPLE_TICKET)
        state_path = tmp_path / ".backlog-ops" / "batch-state.json"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "batch_test_123"}

        with patch("sys.argv", ["batch_submit.py"] + paths):
            with patch.dict(os.environ, {"LITELLM_MASTER_KEY": "sk-test"}, clear=False):
                with patch("scripts.ops.batch_submit.requests") as mock_requests:
                    mock_requests.post.return_value = mock_response
                    exit_code = main(state_path=state_path)

        assert exit_code == 0
        assert state_path.exists()

        # Verify POST was called to the right endpoint
        call_args = mock_requests.post.call_args
        assert "/v1/batches" in call_args[0][0]

        # Verify state was saved
        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert data["batch_id"] == "batch_test_123"

    def test_no_arguments_prints_usage(self, tmp_path, capsys):
        from scripts.ops.batch_submit import main

        state_path = tmp_path / ".backlog-ops" / "batch-state.json"

        with patch("sys.argv", ["batch_submit.py"]):
            exit_code = main(state_path=state_path)

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "no ticket files" in captured.err.lower() or "usage" in captured.err.lower()

    def test_api_error_returns_nonzero(self, tmp_path):
        from scripts.ops.batch_submit import main

        paths = write_tickets(tmp_path, SAMPLE_TICKET)
        state_path = tmp_path / ".backlog-ops" / "batch-state.json"

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.side_effect = Exception("500 Server Error")

        with patch("sys.argv", ["batch_submit.py"] + paths):
            with patch.dict(os.environ, {"LITELLM_MASTER_KEY": "sk-test"}, clear=False):
                with patch("scripts.ops.batch_submit.requests") as mock_requests:
                    mock_requests.post.return_value = mock_response
                    # The script checks status_code, not raise_for_status
                    exit_code = main(state_path=state_path)

        assert exit_code == 1

    def test_saves_review_templates_in_state(self, tmp_path):
        from scripts.ops.batch_submit import main

        paths = write_tickets(tmp_path, SAMPLE_TICKET)
        state_path = tmp_path / ".backlog-ops" / "batch-state.json"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "batch_rv_001"}

        with patch("sys.argv", ["batch_submit.py"] + paths):
            with patch.dict(os.environ, {"LITELLM_MASTER_KEY": "sk-test"}, clear=False):
                with patch("scripts.ops.batch_submit.requests") as mock_requests:
                    mock_requests.post.return_value = mock_response
                    exit_code = main(state_path=state_path)

        assert exit_code == 0
        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert "review_templates" in data
        assert "FEAT-001" in data["review_templates"]
