#!/usr/bin/env python3
"""Simple budget guard from usage ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--warn", type=float, default=0.70)
    parser.add_argument("--hard-stop", type=float, default=1.00)
    parser.add_argument("--budget", type=float, default=1000.0)
    args = parser.parse_args()

    ledger = Path(args.ledger)
    if not ledger.exists():
        raise SystemExit(f"ledger not found: {ledger}")

    total = 0.0
    for lineno, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            import sys
            print(f"warning: skipping malformed ledger entry at line {lineno}", file=sys.stderr)
            continue
        total += float(entry.get("cost_usd", 0))

    ratio = total / args.budget if args.budget else 0
    state = "ok"
    if ratio >= args.hard_stop:
        state = "hard-stop"
    elif ratio >= args.warn:
        state = "warning"

    print(json.dumps({"cost_usd": round(total, 4), "budget": args.budget, "ratio": round(ratio, 4), "state": state}, indent=2))
    return 0 if state != "hard-stop" else 1


if __name__ == "__main__":
    raise SystemExit(main())
