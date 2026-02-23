#!/usr/bin/env python3
"""Tests for scripts/implementer/{commit_msg,pre_review,micro_reflect}.py."""
import json
import sys
from pathlib import Path

import pytest

# Add scripts/implementer to path so we can import the modules
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "implementer"))

from commit_msg import generate_commit_msg
from pre_review import run_pre_review
from micro_reflect import reflect_wave


# ===========================================================================
# commit_msg.py tests (5)
# ===========================================================================


class TestGenerateCommitMsg:
    """Tests for generate_commit_msg()."""

    def test_basic_template(self):
        """Basic template produces '{type}({area}): implement {ticket_id}'."""
        result = generate_commit_msg(type="feat", area="auth", ticket_id="FEAT-042")
        assert result.startswith("feat(auth): implement FEAT-042")

    def test_with_summary(self):
        """When summary is provided, it is appended after an em-dash."""
        result = generate_commit_msg(
            type="fix", area="api", ticket_id="BUG-007", summary="Fix null pointer"
        )
        first_line = result.split("\n")[0]
        assert first_line == "fix(api): implement BUG-007 — Fix null pointer"

    def test_missing_type_defaults_to_feat(self):
        """When type is empty, it defaults to 'feat'."""
        result = generate_commit_msg(type="", area="core", ticket_id="TASK-001")
        assert result.startswith("feat(core): implement TASK-001")

    def test_empty_area_ok(self):
        """Empty area still produces valid commit message with empty parens."""
        result = generate_commit_msg(type="chore", area="", ticket_id="TASK-099")
        assert result.startswith("chore(): implement TASK-099")

    def test_trailer_present(self):
        """Commit message contains 'Closes: {ticket_id}' trailer."""
        result = generate_commit_msg(type="feat", area="db", ticket_id="FEAT-100")
        assert "\n\nCloses: FEAT-100" in result


# ===========================================================================
# pre_review.py tests (5)
# ===========================================================================


class TestRunPreReview:
    """Tests for run_pre_review()."""

    def test_clean_diff_all_pass(self):
        """A clean diff with good lint/test output passes all checks."""
        diff = (
            "+import os\n"
            "+path = os.path.join('a', 'b')\n"
        )
        result = run_pre_review(
            diff=diff,
            test_output="15 passed in 2.3s",
            lint_output="0 warnings, 0 errors",
        )
        assert result["imports_ok"] is True
        assert result["lint_clean"] is True
        assert result["tests_pass"] is True
        assert result["no_debug"] is True
        assert result["format_ok"] is True
        assert result["issues"] == []

    def test_debug_artifact_found(self):
        """Added lines with console.log, print(, debugger, TODO are flagged."""
        diff = (
            "+console.log('debug');\n"
            "+print('hello')\n"
            "+debugger;\n"
            "+// TODO: remove this\n"
        )
        result = run_pre_review(diff=diff)
        assert result["no_debug"] is False
        assert len(result["issues"]) > 0
        # Verify issue messages mention the problematic patterns
        issue_text = " ".join(result["issues"])
        assert "debug" in issue_text.lower() or "console.log" in issue_text.lower()

    def test_lint_errors(self):
        """Lint output with errors flags lint_clean as False."""
        result = run_pre_review(
            diff="+x = 1\n",
            lint_output="3 errors, 2 warnings found",
        )
        assert result["lint_clean"] is False

    def test_test_failures(self):
        """Test output containing 'failed' flags tests_pass as False."""
        result = run_pre_review(
            diff="+x = 1\n",
            test_output="10 passed, 2 failed",
        )
        assert result["tests_pass"] is False

    def test_mixed_tabs_spaces(self):
        """Added lines with mixed tabs and spaces flag format_ok as False."""
        diff = "+\t x = 1\n"  # tab followed by space
        result = run_pre_review(diff=diff)
        assert result["format_ok"] is False


# ===========================================================================
# micro_reflect.py tests (5)
# ===========================================================================


class TestReflectWave:
    """Tests for reflect_wave()."""

    def test_all_pass_helpful(self):
        """Bullet used on completed ticket (no retries) is tagged helpful."""
        wave_results = {
            "completed": ["BUG-001"],
            "failed": {},
            "escalated": [],
        }
        bullets_used = [{"id": "strat-00001", "ticket": "BUG-001"}]
        result = reflect_wave(wave_results, bullets_used)
        assert result["bullet_tags"] == [{"id": "strat-00001", "tag": "helpful"}]
        assert result["new_bullets"] == []

    def test_gate_fail_harmful(self):
        """Bullet used on failed ticket is tagged harmful."""
        wave_results = {
            "completed": [],
            "failed": {"BUG-002": "gate3_lint"},
            "escalated": [],
        }
        bullets_used = [{"id": "err-00003", "ticket": "BUG-002"}]
        result = reflect_wave(wave_results, bullets_used)
        assert result["bullet_tags"] == [{"id": "err-00003", "tag": "harmful"}]
        assert "failed" in result["reasoning"].lower() or "harmful" in result["reasoning"].lower()

    def test_retry_neutral(self):
        """Bullet used on completed ticket that also had failures is tagged neutral."""
        wave_results = {
            "completed": ["TASK-010"],
            "failed": {"TASK-010": "gate2_tdd"},
            "escalated": [],
        }
        bullets_used = [{"id": "strat-00010", "ticket": "TASK-010"}]
        result = reflect_wave(wave_results, bullets_used)
        assert result["bullet_tags"] == [{"id": "strat-00010", "tag": "neutral"}]

    def test_escalated_neutral(self):
        """Bullet used on escalated ticket is tagged neutral."""
        wave_results = {
            "completed": [],
            "failed": {},
            "escalated": ["FEAT-005"],
        }
        bullets_used = [{"id": "strat-00005", "ticket": "FEAT-005"}]
        result = reflect_wave(wave_results, bullets_used)
        assert result["bullet_tags"] == [{"id": "strat-00005", "tag": "neutral"}]

    def test_no_bullets_empty_result(self):
        """Empty bullets_used returns empty bullet_tags and new_bullets."""
        wave_results = {
            "completed": ["BUG-001"],
            "failed": {},
            "escalated": [],
        }
        result = reflect_wave(wave_results, [])
        assert result["bullet_tags"] == []
        assert result["new_bullets"] == []
        assert isinstance(result["reasoning"], str)
