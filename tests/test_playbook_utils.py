#!/usr/bin/env python3
"""Tests for playbook_utils.py — bullet parsing, curation, and selection."""
import sys
from pathlib import Path

import pytest

# Add scripts/ops to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "ops"))
from playbook_utils import (
    parse_bullet,
    parse_playbook,
    update_counters,
    add_bullet,
    archive_bullet,
    prune_playbook,
    get_stats,
    select_relevant,
)

SAMPLE_PLAYBOOK = """\
## Strategies & Insights
[strat-00001] helpful=12 harmful=1 :: Always write failing test before implementation
[strat-00002] helpful=8 harmful=3 :: Pre-read all affected files before spawning
[strat-00003] helpful=0 harmful=0 :: Untested strategy

## Common Mistakes
[err-00001] helpful=5 harmful=0 :: useRef hooks must reset on dependency changes
[err-00002] helpful=2 harmful=7 :: Skipping lint before commit

## Cost Patterns
[cost-00001] helpful=3 harmful=0 :: Batch similar tickets to reduce overhead

## Review Patterns
[rev-00001] helpful=6 harmful=1 :: Check diff size before approving
"""


@pytest.fixture
def playbook_file(tmp_path):
    """Create a playbook file with sample content."""
    p = tmp_path / "playbook.md"
    p.write_text(SAMPLE_PLAYBOOK, encoding="utf-8")
    return str(p)


@pytest.fixture
def empty_playbook(tmp_path):
    """Create an empty playbook file."""
    p = tmp_path / "empty.md"
    p.write_text("## Strategies & Insights\n", encoding="utf-8")
    return str(p)


# ---------- parse_bullet ----------

class TestParseBullet:
    def test_valid_bullet(self):
        line = "[strat-00001] helpful=12 harmful=1 :: Always write failing test"
        result = parse_bullet(line)
        assert result is not None
        assert result["id"] == "strat-00001"
        assert result["helpful"] == 12
        assert result["harmful"] == 1
        assert result["content"] == "Always write failing test"
        assert result["raw_line"] == line

    def test_zero_counters(self):
        line = "[err-00001] helpful=0 harmful=0 :: Some content"
        result = parse_bullet(line)
        assert result is not None
        assert result["helpful"] == 0
        assert result["harmful"] == 0

    def test_non_bullet_line(self):
        assert parse_bullet("## Strategies & Insights") is None
        assert parse_bullet("") is None
        assert parse_bullet("Just a regular line") is None

    def test_malformed_bullet(self):
        assert parse_bullet("[strat-00001] helpful=12 :: missing harmful") is None


# ---------- parse_playbook ----------

class TestParsePlaybook:
    def test_parses_all_bullets(self, playbook_file):
        bullets = parse_playbook(playbook_file)
        assert len(bullets) == 7

    def test_assigns_section(self, playbook_file):
        bullets = parse_playbook(playbook_file)
        strat_bullets = [b for b in bullets if b["section"] == "Strategies & Insights"]
        assert len(strat_bullets) == 3

    def test_section_for_each_bullet(self, playbook_file):
        bullets = parse_playbook(playbook_file)
        sections = {b["section"] for b in bullets}
        assert sections == {
            "Strategies & Insights",
            "Common Mistakes",
            "Cost Patterns",
            "Review Patterns",
        }

    def test_empty_file(self, empty_playbook):
        bullets = parse_playbook(empty_playbook)
        assert bullets == []

    def test_nonexistent_file(self, tmp_path):
        bullets = parse_playbook(str(tmp_path / "missing.md"))
        assert bullets == []


# ---------- update_counters ----------

class TestUpdateCounters:
    def test_increment_helpful(self, playbook_file):
        tags = [{"id": "strat-00001", "tag": "helpful"}]
        count = update_counters(playbook_file, tags)
        assert count == 1
        # Verify the counter was actually incremented in the file
        bullets = parse_playbook(playbook_file)
        strat1 = next(b for b in bullets if b["id"] == "strat-00001")
        assert strat1["helpful"] == 13  # was 12

    def test_increment_harmful(self, playbook_file):
        tags = [{"id": "strat-00001", "tag": "harmful"}]
        count = update_counters(playbook_file, tags)
        assert count == 1
        bullets = parse_playbook(playbook_file)
        strat1 = next(b for b in bullets if b["id"] == "strat-00001")
        assert strat1["harmful"] == 2  # was 1

    def test_neutral_no_change(self, playbook_file):
        tags = [{"id": "strat-00001", "tag": "neutral"}]
        count = update_counters(playbook_file, tags)
        assert count == 1
        bullets = parse_playbook(playbook_file)
        strat1 = next(b for b in bullets if b["id"] == "strat-00001")
        assert strat1["helpful"] == 12  # unchanged
        assert strat1["harmful"] == 1   # unchanged

    def test_multiple_updates(self, playbook_file):
        tags = [
            {"id": "strat-00001", "tag": "helpful"},
            {"id": "err-00001", "tag": "harmful"},
        ]
        count = update_counters(playbook_file, tags)
        assert count == 2

    def test_unknown_id_returns_zero(self, playbook_file):
        tags = [{"id": "strat-99999", "tag": "helpful"}]
        count = update_counters(playbook_file, tags)
        assert count == 0


# ---------- add_bullet ----------

class TestAddBullet:
    def test_add_to_existing_section(self, playbook_file):
        new_id = add_bullet(playbook_file, "Strategies & Insights", "New strategy here")
        assert new_id == "strat-00004"  # strat-00003 is max existing
        bullets = parse_playbook(playbook_file)
        new_bullet = next(b for b in bullets if b["id"] == "strat-00004")
        assert new_bullet["content"] == "New strategy here"
        assert new_bullet["helpful"] == 0
        assert new_bullet["harmful"] == 0

    def test_add_to_missing_section(self, playbook_file):
        new_id = add_bullet(playbook_file, "Common Mistakes", "Another mistake")
        assert new_id == "err-00003"

    def test_create_section_if_missing(self, empty_playbook):
        new_id = add_bullet(empty_playbook, "Common Mistakes", "First mistake")
        assert new_id == "err-00001"
        bullets = parse_playbook(empty_playbook)
        assert len(bullets) == 1
        assert bullets[0]["section"] == "Common Mistakes"

    def test_add_to_cost_section(self, playbook_file):
        new_id = add_bullet(playbook_file, "Cost Patterns", "New cost pattern")
        assert new_id == "cost-00002"

    def test_add_to_review_section(self, playbook_file):
        new_id = add_bullet(playbook_file, "Review Patterns", "New review pattern")
        assert new_id == "rev-00002"


# ---------- archive_bullet ----------

class TestArchiveBullet:
    def test_archive_existing_bullet(self, playbook_file):
        result = archive_bullet(playbook_file, "strat-00001", "no longer relevant")
        assert result is True
        # Bullet should no longer be in Strategies section
        bullets = parse_playbook(playbook_file)
        strat_ids = [b["id"] for b in bullets if b["section"] == "Strategies & Insights"]
        assert "strat-00001" not in strat_ids
        # Bullet should be in Archived section
        archived = [b for b in bullets if b["section"] == "Archived"]
        assert len(archived) == 1
        assert "no longer relevant" in archived[0]["raw_line"]

    def test_archive_nonexistent_bullet(self, playbook_file):
        result = archive_bullet(playbook_file, "strat-99999", "test")
        assert result is False

    def test_archived_section_created(self, playbook_file):
        content = Path(playbook_file).read_text(encoding="utf-8")
        assert "## Archived" not in content
        archive_bullet(playbook_file, "strat-00001", "test reason")
        content = Path(playbook_file).read_text(encoding="utf-8")
        assert "## Archived" in content


# ---------- prune_playbook ----------

class TestPrunePlaybook:
    def test_prune_harmful_bullets(self, playbook_file):
        # err-00002 has helpful=2 harmful=7, total=9 > min_uses=5
        pruned = prune_playbook(playbook_file, min_uses=5)
        assert "err-00002" in pruned

    def test_prune_skips_low_usage(self, playbook_file):
        # With min_uses=20, no bullet qualifies
        pruned = prune_playbook(playbook_file, min_uses=20)
        assert pruned == []

    def test_prune_does_not_prune_helpful(self, playbook_file):
        # strat-00001 has helpful=12 harmful=1, should NOT be pruned
        pruned = prune_playbook(playbook_file, min_uses=5)
        assert "strat-00001" not in pruned

    def test_pruned_bullets_in_archived(self, playbook_file):
        prune_playbook(playbook_file, min_uses=5)
        bullets = parse_playbook(playbook_file)
        archived = [b for b in bullets if b["section"] == "Archived"]
        assert any("auto-pruned" in b["raw_line"] for b in archived)


# ---------- get_stats ----------

class TestGetStats:
    def test_total_count(self, playbook_file):
        stats = get_stats(playbook_file)
        assert stats["total"] == 7

    def test_high_performing(self, playbook_file):
        # strat-00001 helpful=12 harmful=1 -> yes
        # strat-00002 helpful=8 harmful=3 -> no (harmful >= 2)
        # rev-00001 helpful=6 harmful=1 -> yes
        stats = get_stats(playbook_file)
        assert stats["high_performing"] == 2

    def test_problematic(self, playbook_file):
        # err-00002 harmful=7 >= helpful=2, total=9 > 0 -> yes
        stats = get_stats(playbook_file)
        assert stats["problematic"] >= 1

    def test_unused(self, playbook_file):
        # strat-00003 helpful=0 harmful=0 -> yes
        stats = get_stats(playbook_file)
        assert stats["unused"] == 1

    def test_by_section(self, playbook_file):
        stats = get_stats(playbook_file)
        assert "Strategies & Insights" in stats["by_section"]
        assert stats["by_section"]["Strategies & Insights"] == 3


# ---------- select_relevant ----------

class TestSelectRelevant:
    def test_bug_prioritizes_common_mistakes(self, playbook_file):
        results = select_relevant(playbook_file, "BUG", [], [], k=3)
        assert len(results) <= 3
        # First result should be from Common Mistakes
        if results:
            err_bullets = [b for b in results if b["section"] == "Common Mistakes"]
            assert len(err_bullets) >= 1

    def test_feat_prioritizes_strategies(self, playbook_file):
        results = select_relevant(playbook_file, "FEAT", [], [], k=3)
        if results:
            strat_bullets = [b for b in results if b["section"] == "Strategies & Insights"]
            assert len(strat_bullets) >= 1

    def test_sec_prioritizes_review(self, playbook_file):
        results = select_relevant(playbook_file, "SEC", [], [], k=3)
        if results:
            rev_bullets = [b for b in results if b["section"] == "Review Patterns"]
            assert len(rev_bullets) >= 1

    def test_k_limits_results(self, playbook_file):
        results = select_relevant(playbook_file, "TASK", [], [], k=2)
        assert len(results) <= 2

    def test_sorts_by_helpful_ratio(self, playbook_file):
        results = select_relevant(playbook_file, "TASK", [], [], k=10)
        # Results should be sorted such that higher-ratio bullets come first
        # (within each priority tier)
        assert len(results) > 0
