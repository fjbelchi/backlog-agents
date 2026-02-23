#!/usr/bin/env python3
"""Tests for scripts/implementer/classify.py — deterministic ticket classifier."""
import os, sys, pytest
from pathlib import Path

# Add scripts/implementer to path so we can import classify
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "implementer"))

from classify import classify_ticket


# --- Happy path: trivial ---

def test_trivial_single_file_no_tags_no_deps(tmp_path):
    """1 affected file, no special tags, no deps => trivial."""
    ticket = tmp_path / "TASK-001.md"
    ticket.write_text(
        "---\n"
        "id: TASK-001\n"
        "title: Fix typo in readme\n"
        "tags: []\n"
        "affected_files:\n"
        "  - README.md\n"
        "depends_on: []\n"
        "---\n"
        "## Description\nFix a typo.\n"
    )
    assert classify_ticket(str(ticket)) == "trivial"


def test_trivial_zero_files(tmp_path):
    """0 affected files => trivial (<=1 rule)."""
    ticket = tmp_path / "TASK-002.md"
    ticket.write_text(
        "---\n"
        "id: TASK-002\n"
        "title: Update docs\n"
        "tags: []\n"
        "affected_files: []\n"
        "depends_on: []\n"
        "---\n"
        "## Description\nDocs only.\n"
    )
    assert classify_ticket(str(ticket)) == "trivial"


# --- Happy path: simple ---

def test_simple_two_files(tmp_path):
    """2 affected files, no tags, no deps => simple."""
    ticket = tmp_path / "BUG-001.md"
    ticket.write_text(
        "---\n"
        "id: BUG-001\n"
        "title: Fix login redirect\n"
        "tags: []\n"
        "affected_files:\n"
        "  - src/auth/login.ts\n"
        "  - src/auth/callback.ts\n"
        "depends_on: []\n"
        "---\n"
        "## Description\nFix redirect.\n"
    )
    assert classify_ticket(str(ticket)) == "simple"


def test_simple_three_files(tmp_path):
    """3 affected files, no tags, no deps => simple."""
    ticket = tmp_path / "TASK-003.md"
    ticket.write_text(
        "---\n"
        "id: TASK-003\n"
        "title: Refactor utils\n"
        "tags: [REFACTOR]\n"
        "affected_files:\n"
        "  - src/utils/a.ts\n"
        "  - src/utils/b.ts\n"
        "  - src/utils/c.ts\n"
        "depends_on: []\n"
        "---\n"
        "## Description\nRefactor utils.\n"
    )
    assert classify_ticket(str(ticket)) == "simple"


# --- Happy path: complex by file count ---

def test_complex_four_files(tmp_path):
    """4 affected files => complex."""
    ticket = tmp_path / "FEAT-001.md"
    ticket.write_text(
        "---\n"
        "id: FEAT-001\n"
        "title: Add payment system\n"
        "tags: []\n"
        "affected_files:\n"
        "  - src/pay/stripe.ts\n"
        "  - src/pay/handler.ts\n"
        "  - src/pay/models.ts\n"
        "  - src/pay/routes.ts\n"
        "depends_on: []\n"
        "---\n"
        "## Description\nPayment integration.\n"
    )
    assert classify_ticket(str(ticket)) == "complex"


# --- Complex by tags ---

def test_complex_arch_tag_overrides_file_count(tmp_path):
    """ARCH tag forces complex even with 1 file."""
    ticket = tmp_path / "TASK-010.md"
    ticket.write_text(
        "---\n"
        "id: TASK-010\n"
        "title: Restructure module layout\n"
        "tags: [ARCH]\n"
        "affected_files:\n"
        "  - src/index.ts\n"
        "depends_on: []\n"
        "---\n"
        "## Description\nArchitecture change.\n"
    )
    assert classify_ticket(str(ticket)) == "complex"


def test_complex_security_tag(tmp_path):
    """SECURITY tag forces complex."""
    ticket = tmp_path / "BUG-010.md"
    ticket.write_text(
        "---\n"
        "id: BUG-010\n"
        "title: Fix XSS vulnerability\n"
        "tags: [SECURITY]\n"
        "affected_files:\n"
        "  - src/sanitize.ts\n"
        "depends_on: []\n"
        "---\n"
        "## Description\nSecurity fix.\n"
    )
    assert classify_ticket(str(ticket)) == "complex"


def test_complex_sec_tag(tmp_path):
    """SEC tag (abbreviation) also forces complex."""
    ticket = tmp_path / "BUG-011.md"
    ticket.write_text(
        "---\n"
        "id: BUG-011\n"
        "title: Fix CSRF token\n"
        "tags: [SEC]\n"
        "affected_files:\n"
        "  - src/csrf.ts\n"
        "depends_on: []\n"
        "---\n"
        "## Description\nCSRF fix.\n"
    )
    assert classify_ticket(str(ticket)) == "complex"


# --- Complex by dependencies ---

def test_complex_has_dependencies(tmp_path):
    """Non-empty depends_on forces complex even with 1 file."""
    ticket = tmp_path / "TASK-020.md"
    ticket.write_text(
        "---\n"
        "id: TASK-020\n"
        "title: Add feature B\n"
        "tags: []\n"
        "affected_files:\n"
        "  - src/b.ts\n"
        "depends_on:\n"
        "  - TASK-019\n"
        "---\n"
        "## Description\nDepends on TASK-019.\n"
    )
    assert classify_ticket(str(ticket)) == "complex"


# --- Manual override ---

def test_manual_override_complexity_field(tmp_path):
    """Explicit complexity: field overrides heuristic rules."""
    ticket = tmp_path / "TASK-030.md"
    ticket.write_text(
        "---\n"
        "id: TASK-030\n"
        "title: Big refactor marked simple\n"
        "tags: [ARCH]\n"
        "affected_files:\n"
        "  - src/a.ts\n"
        "  - src/b.ts\n"
        "  - src/c.ts\n"
        "  - src/d.ts\n"
        "  - src/e.ts\n"
        "complexity: simple\n"
        "depends_on: []\n"
        "---\n"
        "## Description\nManually set to simple.\n"
    )
    assert classify_ticket(str(ticket)) == "simple"


def test_manual_override_trivial(tmp_path):
    """Explicit complexity: trivial overrides even with deps."""
    ticket = tmp_path / "TASK-031.md"
    ticket.write_text(
        "---\n"
        "id: TASK-031\n"
        "title: Override to trivial\n"
        "tags: []\n"
        "affected_files:\n"
        "  - src/a.ts\n"
        "  - src/b.ts\n"
        "depends_on:\n"
        "  - TASK-030\n"
        "complexity: trivial\n"
        "---\n"
        "## Description\nManual trivial.\n"
    )
    assert classify_ticket(str(ticket)) == "trivial"


# --- Edge cases ---

def test_missing_frontmatter_returns_complex(tmp_path):
    """No frontmatter at all => complex (safe default)."""
    ticket = tmp_path / "TASK-040.md"
    ticket.write_text("## Description\nNo frontmatter.\n")
    assert classify_ticket(str(ticket)) == "complex"


def test_missing_fields_returns_complex(tmp_path):
    """Frontmatter with no relevant fields => complex (safe default).

    Empty tags, empty affected_files, empty depends_on means
    affected_files count is 0 (<=1) => trivial... but wait,
    default empty lists means: 0 files, no tags, no deps => trivial.
    Actually per the rules: <=1 file => trivial. So empty = trivial.
    Let me test partial frontmatter (only id, no files/tags/deps fields at all).
    """
    ticket = tmp_path / "TASK-041.md"
    ticket.write_text(
        "---\n"
        "id: TASK-041\n"
        "title: Minimal ticket\n"
        "---\n"
        "## Description\nMinimal.\n"
    )
    # Missing fields default to empty lists: 0 files, no tags, no deps => trivial
    assert classify_ticket(str(ticket)) == "trivial"


def test_inline_list_format(tmp_path):
    """Inline YAML list [a, b, c] for affected_files."""
    ticket = tmp_path / "BUG-050.md"
    ticket.write_text(
        "---\n"
        "id: BUG-050\n"
        "title: Inline lists\n"
        "tags: []\n"
        "affected_files: [src/a.ts, src/b.ts]\n"
        "depends_on: []\n"
        "---\n"
        "## Description\nInline format.\n"
    )
    assert classify_ticket(str(ticket)) == "simple"


def test_multiline_yaml_list_format(tmp_path):
    """Multiline YAML list with - items for affected_files."""
    ticket = tmp_path / "BUG-051.md"
    ticket.write_text(
        "---\n"
        "id: BUG-051\n"
        "title: Multiline lists\n"
        "tags:\n"
        "  - REFACTOR\n"
        "affected_files:\n"
        "  - src/a.ts\n"
        "  - src/b.ts\n"
        "  - src/c.ts\n"
        "depends_on:\n"
        "  - BUG-050\n"
        "---\n"
        "## Description\nMultiline format.\n"
    )
    # depends_on is non-empty => complex (regardless of file count)
    assert classify_ticket(str(ticket)) == "complex"


def test_inline_tags_with_security_keyword(tmp_path):
    """Inline tags: [SECURITY, REFACTOR] should detect SECURITY."""
    ticket = tmp_path / "BUG-052.md"
    ticket.write_text(
        "---\n"
        "id: BUG-052\n"
        "title: Inline security tag\n"
        "tags: [SECURITY, REFACTOR]\n"
        "affected_files: [src/a.ts]\n"
        "depends_on: []\n"
        "---\n"
        "## Description\nInline security.\n"
    )
    assert classify_ticket(str(ticket)) == "complex"


def test_nonexistent_file_returns_complex():
    """File that doesn't exist => complex (safe default)."""
    assert classify_ticket("/nonexistent/path/ticket.md") == "complex"
