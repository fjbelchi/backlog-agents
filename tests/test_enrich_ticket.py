#!/usr/bin/env python3
"""Tests for scripts/implementer/enrich_ticket.py — ticket enrichment with git metrics."""
import sys
from pathlib import Path

import pytest

# Add scripts/implementer to path so we can import enrich_ticket
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "implementer"))

from enrich_ticket import enrich_ticket


# ---------------------------------------------------------------------------
# 1. Happy path: enriches frontmatter with status/date/commit
# ---------------------------------------------------------------------------

def test_enriches_frontmatter_fields(tmp_path):
    """Completed ticket gets status, date, commit, and metadata in frontmatter."""
    ticket = tmp_path / "BUG-001.md"
    ticket.write_text(
        "---\n"
        "id: BUG-001\n"
        "title: Fix login crash\n"
        "status: in-progress\n"
        "tags: []\n"
        "affected_files:\n"
        "  - src/auth.py\n"
        "depends_on: []\n"
        "---\n"
        "## Description\nFix the login crash.\n"
    )
    result = enrich_ticket(
        ticket_path=str(ticket),
        commit_hash="abc1234",
        review_rounds=2,
        tests_added=5,
        cost_usd=0.35,
        model="sonnet",
    )

    # Verify returned dict contains enriched fields
    assert result["status"] == "completed"
    assert result["commit"] == "abc1234"
    assert result["review_rounds"] == 2
    assert result["tests_added"] == 5
    assert result["cost_usd"] == 0.35
    assert result["model"] == "sonnet"
    assert "completed" in result  # date field

    # Verify the file was updated
    content = ticket.read_text(encoding="utf-8")
    assert "status: completed" in content
    assert "commit: abc1234" in content
    assert "review_rounds: 2" in content
    assert "tests_added: 5" in content
    assert "implemented_by: backlog-implementer-v9" in content


# ---------------------------------------------------------------------------
# 2. Happy path: adds Actual Cost section
# ---------------------------------------------------------------------------

def test_adds_actual_cost_section(tmp_path):
    """An '## Actual Cost' section is appended with model, cost, and reviews."""
    ticket = tmp_path / "FEAT-010.md"
    ticket.write_text(
        "---\n"
        "id: FEAT-010\n"
        "title: Add payments\n"
        "status: pending\n"
        "---\n"
        "## Description\nPayments feature.\n"
    )
    enrich_ticket(
        ticket_path=str(ticket),
        commit_hash="def5678",
        review_rounds=1,
        tests_added=3,
        cost_usd=0.25,
        model="haiku",
    )

    content = ticket.read_text(encoding="utf-8")
    assert "## Actual Cost" in content
    assert "model: haiku" in content
    assert "cost_usd: 0.25" in content
    assert "review_rounds: 1" in content


# ---------------------------------------------------------------------------
# 3. Edge case: ticket without frontmatter
# ---------------------------------------------------------------------------

def test_handles_ticket_without_frontmatter(tmp_path):
    """Ticket with no frontmatter still gets enriched (frontmatter is created)."""
    ticket = tmp_path / "TASK-099.md"
    ticket.write_text("## Description\nNo frontmatter here.\n")

    result = enrich_ticket(
        ticket_path=str(ticket),
        commit_hash="aaa1111",
        review_rounds=1,
        tests_added=0,
        cost_usd=0.10,
        model="haiku",
    )

    assert result["status"] == "completed"
    assert result["commit"] == "aaa1111"

    content = ticket.read_text(encoding="utf-8")
    assert "status: completed" in content
    assert "## Actual Cost" in content
    # Original content preserved
    assert "## Description" in content
    assert "No frontmatter here." in content


# ---------------------------------------------------------------------------
# 4. Edge case: preserves existing content
# ---------------------------------------------------------------------------

def test_preserves_existing_content(tmp_path):
    """All original body sections are preserved after enrichment."""
    ticket = tmp_path / "BUG-020.md"
    original_body = (
        "## Description\nDetailed bug description.\n\n"
        "## Steps to Reproduce\n1. Open app\n2. Click button\n\n"
        "## Expected Behavior\nShould not crash.\n"
    )
    ticket.write_text(
        "---\n"
        "id: BUG-020\n"
        "title: Button crash\n"
        "status: pending\n"
        "priority: 0\n"
        "tags: [UI]\n"
        "---\n"
        + original_body
    )

    enrich_ticket(
        ticket_path=str(ticket),
        commit_hash="bbb2222",
        review_rounds=1,
        tests_added=2,
        cost_usd=0.15,
        model="haiku",
    )

    content = ticket.read_text(encoding="utf-8")
    # All original sections preserved
    assert "## Description" in content
    assert "Detailed bug description." in content
    assert "## Steps to Reproduce" in content
    assert "## Expected Behavior" in content
    # And priority was preserved in frontmatter
    assert "priority: 0" in content


# ---------------------------------------------------------------------------
# 5. Idempotent: running twice doesn't duplicate sections
# ---------------------------------------------------------------------------

def test_idempotent_no_duplicate_sections(tmp_path):
    """Running enrich_ticket twice doesn't create duplicate Actual Cost sections."""
    ticket = tmp_path / "TASK-050.md"
    ticket.write_text(
        "---\n"
        "id: TASK-050\n"
        "title: Idempotent test\n"
        "status: pending\n"
        "---\n"
        "## Description\nTest idempotency.\n"
    )

    # Run twice
    enrich_ticket(
        ticket_path=str(ticket),
        commit_hash="ccc3333",
        review_rounds=1,
        tests_added=0,
        cost_usd=0.05,
        model="haiku",
    )
    enrich_ticket(
        ticket_path=str(ticket),
        commit_hash="ddd4444",
        review_rounds=2,
        tests_added=3,
        cost_usd=0.10,
        model="sonnet",
    )

    content = ticket.read_text(encoding="utf-8")
    # Only one Actual Cost section
    assert content.count("## Actual Cost") == 1
    # Second run overwrites with new values
    assert "commit: ddd4444" in content
    assert "cost_usd: 0.1" in content


# ---------------------------------------------------------------------------
# 6. Default parameter values
# ---------------------------------------------------------------------------

def test_default_parameter_values(tmp_path):
    """Default values for optional parameters are applied correctly."""
    ticket = tmp_path / "TASK-060.md"
    ticket.write_text(
        "---\n"
        "id: TASK-060\n"
        "title: Defaults test\n"
        "status: pending\n"
        "---\n"
        "## Description\nTest defaults.\n"
    )

    result = enrich_ticket(
        ticket_path=str(ticket),
        commit_hash="eee5555",
    )

    assert result["review_rounds"] == 1
    assert result["tests_added"] == 0
    assert result["cost_usd"] == 0.0
    assert result["model"] == "haiku"

    content = ticket.read_text(encoding="utf-8")
    assert "review_rounds: 1" in content
    assert "model: haiku" in content
