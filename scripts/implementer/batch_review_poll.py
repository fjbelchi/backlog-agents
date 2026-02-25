#!/usr/bin/env python3
"""Poll Anthropic Batch API for Gate 4 review results and consolidate.

Usage:
    python3 scripts/implementer/batch_review_poll.py \
        --batch-id msgbatch_xxx \
        --ticket-id FEAT-001 \
        --timeout 300 \
        --interval 30

Output (stdout): JSON with ticket_id, reviews[], consolidated_verdict, batch_id
Exit codes: 0=results ready, 1=timeout or API error
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

BATCH_API_PATH = "/v1/messages/batches"
ANTHROPIC_BETA_HEADER = "prompt-caching-2024-07-31"


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "anthropic-beta": ANTHROPIC_BETA_HEADER,
    }


def _extract_verdict(text: str) -> str:
    """Parse APPROVED or CHANGES_REQUESTED from reviewer output text."""
    upper = text.upper()
    if "CHANGES_REQUESTED" in upper:
        return "CHANGES_REQUESTED"
    if "APPROVED" in upper:
        return "APPROVED"
    return "CHANGES_REQUESTED"  # conservative default


def _parse_result(result_line: dict) -> dict:
    """Convert one batch result line into a review dict."""
    custom_id = result_line.get("custom_id", "")
    focus = custom_id.split("-review-")[-1] if "-review-" in custom_id else "unknown"

    result = result_line.get("result", {})
    if result.get("type") != "succeeded":
        return {"focus": focus, "verdict": "CHANGES_REQUESTED", "findings": [],
                "error": result.get("error", {}).get("message", "batch request failed")}

    content = result.get("message", {}).get("content", [])
    text = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
    verdict = _extract_verdict(text)

    return {"focus": focus, "verdict": verdict, "findings": [], "raw": text}


def consolidate_results(ticket_id: str, batch_id: str, reviews: list[dict]) -> dict:
    """Merge per-focus reviews into final consolidated result."""
    all_approved = all(r["verdict"] == "APPROVED" for r in reviews)
    return {
        "ticket_id": ticket_id,
        "reviews": reviews,
        "consolidated_verdict": "APPROVED" if all_approved else "CHANGES_REQUESTED",
        "batch_id": batch_id,
        "cost_savings_pct": 50,
    }


def poll_and_consolidate(
    batch_id: str,
    ticket_id: str,
    base_url: str,
    api_key: str,
    timeout: int = 300,
    interval: int = 30,
) -> dict:
    """Poll until batch ends or timeout exceeded.

    Raises TimeoutError on timeout.
    Raises RuntimeError on API error.
    """
    base = base_url.rstrip("/")
    status_url = f"{base}{BATCH_API_PATH}/{batch_id}"
    results_url = f"{base}{BATCH_API_PATH}/{batch_id}/results"
    hdrs = _headers(api_key)

    elapsed = 0
    while elapsed < timeout:
        resp = requests.get(status_url, headers=hdrs, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"Status check failed: {resp.status_code} {resp.text[:200]}")

        data = resp.json()
        if data.get("processing_status") == "ended":
            # Fetch results
            rresp = requests.get(results_url, headers=hdrs, timeout=60, stream=True)
            if rresp.status_code != 200:
                raise RuntimeError(f"Results fetch failed: {rresp.status_code}")
            reviews = [_parse_result(json.loads(line)) for line in rresp.iter_lines() if line]
            return consolidate_results(ticket_id, batch_id, reviews)

        if data.get("processing_status") == "errored":
            raise RuntimeError(f"Batch {batch_id} failed with status 'errored'")

        time.sleep(interval)
        elapsed += interval

    raise TimeoutError(f"Batch {batch_id} did not complete within {timeout}s")


def main() -> int:
    ap = argparse.ArgumentParser(description="Poll Batch API for review results")
    ap.add_argument("--batch-id", required=True)
    ap.add_argument("--ticket-id", required=True)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--interval", type=int, default=30)
    ap.add_argument("--base-url", default=os.environ.get("LITELLM_BASE_URL", "https://api.anthropic.com"))
    ap.add_argument("--api-key-env", default="ANTHROPIC_API_KEY")
    a = ap.parse_args()

    api_key = os.environ.get(a.api_key_env, "")
    if not api_key:
        print(f"Error: env var {a.api_key_env} not set", file=sys.stderr)
        return 1

    try:
        result = poll_and_consolidate(
            batch_id=a.batch_id,
            ticket_id=a.ticket_id,
            base_url=a.base_url,
            api_key=api_key,
            timeout=a.timeout,
            interval=a.interval,
        )
        print(json.dumps(result))
        return 0
    except TimeoutError as e:
        print(f"Timeout: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
