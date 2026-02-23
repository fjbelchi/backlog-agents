#!/usr/bin/env python3
"""Template-based conventional commit message generation.

Produces commit messages in the format:
    {type}({area}): implement {ticket_id}[ — {summary}]

    Closes: {ticket_id}

Only uses Python stdlib -- no external dependencies.

Usage:
    python3 commit_msg.py --type feat --area auth --ticket FEAT-042 --summary "Add OAuth2"
"""

from __future__ import annotations

import argparse
import sys


def generate_commit_msg(
    type: str,
    area: str,
    ticket_id: str,
    summary: str = "",
) -> str:
    """Generate a conventional commit message from template parameters.

    Args:
        type: Commit type (feat, fix, chore, etc.). Defaults to 'feat' if empty.
        area: Scope/area of the change. May be empty.
        ticket_id: Ticket identifier (e.g. FEAT-042).
        summary: Optional one-line summary appended after em-dash.

    Returns:
        Multi-line commit message string with Closes trailer.
    """
    effective_type = type if type else "feat"

    subject = f"{effective_type}({area}): implement {ticket_id}"
    if summary:
        subject += f" \u2014 {summary}"

    return f"{subject}\n\nCloses: {ticket_id}"


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate a conventional commit message.",
    )
    parser.add_argument("--type", default="feat", help="Commit type (feat, fix, etc.)")
    parser.add_argument("--area", default="", help="Scope/area of the change")
    parser.add_argument("--ticket", required=True, help="Ticket ID (e.g. FEAT-042)")
    parser.add_argument("--summary", default="", help="Optional one-line summary")
    args = parser.parse_args()

    msg = generate_commit_msg(
        type=args.type,
        area=args.area,
        ticket_id=args.ticket,
        summary=args.summary,
    )
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
