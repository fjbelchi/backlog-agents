#!/usr/bin/env python3
"""Generate a detailed cost analytics report from the usage ledger.

Complements cost_guard.py (threshold checks) with breakdown analytics
for weekly reviews and optimization decisions.

Usage:
    python scripts/ops/cost_report.py --ledger .backlog-ops/usage-ledger.jsonl
    python scripts/ops/cost_report.py --ledger .backlog-ops/usage-ledger.jsonl --days 7
    python scripts/ops/cost_report.py --ledger .backlog-ops/usage-ledger.jsonl --json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path


def parse_ts(ts: str) -> datetime:
    """Parse ISO timestamp."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Cost analytics report")
    parser.add_argument("--ledger", required=True, help="Path to usage-ledger.jsonl")
    parser.add_argument("--days", type=int, default=0, help="Filter to last N days (0=all)")
    parser.add_argument("--json", dest="json_out", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    ledger = Path(args.ledger)
    if not ledger.exists():
        raise SystemExit(f"Ledger not found: {ledger}")

    entries = []
    cutoff = None
    if args.days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if cutoff and "timestamp" in entry:
            ts = parse_ts(entry["timestamp"])
            if ts < cutoff:
                continue
        entries.append(entry)

    if not entries:
        print("No entries found.")
        return 0

    # Aggregations
    total_cost = sum(float(e.get("cost_usd", 0)) for e in entries)
    total_input = sum(int(e.get("input_tokens", 0)) for e in entries)
    total_output = sum(int(e.get("output_tokens", 0)) for e in entries)
    total_cached = sum(int(e.get("cached_input_tokens", 0)) for e in entries)

    by_model: dict[str, float] = defaultdict(float)
    by_workflow: dict[str, float] = defaultdict(float)
    by_phase: dict[str, float] = defaultdict(float)
    cache_hits = 0
    cache_misses = 0
    batch_count = 0
    escalations = 0

    for e in entries:
        alias = e.get("model_alias", "unknown")
        by_model[alias] += float(e.get("cost_usd", 0))
        by_workflow[e.get("workflow", "unknown")] += float(e.get("cost_usd", 0))
        by_phase[e.get("phase", "unknown")] += float(e.get("cost_usd", 0))

        if e.get("cache_hit"):
            cache_hits += 1
        else:
            cache_misses += 1

        if e.get("batch_job_id"):
            batch_count += 1

        if e.get("escalation_reason"):
            escalations += 1

    cache_rate = cache_hits / max(1, cache_hits + cache_misses) * 100
    batch_rate = batch_count / max(1, len(entries)) * 100
    escalation_rate = escalations / max(1, len(entries)) * 100

    report = {
        "period": f"Last {args.days} days" if args.days else "All time",
        "total_requests": len(entries),
        "total_cost_usd": round(total_cost, 4),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_cached_input_tokens": total_cached,
        "cache_hit_rate_pct": round(cache_rate, 1),
        "batch_rate_pct": round(batch_rate, 1),
        "escalation_rate_pct": round(escalation_rate, 1),
        "cost_by_model": {k: round(v, 4) for k, v in sorted(by_model.items(), key=lambda x: -x[1])},
        "cost_by_workflow": {k: round(v, 4) for k, v in sorted(by_workflow.items(), key=lambda x: -x[1])},
        "cost_by_phase": {k: round(v, 4) for k, v in sorted(by_phase.items(), key=lambda x: -x[1])},
        "kpi_status": {
            "cache_hit_rate": "OK" if cache_rate >= 60 else "NEEDS_IMPROVEMENT",
            "cheap_model_ratio": "OK" if by_model.get("cheap", 0) / max(total_cost, 0.01) >= 0.5 else "NEEDS_IMPROVEMENT",
            "escalation_rate": "OK" if escalation_rate < 5 else "WARNING",
            "batch_utilization": "OK" if batch_rate >= 30 else "NEEDS_IMPROVEMENT",
        },
    }

    if args.json_out:
        print(json.dumps(report, indent=2))
    else:
        print(f"═══ COST REPORT ({report['period']}) ═══")
        print(f"Requests:    {report['total_requests']}")
        print(f"Total Cost:  ${report['total_cost_usd']}")
        print(f"Tokens:      {total_input:,} in / {total_output:,} out / {total_cached:,} cached")
        print(f"Cache Hit:   {report['cache_hit_rate_pct']}%")
        print(f"Batch Rate:  {report['batch_rate_pct']}%")
        print(f"Escalations: {report['escalation_rate_pct']}%")
        print()
        print("─── Cost by Model ───")
        for model, cost in report["cost_by_model"].items():
            print(f"  {model:20s} ${cost}")
        print()
        print("─── Cost by Workflow ───")
        for wf, cost in report["cost_by_workflow"].items():
            print(f"  {wf:20s} ${cost}")
        print()
        print("─── KPI Status ───")
        for kpi, status in report["kpi_status"].items():
            indicator = "✓" if status == "OK" else "⚠"
            print(f"  {indicator} {kpi}: {status}")
        print("═══════════════════════════════")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
