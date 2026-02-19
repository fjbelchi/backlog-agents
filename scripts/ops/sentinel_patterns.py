#!/usr/bin/env python3
"""Pattern ledger for backlog-sentinel continuous learning.

Tracks recurring error patterns across commits. Escalates to codeRules
when occurrence threshold is exceeded.

Usage:
    python scripts/ops/sentinel_patterns.py --findings findings.json
    python scripts/ops/sentinel_patterns.py --findings findings.json --propose-rules
"""

from __future__ import annotations
import argparse, json, re
from datetime import datetime, timezone
from pathlib import Path


LEDGER_PATH = Path(".backlog-ops/sentinel-patterns.json")


def load_ledger() -> dict:
    if not LEDGER_PATH.exists():
        return {
            "version": "1.0",
            "patterns": [],
            "thresholds": {
                "recurring": 2,
                "escalateToSoftGate": 3,
                "escalateToHardGate": 5,
            },
        }
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def save_ledger(ledger: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower())[:60].strip("-")


def similarity(a: str, b: str) -> float:
    """Simple word-overlap similarity (Jaccard index)."""
    wa = set(re.findall(r"\w+", a.lower()))
    wb = set(re.findall(r"\w+", b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def update_ledger(findings: list[dict], thresholds: dict) -> dict:
    """Match findings to patterns, increment counts, return escalated patterns."""
    ledger = load_ledger()
    if thresholds:
        ledger["thresholds"].update(thresholds)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    escalated = []

    for finding in findings:
        desc = finding.get("description", "")
        matched = False
        for pattern in ledger["patterns"]:
            if similarity(desc, pattern["description"]) > 0.6:
                pattern["occurrences"] += 1
                pattern["last_seen"] = today
                if finding.get("file") not in pattern["files"]:
                    pattern["files"].append(finding["file"])
                matched = True
                # Check escalation thresholds
                t = ledger["thresholds"]
                soft = t.get("escalateToSoftGate", 3)
                if (pattern["occurrences"] >= soft
                        and not pattern.get("escalated_to_rules")):
                    escalated.append(pattern)
                break
        if not matched:
            ledger["patterns"].append({
                "id": slugify(desc),
                "description": desc,
                "category": finding.get("category", "bug"),
                "occurrences": 1,
                "files": [finding.get("file", "unknown")],
                "first_seen": today,
                "last_seen": today,
                "escalated_to_rules": False,
            })

    save_ledger(ledger)
    return {"ledger": ledger, "escalated": escalated}


def propose_rules(escalated: list[dict], rules_file: str) -> None:
    """Append escalated patterns to codeRules file as soft gates."""
    if not escalated:
        return
    rules_path = Path(rules_file)
    if not rules_path.exists():
        print(f"codeRules file not found: {rules_file} — skipping rule proposal")
        return
    additions = "\n".join(
        f"- [ ] {p['description']}\n"
        f"      [auto-added by sentinel, {p['occurrences']}x — {p['last_seen']}]"
        for p in escalated
    )
    content = rules_path.read_text(encoding="utf-8")
    if "## Soft Gates" in content:
        content = content.replace(
            "## Soft Gates",
            f"## Soft Gates\n{additions}\n",
            1,
        )
    else:
        content += f"\n## Soft Gates (auto-added by sentinel)\n{additions}\n"
    rules_path.write_text(content, encoding="utf-8")
    print(f"Added {len(escalated)} pattern(s) to {rules_file}")
    # Mark escalated patterns as done
    ledger = load_ledger()
    for ep in escalated:
        for p in ledger["patterns"]:
            if p["id"] == ep["id"]:
                p["escalated_to_rules"] = True
    save_ledger(ledger)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sentinel pattern ledger")
    parser.add_argument("--findings", required=True, help="JSON file with findings")
    parser.add_argument("--config", default="backlog.config.json")
    parser.add_argument(
        "--propose-rules",
        action="store_true",
        help="Auto-add escalated patterns to codeRules.source",
    )
    args = parser.parse_args()

    findings_raw = json.loads(Path(args.findings).read_text(encoding="utf-8"))
    findings: list[dict] = (
        findings_raw.get("findings", [])
        if isinstance(findings_raw, dict)
        else findings_raw
    )

    config: dict = {}
    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    except Exception:
        pass

    thresholds = config.get("sentinel", {}).get("patternThresholds", {})
    result = update_ledger(findings, thresholds)

    print(f"Patterns tracked: {len(result['ledger']['patterns'])}")
    print(f"Escalated:        {len(result['escalated'])}")

    if args.propose_rules and result["escalated"]:
        rules_file = config.get("codeRules", {}).get("source", ".claude/code-rules.md")
        propose_rules(result["escalated"], rules_file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
