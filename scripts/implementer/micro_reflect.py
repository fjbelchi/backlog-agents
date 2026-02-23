#!/usr/bin/env python3
"""Rule-based playbook bullet tagging (micro-reflector). Stdlib only.

Usage: python3 micro_reflect.py --wave-results '{}' --bullets-used '[]'
"""
from __future__ import annotations
import argparse, json, sys  # noqa: E401


def reflect_wave(wave_results: dict, bullets_used: list[dict]) -> dict:
    """Tag bullets as helpful/harmful/neutral based on wave outcomes."""
    completed = set(wave_results.get("completed", []))
    failed = wave_results.get("failed", {})
    escalated = set(wave_results.get("escalated", []))
    tags, parts = [], []
    counts = {"helpful": 0, "harmful": 0, "neutral": 0}

    for b in bullets_used:
        bid, tid = b["id"], b["ticket"]
        if tid in escalated:
            tag, reason = "neutral", f"{tid} escalated"
        elif tid in completed and tid in failed:
            tag, reason = "neutral", f"{tid} completed with retry"
        elif tid in failed:
            tag, reason = "harmful", f"{tid} failed {failed[tid]}"
        elif tid in completed:
            tag, reason = "helpful", f"{tid} passed"
        else:
            tag, reason = "neutral", f"{tid} unknown outcome"
        tags.append({"id": bid, "tag": tag})
        counts[tag] += 1
        parts.append(reason)

    if parts:
        summary = " + ".join(f"{v} {k}" for k, v in counts.items() if v)
        reasoning = f"{summary} ({', '.join(parts)})"
    else:
        reasoning = "no bullets to tag"
    return {"bullet_tags": tags, "new_bullets": [], "reasoning": reasoning}


def main() -> int:
    ap = argparse.ArgumentParser(description="Micro-reflector for bullet tagging.")
    ap.add_argument("--wave-results", required=True)
    ap.add_argument("--bullets-used", required=True)
    a = ap.parse_args()
    try:
        wr = json.loads(a.wave_results)
        bu = json.loads(a.bullets_used)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON: {e}", file=sys.stderr); return 1
    print(json.dumps(reflect_wave(wr, bu), indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
