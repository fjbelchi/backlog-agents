#!/usr/bin/env python3
"""Tests for scripts/implementer/batch_review_poll.py"""

import json
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_mock_response(processing_status, results=None):
    """Build mock API responses for batch status and results."""
    status_resp = MagicMock()
    status_resp.status_code = 200
    status_resp.json.return_value = {"processing_status": processing_status, "id": "msgbatch_test"}

    results_resp = MagicMock()
    results_resp.status_code = 200
    results_resp.iter_lines.return_value = [
        json.dumps(r).encode() for r in (results or [])
    ]
    return status_resp, results_resp


SAMPLE_RESULT_SPEC = {
    "custom_id": "FEAT-001-review-spec",
    "result": {
        "type": "succeeded",
        "message": {
            "content": [{"type": "text", "text": "## Review: spec\n\n### Summary\nVerdict: APPROVED\n"}]
        }
    }
}

SAMPLE_RESULT_QUALITY = {
    "custom_id": "FEAT-001-review-quality",
    "result": {
        "type": "succeeded",
        "message": {
            "content": [{"type": "text", "text": "## Review: quality\n\n### Summary\nVerdict: CHANGES_REQUESTED\n"}]
        }
    }
}


def test_poll_returns_consolidated_on_success():
    """When batch ends successfully, returns dict with reviews and consolidated_verdict."""
    from scripts.implementer.batch_review_poll import poll_and_consolidate

    status_resp, results_resp = _make_mock_response("ended", [SAMPLE_RESULT_SPEC, SAMPLE_RESULT_QUALITY])

    with patch("requests.get", side_effect=[status_resp, results_resp]):
        result = poll_and_consolidate(
            batch_id="msgbatch_test",
            ticket_id="FEAT-001",
            base_url="https://api.anthropic.com",
            api_key="sk-test",
            timeout=10,
            interval=1,
        )

    assert result["ticket_id"] == "FEAT-001"
    assert len(result["reviews"]) == 2
    assert result["consolidated_verdict"] in ("APPROVED", "CHANGES_REQUESTED")
    assert result["batch_id"] == "msgbatch_test"


def test_poll_timeout_raises():
    """When batch never ends within timeout, raises TimeoutError."""
    from scripts.implementer.batch_review_poll import poll_and_consolidate

    in_progress_resp = MagicMock()
    in_progress_resp.status_code = 200
    in_progress_resp.json.return_value = {"processing_status": "in_progress", "id": "msgbatch_test"}

    with patch("requests.get", return_value=in_progress_resp), \
         patch("time.sleep"):
        with pytest.raises(TimeoutError):
            poll_and_consolidate(
                batch_id="msgbatch_test",
                ticket_id="FEAT-001",
                base_url="https://api.anthropic.com",
                api_key="sk-test",
                timeout=2,
                interval=1,
            )


def test_consolidated_verdict_changes_if_any_requests_changes():
    """consolidated_verdict is CHANGES_REQUESTED if any review requests changes."""
    from scripts.implementer.batch_review_poll import consolidate_results

    reviews = [
        {"focus": "spec", "verdict": "APPROVED", "findings": []},
        {"focus": "quality", "verdict": "CHANGES_REQUESTED", "findings": []},
    ]
    result = consolidate_results("FEAT-001", "msgbatch_test", reviews)
    assert result["consolidated_verdict"] == "CHANGES_REQUESTED"


def test_consolidated_verdict_approved_if_all_approved():
    """consolidated_verdict is APPROVED only when all reviews approve."""
    from scripts.implementer.batch_review_poll import consolidate_results

    reviews = [
        {"focus": "spec", "verdict": "APPROVED", "findings": []},
        {"focus": "quality", "verdict": "APPROVED", "findings": []},
    ]
    result = consolidate_results("FEAT-001", "msgbatch_test", reviews)
    assert result["consolidated_verdict"] == "APPROVED"


def test_poll_errored_raises_immediately():
    """When batch status is 'errored', raises RuntimeError immediately (no timeout wait)."""
    from scripts.implementer.batch_review_poll import poll_and_consolidate

    errored_resp = MagicMock()
    errored_resp.status_code = 200
    errored_resp.json.return_value = {"processing_status": "errored", "id": "msgbatch_test"}

    with patch("requests.get", return_value=errored_resp), \
         patch("time.sleep") as mock_sleep:
        with pytest.raises(RuntimeError, match="errored"):
            poll_and_consolidate(
                batch_id="msgbatch_test",
                ticket_id="FEAT-001",
                base_url="https://api.anthropic.com",
                api_key="sk-test",
                timeout=300,
                interval=30,
            )
        # Must NOT have slept — should exit immediately
        mock_sleep.assert_not_called()
