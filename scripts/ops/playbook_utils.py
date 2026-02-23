#!/usr/bin/env python3
"""ACE-inspired evolving playbook utilities.

Manages a markdown-based playbook file with scored strategy bullets.
Supports parsing, counter updates, bullet curation (add/archive/prune),
statistics, and relevance-based selection for ticket context injection.

Playbook format::

    ## Strategies & Insights
    [strat-00001] helpful=12 harmful=1 :: Always write failing test before implementation

    ## Common Mistakes
    [err-00001] helpful=5 harmful=0 :: useRef hooks must reset on dependency changes

Usage:
    python scripts/ops/playbook_utils.py stats <path>
    python scripts/ops/playbook_utils.py prune <path>
    python scripts/ops/playbook_utils.py add <path> <section> <content>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Regex for a single playbook bullet line.
BULLET_RE = re.compile(r"\[([^\]]+)\]\s*helpful=(\d+)\s*harmful=(\d+)\s*::\s*(.*)")

# Map section header text to bullet-ID prefix.
SECTION_PREFIXES: dict[str, str] = {
    "Strategies & Insights": "strat",
    "Common Mistakes": "err",
    "Cost Patterns": "cost",
    "Review Patterns": "rev",
    "Archived": "archived",
}


def parse_bullet(line: str) -> dict | None:
    """Parse a single playbook bullet line.

    Returns a dict with keys ``id``, ``helpful``, ``harmful``, ``content``,
    ``raw_line`` -- or ``None`` if the line is not a valid bullet.
    """
    m = BULLET_RE.match(line.strip())
    if not m:
        return None
    return {
        "id": m.group(1),
        "helpful": int(m.group(2)),
        "harmful": int(m.group(3)),
        "content": m.group(4),
        "raw_line": line.strip(),
    }


def parse_playbook(path: str) -> list[dict]:
    """Read a playbook file and parse all bullet lines.

    Each returned dict has the standard bullet fields plus a ``section`` field
    taken from the most recent ``## Header`` above it.  Returns an empty list
    if the file does not exist.
    """
    p = Path(path)
    if not p.exists():
        return []

    bullets: list[dict] = []
    current_section: str | None = None

    for line in p.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current_section = stripped[3:].strip()
            continue
        bullet = parse_bullet(stripped)
        if bullet is not None and current_section is not None:
            bullet["section"] = current_section
            bullets.append(bullet)

    return bullets


def update_counters(path: str, tags: list[dict]) -> int:
    """Increment helpful/harmful counters for the given bullet IDs.

    *tags* is a list of ``{"id": "<bullet-id>", "tag": "helpful|harmful|neutral"}``.
    For ``neutral`` the bullet is matched but counters are unchanged.

    Returns the number of bullets that were successfully matched.
    """
    p = Path(path)
    lines = p.read_text(encoding="utf-8").splitlines()
    tag_map: dict[str, str] = {t["id"]: t["tag"] for t in tags}
    matched = 0

    new_lines: list[str] = []
    for line in lines:
        bullet = parse_bullet(line)
        if bullet and bullet["id"] in tag_map:
            tag = tag_map[bullet["id"]]
            h = bullet["helpful"]
            d = bullet["harmful"]
            if tag == "helpful":
                h += 1
            elif tag == "harmful":
                d += 1
            # neutral -> no change
            new_line = f'[{bullet["id"]}] helpful={h} harmful={d} :: {bullet["content"]}'
            new_lines.append(new_line)
            matched += 1
        else:
            new_lines.append(line)

    p.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return matched


def _max_id_for_prefix(bullets: list[dict], prefix: str) -> int:
    """Return the highest numeric suffix among bullets matching *prefix*."""
    max_num = 0
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    for b in bullets:
        m = pattern.match(b["id"])
        if m:
            max_num = max(max_num, int(m.group(1)))
    return max_num


def add_bullet(path: str, section: str, content: str) -> str:
    """Add a new bullet to the given section, auto-generating its ID.

    If the section header does not exist in the file it is created at the end.
    Returns the newly assigned bullet ID (e.g. ``strat-00004``).
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines()

    prefix = SECTION_PREFIXES.get(section)
    if prefix is None:
        raise ValueError(f"Unknown section: {section!r}")

    # Scan ALL bullets in the file to determine max id for this prefix.
    all_bullets = parse_playbook(path)
    next_num = _max_id_for_prefix(all_bullets, prefix) + 1
    new_id = f"{prefix}-{next_num:05d}"
    new_line = f"[{new_id}] helpful=0 harmful=0 :: {content}"

    header = f"## {section}"
    if header in text:
        # Find the header line and insert the bullet after the last bullet
        # in that section (or right after the header if section is empty).
        header_idx: int | None = None
        insert_idx: int | None = None
        for i, line in enumerate(lines):
            if line.strip() == header:
                header_idx = i
                insert_idx = i + 1  # default: right after header
                continue
            if header_idx is not None and i > header_idx:
                if line.strip().startswith("## "):
                    # Reached next section -- stop.
                    break
                bullet = parse_bullet(line)
                if bullet is not None:
                    insert_idx = i + 1

        if insert_idx is not None:
            lines.insert(insert_idx, new_line)
    else:
        # Section doesn't exist yet -- append at end of file.
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(header)
        lines.append(new_line)

    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return new_id


def archive_bullet(path: str, bullet_id: str, reason: str) -> bool:
    """Move a bullet to the ``## Archived`` section.

    Appends ``(archived: <reason>)`` to the bullet content.
    Creates the Archived section if it does not exist.
    Returns ``True`` if the bullet was found and archived, ``False`` otherwise.
    """
    p = Path(path)
    lines = p.read_text(encoding="utf-8").splitlines()

    # Find and remove the bullet.
    removed_bullet: dict | None = None
    new_lines: list[str] = []
    for line in lines:
        bullet = parse_bullet(line)
        if bullet and bullet["id"] == bullet_id:
            removed_bullet = bullet
            continue  # skip -- will re-add in Archived
        new_lines.append(line)

    if removed_bullet is None:
        return False

    archived_line = (
        f'[{removed_bullet["id"]}] helpful={removed_bullet["helpful"]} '
        f'harmful={removed_bullet["harmful"]} :: '
        f'{removed_bullet["content"]} (archived: {reason})'
    )

    # Find or create ## Archived section.
    archive_header = "## Archived"
    if archive_header in "\n".join(new_lines):
        # Append after the last line in the Archived section.
        header_idx: int | None = None
        insert_idx: int | None = None
        for i, line in enumerate(new_lines):
            if line.strip() == archive_header:
                header_idx = i
                insert_idx = i + 1
                continue
            if header_idx is not None and i > header_idx:
                if line.strip().startswith("## "):
                    break
                if parse_bullet(line) is not None or line.strip():
                    insert_idx = i + 1
        if insert_idx is not None:
            new_lines.insert(insert_idx, archived_line)
    else:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append(archive_header)
        new_lines.append(archived_line)

    p.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return True


def prune_playbook(path: str, min_uses: int = 5) -> list[str]:
    """Archive bullets where harmful > helpful and total usage > *min_uses*.

    Each pruned bullet gets the reason ``auto-pruned: harmful>helpful``.
    Returns a list of pruned bullet IDs.
    """
    bullets = parse_playbook(path)
    pruned_ids: list[str] = []
    for b in bullets:
        total = b["helpful"] + b["harmful"]
        if b["harmful"] > b["helpful"] and total > min_uses:
            archive_bullet(path, b["id"], "auto-pruned: harmful>helpful")
            pruned_ids.append(b["id"])
    return pruned_ids


def get_stats(path: str) -> dict:
    """Return aggregate statistics about the playbook.

    Keys: ``total``, ``high_performing``, ``problematic``, ``unused``,
    ``by_section`` (section name -> count).

    Definitions:
    - high_performing: helpful > 5 AND harmful < 2
    - problematic: harmful >= helpful AND (helpful + harmful) > 0
    - unused: helpful == 0 AND harmful == 0
    """
    bullets = parse_playbook(path)
    high_performing = 0
    problematic = 0
    unused = 0
    by_section: dict[str, int] = {}

    for b in bullets:
        sec = b["section"]
        by_section[sec] = by_section.get(sec, 0) + 1
        total = b["helpful"] + b["harmful"]
        if b["helpful"] > 5 and b["harmful"] < 2:
            high_performing += 1
        if b["harmful"] >= b["helpful"] and total > 0:
            problematic += 1
        if total == 0:
            unused += 1

    return {
        "total": len(bullets),
        "high_performing": high_performing,
        "problematic": problematic,
        "unused": unused,
        "by_section": by_section,
    }


def select_relevant(
    path: str,
    ticket_type: str,
    tags: list[str],
    affected_files: list[str],
    k: int = 10,
) -> list[dict]:
    """Select the top-K most relevant bullets for a given ticket context.

    Prioritization by ticket type:
    - BUG  -> "Common Mistakes" first
    - FEAT -> "Strategies & Insights" first
    - SEC  -> "Review Patterns" first

    Within each tier, bullets are sorted by helpful-to-harmful ratio
    (descending).  Bullets with harmful >= helpful are deprioritized.
    """
    bullets = parse_playbook(path)
    if not bullets:
        return []

    priority_section: str | None = {
        "BUG": "Common Mistakes",
        "FEAT": "Strategies & Insights",
        "SEC": "Review Patterns",
    }.get(ticket_type.upper())

    def score(b: dict) -> tuple[int, float]:
        """Return (priority_tier, ratio) for sorting.

        Higher priority_tier and higher ratio = more relevant.
        """
        tier = 1 if priority_section and b["section"] == priority_section else 0
        total = b["helpful"] + b["harmful"]
        if total == 0:
            ratio = 0.0
        else:
            ratio = b["helpful"] / total
        return (tier, ratio)

    bullets.sort(key=score, reverse=True)
    return bullets[:k]


def main() -> int:
    """CLI entry point for playbook utilities."""
    if len(sys.argv) < 3:
        print(
            "Usage:\n"
            "  playbook_utils.py stats <path>\n"
            "  playbook_utils.py prune <path>\n"
            "  playbook_utils.py add <path> <section> <content>",
            file=sys.stderr,
        )
        return 1

    cmd = sys.argv[1]
    path = sys.argv[2]

    if cmd == "stats":
        import json

        stats = get_stats(path)
        print(json.dumps(stats, indent=2))
        return 0

    if cmd == "prune":
        pruned = prune_playbook(path)
        if pruned:
            print(f"Pruned {len(pruned)} bullet(s): {', '.join(pruned)}")
        else:
            print("No bullets pruned.")
        return 0

    if cmd == "add":
        if len(sys.argv) < 5:
            print("Usage: playbook_utils.py add <path> <section> <content>", file=sys.stderr)
            return 1
        section = sys.argv[3]
        content = sys.argv[4]
        new_id = add_bullet(path, section, content)
        print(f"Added: {new_id}")
        return 0

    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
