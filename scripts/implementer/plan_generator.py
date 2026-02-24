#!/usr/bin/env python3
"""
plan_generator.py — Deterministic Gate 1 replacement.
Reads a ticket markdown file and emits ## Implementation Plan to stdout.
Cost: $0. No LLM calls.
"""
import argparse, re, sys
from pathlib import Path

def parse_affected_files(body: str) -> list[dict]:
    rows = []
    in_table = False
    for line in body.splitlines():
        if "## Affected Files" in line:
            in_table = True
            continue
        if in_table:
            if line.startswith("##"):
                break
            if line.startswith("|") and not re.match(r"\|[-| ]+\|", line):
                parts = [p.strip() for p in line.strip("|").split("|")]
                if len(parts) >= 3 and parts[0] not in ("File", "file"):
                    rows.append({"path": parts[0], "action": parts[1], "desc": parts[2]})
    return rows

def parse_acceptance_criteria(body: str) -> list[str]:
    return re.findall(r"- \[[ x]\] (AC-\d+[^:\n]*:[^\n]+)", body)

def generate_plan(files: list[dict], acs: list[str]) -> str:
    lines = ["## Implementation Plan"]
    # Order: create → modify → delete
    ordered = (
        [f for f in files if f["action"] == "create"] +
        [f for f in files if f["action"] == "modify"] +
        [f for f in files if f["action"] == "delete"]
    )
    for f in ordered:
        lines.append(f"- {f['action'].capitalize()} `{f['path']}`: {f['desc']}")
    if acs:
        lines.append("")
        lines.append("Tests to write:")
        for ac in acs:
            lines.append(f"- {ac.strip()}")
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticket", required=True)
    args = parser.parse_args()

    path = Path(args.ticket)
    if not path.exists():
        print(f"Error: ticket file not found: {path}", file=sys.stderr)
        sys.exit(1)

    content = path.read_text()
    # Strip YAML frontmatter
    body = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)

    files = parse_affected_files(body)
    acs = parse_acceptance_criteria(body)
    print(generate_plan(files, acs))

if __name__ == "__main__":
    main()
