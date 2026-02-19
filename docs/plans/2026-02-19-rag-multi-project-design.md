# Design: Project-Aware RAG with Multi-Context Support

**Date:** 2026-02-19
**Status:** Approved
**Scope:** RAG server refactor + RagClient + file watcher + skills integration

---

## Context

The current RAG server has a single hardcoded collection (`"codebase"`) shared across all projects. When working on multiple projects, code search results are mixed together, making the RAG effectively useless for context-specific retrieval.

Additionally, the sentinel skill (in design) exposes a second gap: the RAG only indexes source code, but sentinel needs to search backlog tickets for deduplication and the implementer needs to query past sentinel findings as "recurring pattern memory".

This design addresses both gaps through a project-aware API, per-project physical isolation, an always-on file watcher, a RagClient helper, and explicit integration hooks in all five skills.

---

## Architecture Overview

```
CWD → backlog.config.json → project.name
              ↓
    RagClient (Python + Shell)
         auto-detects project, wraps all HTTP calls
              ↓  X-Project header (or project body field)
    RAG Server (Docker, port 8001)
              ↓
    /data/chroma/{project_name}/   ← per-project ChromaDB
              ↑
    Watcher (host process)
         watches: source files + backlog/data/
         always active (started by claude-with-services.sh)
```

### Project Detection (precedence)

1. `X-Project` header in request
2. `project` field in JSON body
3. `backlog.config.json` → `project.name` (walked up from CWD by RagClient)
4. Fallback: CWD basename

---

## Current Gaps

| Gap | Impact |
|-----|--------|
| Single hardcoded `"codebase"` collection | All projects share one index |
| `/search` and `/index` have no project context | No per-project routing |
| No `/projects` endpoint | No visibility into what is indexed |
| `add()` instead of `upsert()` | Re-indexing creates duplicate documents |
| No file watcher | Index goes stale immediately |
| Skills do not call RAG | Index does not grow with work |
| No ticket indexing | Sentinel cannot deduplicate or use recurring pattern memory |
| No UI | Testing and verification requires manual curl |

---

## Component 1: RAG Server (project-aware)

### Physical isolation

Each project gets its own ChromaDB path:

```
/data/chroma/
├── my-api/            ← project A
├── frontend-app/      ← project B
└── default/           ← backward compatibility
```

The Docker volume `chromadata:/data/chroma` remains unchanged. Subdirectories are created on first use.

### Endpoints

```
# Modified
POST /search              body: { project?, query, n_results, filter? }
POST /index               body: { project?, documents, ids, metadatas }  ← upsert
GET  /health              → enhanced: lists active projects

# New
GET  /projects                    → list all indexed projects + doc counts by type
GET  /projects/{name}/stats       → detailed stats for a project
DELETE /projects/{name}           → clear a project's entire index
POST /projects/{name}/init        → create empty collection for a project
GET  /ui                          → mini HTML UI (project list + search form)
```

### Document ID strategy (deduplication)

Stable IDs using `upsert()` instead of `add()`:

```
format: "{project}::{relative_path}::{chunk_index}"
example: "my-api::src/auth/login.py::0"
         "my-api::backlog/data/pending/BUG-018.md::0"
```

Re-indexing the same file replaces the existing document. Index stays clean.

### Document types

| `type` metadata | Source | Watcher? |
|---|---|---|
| `"code"` | Source files (.py, .ts, .go, etc.) | Yes |
| `"ticket"` | `backlog/data/pending/*.md` | Yes |

Type metadata enables filtering: `filter={"type": "ticket"}` or `filter={"found_by": "backlog-sentinel"}`.

### Mini UI (`/ui`)

HTML page served inline by the server (no external dependencies):

- Table of indexed projects with doc count by type (code / ticket)
- Search form: project selector + query input + n_results
- Results with file path, snippet preview, similarity score
- Last indexed timestamp per project

Accessible at `http://localhost:8001/ui`.

---

## Component 2: RagClient Helper

### `scripts/rag/client.py` — Python class

```python
class RagClient:
    def __init__(self, project: str = None, base_url: str = "http://localhost:8001"):
        self.project = project or self._detect_project()
        self.base_url = base_url

    def _detect_project(self) -> str:
        """Walk up from CWD looking for backlog.config.json.
        Returns project.name or CWD basename as fallback."""
        ...

    def search(self, query: str, n: int = 5, filter: dict = None) -> list[dict]: ...
    def index_files(self, paths: list[str]) -> dict: ...
    def upsert_file(self, path: str, type: str = "code") -> dict: ...
    def clear(self) -> dict: ...
    def stats(self) -> dict: ...
```

Skills import this class directly. No knowledge of server internals required.

### `scripts/rag/client.sh` — Shell wrapper

Sourceable functions for shell scripts and Makefile targets:

```bash
source scripts/rag/client.sh

rag_search "authentication logic"   # search in current project
rag_index_dir ./src                 # index a directory
rag_upsert_file src/auth/login.py   # upsert single file
rag_clear                           # clear current project index
rag_status                          # stats for current project
```

Project name is auto-detected from `backlog.config.json` in CWD.

### Makefile targets

```makefile
rag-status:           # show projects and doc counts
rag-index:            # make rag-index [DIR=./src]
rag-search:           # make rag-search QUERY="auth"
rag-clear:            # make rag-clear [PROJECT=my-api]
```

---

## Component 3: File Watcher

### Design

Host-side process (not inside Docker container). Avoids the need to mount project directories into `docker-compose.yml`. Calls the RAG server HTTP API to index changes.

```
scripts/rag/watcher.py
  --watch /path/to/project   ← defaults to CWD
```

### Behavior

- Reads `backlog.config.json` in watched directory to get project name
- Uses `watchdog` library for filesystem events
- On `created` / `modified` → `client.upsert_file(path)`
- On `deleted` → `DELETE /projects/{project}/docs/{id}` to remove from index
- Watches: source files filtered by `agentRouting.rules` patterns + `backlog/data/`
- Debounce: 2s (prevents spam on formatter multi-save)

### Always-on policy

The watcher is **not optional**. It is started automatically alongside all other services:

```bash
# claude-with-services.sh
python3 scripts/rag/watcher.py --watch "$CWD" &
```

`make services-up` starts it. `make services-down` kills it. If the watched directory has no `backlog.config.json`, the watcher waits until one appears (supports project switching without restart).

---

## Component 4: Skills Integration

### Index scope

The watcher watches two paths:
- Source code files (filtered by stack patterns from `backlog.config.json`)
- `backlog/data/pending/*.md` (ticket files)

Both document types are searchable and filterable via metadata.

### Per-skill integration

**`backlog-init`**

| When | RAG action |
|---|---|
| After initialization completes | `rag_index_dir .` (code) + `rag_index_dir backlog/data/` (tickets) |

**`backlog-ticket`**

| When | RAG action |
|---|---|
| Generating ticket | `rag_search(ticket_context)` → enriches `context` and `acceptanceCriteria` |
| Saving ticket | `rag_upsert(ticket_path, type="ticket")` |

**`backlog-implementer`**

| When | RAG action |
|---|---|
| Gate 1 PLAN | `rag_search(task_description)` → context enrichment for prompt |
| Gate 1 PLAN | `rag_search(affected_files, filter={"found_by": "backlog-sentinel"})` → "Recurring Patterns" block injected before code writing |
| Gate 2 IMPLEMENT (post-file) | `rag_upsert_file(path)` per modified file |
| Gate 5 COMMIT | `rag_index_dir(touched_files)` sync pass |

**`backlog-sentinel`**

| When | RAG action |
|---|---|
| Phase 0.5 — context compression | `rag_search(file_name)` per changed file → snippets for reviewers (~800t vs ~3k full files) |
| Phase 0.5 — architecture rules | `rag_search(changed_files, filter={"type": "code"})` → relevant rules from codeRules.source |
| Phase 0.5 — duplicate pre-check | `rag_search(finding, filter={"type": "ticket"})` similarity > 0.85 → skip |
| Phase 2 — per finding | `rag_search(finding_description, filter={"type": "ticket"})` → final dedup |
| Phase 3 — post-ticket | `rag_upsert(ticket_path, type="ticket", found_by="backlog-sentinel")` |
| Phase 3 — pattern ledger | `rag_search(pattern_description)` → recurring pattern matching |

**`backlog-refinement`**

| When | RAG action |
|---|---|
| Verifying code references in tickets | `rag_search(function_or_class_name)` → confirms referenced code exists |

---

## Files to Create

```
scripts/rag/client.py              ← RagClient Python class
scripts/rag/client.sh              ← Shell wrapper functions
scripts/rag/watcher.py             ← File watcher (host-side)
```

## Files to Modify

```
scripts/rag/server.py              ← Project-aware API + mini UI + upsert
docker-compose.yml                 ← No structural changes (volume already correct)
claude-with-services.sh            ← Auto-start watcher
Makefile                           ← 4 new rag-* targets
skills/backlog-init/SKILL.md       ← Add initial RAG indexing step
skills/backlog-ticket/SKILL.md     ← Add RAG search + upsert
skills/backlog-implementer/SKILL.md← Add RAG context + recurring patterns block
skills/backlog-sentinel/SKILL.md   ← Add Phase 0.5 RAG queries (already in sentinel design)
skills/backlog-refinement/SKILL.md ← Add code reference verification via RAG
```

---

## Non-Goals (out of scope)

- LiteLLM as embedding provider (keeps RAG independent of LiteLLM uptime)
- RAG tool in LiteLLM playground (Phase 2)
- Per-project Docker volumes (single volume with subdirectories is sufficient)
- Embedding model upgrade (all-MiniLM-L6-v2 is adequate for Phase 1)
- Multi-machine RAG sharing

---

## Cost Impact

All RAG operations are `$0` — local vector search, no LLM calls. The watcher adds negligible CPU overhead (~0% idle, brief spikes on file save). The sentinel's Phase 0.5 RAG queries replace full-file context passed to LLM reviewers, reducing input tokens by ~75% per commit.
