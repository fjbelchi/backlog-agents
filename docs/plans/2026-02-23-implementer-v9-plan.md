# Implementer v9.0 Token Optimization Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce implementer SKILL.md from 1055→350 lines (~70% token reduction) and replace 7 LLM calls with deterministic scripts.

**Architecture:** Script delegation layer (9 scripts) + template extraction (4 templates) + aggressive prompt compression.

**Tech Stack:** Python 3, bash, pytest

---

### Task 1: classify.py — Deterministic ticket classifier

**Files:**
- Create: `scripts/implementer/classify.py`
- Test: `tests/test_classify.py`

**Step 1: Write failing tests**
```python
# tests/test_classify.py
import pytest, tempfile, os
from scripts.implementer.classify import classify_ticket

def _write_ticket(tmp, content):
    p = os.path.join(tmp, "t.md")
    with open(p, "w") as f: f.write(content)
    return p

def test_trivial_single_file_no_tags(tmp_path):
    p = _write_ticket(str(tmp_path), "---\nid: BUG-001\naffected_files: [src/foo.py]\ntags: []\n---\nFix typo")
    assert classify_ticket(p) == "trivial"

def test_simple_few_files(tmp_path):
    p = _write_ticket(str(tmp_path), "---\nid: BUG-002\naffected_files: [a.py, b.py, c.py]\ntags: []\n---\nFix bug")
    assert classify_ticket(p) == "simple"

def test_complex_many_files(tmp_path):
    p = _write_ticket(str(tmp_path), "---\nid: FEAT-001\naffected_files: [a.py,b.py,c.py,d.py]\ntags: []\n---\nBig feat")
    assert classify_ticket(p) == "complex"

def test_arch_tag_forces_complex(tmp_path):
    p = _write_ticket(str(tmp_path), "---\nid: BUG-003\naffected_files: [a.py]\ntags: [ARCH]\n---\nArch change")
    assert classify_ticket(p) == "complex"

def test_manual_override(tmp_path):
    p = _write_ticket(str(tmp_path), "---\nid: BUG-004\ncomplexity: simple\naffected_files: [a.py,b.py,c.py,d.py]\ntags: []\n---\nOverride")
    assert classify_ticket(p) == "simple"
```

**Step 2:** Run `pytest tests/test_classify.py -v` — expect FAIL

**Step 3: Implement**
```python
# scripts/implementer/classify.py
from __future__ import annotations
import re, sys

def _parse_frontmatter(path: str) -> dict:
    with open(path) as f: text = f.read()
    m = re.search(r'^---\n(.*?)\n---', text, re.DOTALL)
    if not m: return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ':' in line:
            k, v = line.split(':', 1)
            fm[k.strip()] = v.strip()
    return fm

def _parse_list(val: str) -> list:
    return [x.strip().strip('"').strip("'") for x in val.strip('[]').split(',') if x.strip()]

def classify_ticket(path: str) -> str:
    fm = _parse_frontmatter(path)
    if 'complexity' in fm and fm['complexity'] in ('trivial','simple','complex'):
        return fm['complexity']
    files = _parse_list(fm.get('affected_files', '[]'))
    tags = [t.upper() for t in _parse_list(fm.get('tags', '[]'))]
    deps = _parse_list(fm.get('depends_on', '[]'))
    if any(t in ('ARCH','SECURITY','SEC') for t in tags): return "complex"
    if deps: return "complex"
    if len(files) <= 1: return "trivial"
    if len(files) <= 3: return "simple"
    return "complex"

if __name__ == "__main__":
    if len(sys.argv) < 2: raise SystemExit("Usage: classify.py <ticket.md>")
    print(classify_ticket(sys.argv[1]))
```

**Step 4:** Run `pytest tests/test_classify.py -v` — expect PASS

**Step 5:** `git add scripts/implementer/classify.py tests/test_classify.py && git commit -m "feat(v9): add deterministic ticket classifier"`

---

### Task 2: wave_plan.py — Graph-based wave planner

**Files:**
- Create: `scripts/implementer/wave_plan.py`
- Test: `tests/test_wave_plan.py`

**Step 1: Write failing tests**
```python
# tests/test_wave_plan.py
import pytest, json
from scripts.implementer.wave_plan import plan_wave

def test_no_conflict_parallel():
    tickets = [
        {"id":"BUG-001","priority":"P1","affected_files":["a.py"],"depends_on":[]},
        {"id":"BUG-002","priority":"P1","affected_files":["b.py"],"depends_on":[]}
    ]
    result = plan_wave(tickets, max_slots=3)
    assert len(result["waves"]) == 1
    assert len(result["waves"][0]["tickets"]) == 2

def test_file_conflict_sequential():
    tickets = [
        {"id":"BUG-001","priority":"P0","affected_files":["shared.py"],"depends_on":[]},
        {"id":"BUG-002","priority":"P1","affected_files":["shared.py"],"depends_on":[]}
    ]
    result = plan_wave(tickets, max_slots=3)
    assert result["waves"][0]["tickets"][0]["id"] == "BUG-001"
    total = sum(len(w["tickets"]) for w in result["waves"])
    assert total == 2

def test_dependency_ordering():
    tickets = [
        {"id":"FEAT-002","priority":"P3","affected_files":["b.py"],"depends_on":["FEAT-001"]},
        {"id":"FEAT-001","priority":"P3","affected_files":["a.py"],"depends_on":[]}
    ]
    result = plan_wave(tickets, max_slots=3)
    ids = [t["id"] for w in result["waves"] for t in w["tickets"]]
    assert ids.index("FEAT-001") < ids.index("FEAT-002")

def test_max_slots_respected():
    tickets = [{"id":f"T-{i}","priority":"P2","affected_files":[f"{i}.py"],"depends_on":[]} for i in range(10)]
    result = plan_wave(tickets, max_slots=3)
    for w in result["waves"]:
        assert len(w["tickets"]) <= 3

def test_subagent_routing():
    tickets = [{"id":"T-1","priority":"P1","affected_files":["src/App.tsx"],"depends_on":[]}]
    result = plan_wave(tickets, max_slots=3)
    assert result["waves"][0]["tickets"][0]["subagent_type"] == "frontend"
```

**Step 2:** Run `pytest tests/test_wave_plan.py -v` — expect FAIL

**Step 3: Implement** graph-based conflict detection with greedy bin-packing. Route subagent_type from file extensions (.tsx→frontend, .py→backend, Dockerfile→devops, .ipynb→ml-engineer, default→general-purpose).

**Step 4:** Run `pytest tests/test_wave_plan.py -v` — expect PASS

**Step 5:** `git add scripts/implementer/wave_plan.py tests/test_wave_plan.py && git commit -m "feat(v9): add graph-based wave planner"`

---

### Task 3: commit_msg.py + pre_review.py + micro_reflect.py

Three small utility scripts in one task (each <50 lines).

**Files:**
- Create: `scripts/implementer/commit_msg.py`
- Create: `scripts/implementer/pre_review.py`
- Create: `scripts/implementer/micro_reflect.py`
- Test: `tests/test_impl_utils.py`

**Step 1: Write failing tests** — 5 tests for commit_msg (template, with summary, missing args), 5 for pre_review (clean diff, debug artifacts, lint errors, test failures, import check), 5 for micro_reflect (all pass→helpful, gate fail→harmful, retry→neutral).

**Step 2:** Run tests — expect FAIL

**Step 3: Implement** all three scripts using only stdlib.

**Step 4:** Run tests — expect PASS

**Step 5:** `git add scripts/implementer/commit_msg.py scripts/implementer/pre_review.py scripts/implementer/micro_reflect.py tests/test_impl_utils.py && git commit -m "feat(v9): add commit_msg, pre_review, micro_reflect scripts"`

---

### Task 4: enrich_ticket.py + wave_end.py

**Files:**
- Create: `scripts/implementer/enrich_ticket.py`
- Create: `scripts/implementer/wave_end.py`
- Test: `tests/test_enrich_ticket.py`
- Test: `tests/test_wave_end.py`

**Step 1: Write failing tests** — 5 for enrich_ticket (adds status, date, cost section, commit hash, handles missing fields), 5 for wave_end (writes wave log, runs micro_reflect, moves tickets, checks session limit, handles empty wave).

**Step 2:** Run tests — expect FAIL

**Step 3: Implement.** enrich_ticket.py reads git info and writes to ticket. wave_end.py orchestrates: enrich → cost_history → move → wave_summary → micro_reflect → session check.

**Step 4:** Run tests — expect PASS

**Step 5:** `git add scripts/implementer/enrich_ticket.py scripts/implementer/wave_end.py tests/test_enrich_ticket.py tests/test_wave_end.py && git commit -m "feat(v9): add enrich_ticket and wave_end scripts"`

---

### Task 5: startup.sh — Merged Phase 0 + 0.5

**Files:**
- Create: `scripts/implementer/startup.sh`
- Test: `tests/test_startup.sh`

**Step 1: Write failing test** — bash test that runs startup.sh with mock config and validates JSON output structure.

**Step 2:** Run test — expect FAIL

**Step 3: Implement** startup.sh: read config, resolve plugin root, detect Ollama, classify tickets via classify.py, load playbook stats, cache health check. Output JSON.

**Step 4:** Run test — expect PASS

**Step 5:** `git add scripts/implementer/startup.sh tests/test_startup.sh && git commit -m "feat(v9): add merged startup script (Phase 0+0.5)"`

---

### Task 6: Extract 4 template files

**Files:**
- Create: `skills/backlog-implementer/templates/fast-path-agent.md`
- Create: `skills/backlog-implementer/templates/wave-summary-agent.md`
- Create: `skills/backlog-implementer/templates/micro-reflector.md`
- Create: `skills/backlog-implementer/templates/pre-review.md`

**Step 1:** Extract fast-path prompt from SKILL.md lines 732-776 → `templates/fast-path-agent.md`

**Step 2:** Extract wave summary prompt from SKILL.md lines 857-877 → `templates/wave-summary-agent.md`

**Step 3:** Extract micro-reflector prompt from SKILL.md lines 893-917 → `templates/micro-reflector.md`

**Step 4:** Extract pre-review prompt from SKILL.md lines 552-571 → `templates/pre-review.md`

**Step 5:** `git add skills/backlog-implementer/templates/ && git commit -m "feat(v9): extract 4 inline prompts to template files"`

---

### Task 7: Rewrite SKILL.md — Aggressive compression

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md` (1055→350 lines)

**Step 1:** Rewrite SKILL.md following the compressed structure from the design doc. Replace inline prompts with template references, inline bash with script calls, verbose prose with tables, remove duplicated Iron Laws/Context Mgmt.

**Step 2:** Verify: `wc -l skills/backlog-implementer/SKILL.md` ≤ 400

**Step 3:** Verify all script references resolve: `bash -n scripts/implementer/startup.sh`, `python3 -c "import scripts.implementer.classify"`

**Step 4:** `git add skills/backlog-implementer/SKILL.md && git commit -m "feat(v9): compress SKILL.md 1055→350 lines (70% token reduction)"`

---

### Task 8: Update CLAUDE.md + version bump

**Files:**
- Modify: `skills/backlog-implementer/CLAUDE.md`
- Modify: `skills/backlog-implementer/SKILL.md` (frontmatter only)

**Step 1:** Bump SKILL.md frontmatter: v8.0 → v9.0

**Step 2:** Rewrite CLAUDE.md as the human-readable reference. Move all "why" commentary here. Document: script layer, template layer, migration notes, troubleshooting.

**Step 3:** Run all tests: `python3 -m pytest tests/ -v`

**Step 4:** `git add skills/backlog-implementer/ && git commit -m "release: implementer v9.0 — 70% token reduction via script delegation"`
