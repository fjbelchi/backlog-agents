#!/usr/bin/env python3
"""Tests for scripts/implementer/batch_review.py"""

import json
import os
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SAMPLE_DIFF = textwrap.dedent("""\
    diff --git a/src/auth.ts b/src/auth.ts
    index abc..def 100644
    --- a/src/auth.ts
    +++ b/src/auth.ts
    @@ -1,3 +1,6 @@
    +export function login(email: string) {
    +  return db.users.find(email);
    +}
""")

SAMPLE_TICKET = textwrap.dedent("""\
    ---
    id: FEAT-001
    title: Add login
    ---
    ## Acceptance Criteria
    - [ ] AC-1: login returns user
""")


def test_build_review_requests_one_per_focus(tmp_path):
    """One batch request is built per focus type."""
    from scripts.implementer.batch_review import build_review_requests
    reqs = build_review_requests(
        ticket_id="FEAT-001",
        diff=SAMPLE_DIFF,
        ticket_content=SAMPLE_TICKET,
        code_rules="",
        focus_types=["spec", "quality"],
        reviewer_prefix="You are a reviewer.",
    )
    assert len(reqs) == 2
    ids = [r["custom_id"] for r in reqs]
    assert "FEAT-001-review-spec" in ids
    assert "FEAT-001-review-quality" in ids


def test_build_review_requests_system_cached(tmp_path):
    """System message first block has cache_control."""
    from scripts.implementer.batch_review import build_review_requests
    reqs = build_review_requests(
        ticket_id="FEAT-001",
        diff=SAMPLE_DIFF,
        ticket_content=SAMPLE_TICKET,
        code_rules="",
        focus_types=["spec"],
        reviewer_prefix="Static prefix.",
    )
    system = reqs[0]["params"]["system"]
    assert isinstance(system, list)
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert "Static prefix." in system[0]["text"]


def test_build_review_requests_user_two_blocks():
    """User message: first block cached (code_rules), second dynamic (diff+ACs)."""
    from scripts.implementer.batch_review import build_review_requests
    reqs = build_review_requests(
        ticket_id="FEAT-001",
        diff=SAMPLE_DIFF,
        ticket_content=SAMPLE_TICKET,
        code_rules="No side effects.",
        focus_types=["quality"],
        reviewer_prefix="",
    )
    user_content = reqs[0]["params"]["messages"][0]["content"]
    assert len(user_content) == 2
    assert "cache_control" in user_content[0]        # stable code rules
    assert "No side effects." in user_content[0]["text"]
    assert "cache_control" not in user_content[1]    # dynamic diff+ACs
    assert SAMPLE_DIFF in user_content[1]["text"]


def test_empty_diff_raises():
    """Empty diff should raise ValueError."""
    from scripts.implementer.batch_review import build_review_requests
    with pytest.raises(ValueError, match="empty diff"):
        build_review_requests(
            ticket_id="FEAT-001",
            diff="",
            ticket_content=SAMPLE_TICKET,
            code_rules="",
            focus_types=["spec"],
            reviewer_prefix="",
        )
