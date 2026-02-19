# RAG Pipeline Reference

## Overview

The RAG (Retrieval-Augmented Generation) pipeline reduces LLM input tokens by 60-80% for large codebases. Instead of feeding entire files into context, skills query a local index and retrieve only the **relevant chunks** — typically 3-5 fragments of ~512 tokens each instead of a full 20K-token file.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       INDEXING PHASE (offline)                  │
│                                                                 │
│  source files ──→ file filter ──→ chunker (512 tok) ──→ JSONL  │
│   (rglob *)       (patterns +      (overlapping        index   │
│                    exclusions)       3-line overlap)             │
│                                                                 │
│  Output: .backlog-ops/rag-index/chunks.jsonl                    │
│          .backlog-ops/rag-index/meta.json                       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     RETRIEVAL PHASE (per skill call)            │
│                                                                 │
│  skill query ──→ tokenize ──→ score chunks ──→ top-K ──→ LLM   │
│  "auth          (lowercase    (token overlap    (10)     context │
│   middleware"    alphanum)     ratio scoring)                    │
└─────────────────────────────────────────────────────────────────┘
```

## Current Implementation

### Indexer: `scripts/ops/rag_index.py`

The current indexer is **deterministic and zero-cost** — it uses no LLM or embedding model. It operates in three modes:

| Command | What it does | Cost |
|---------|-------------|------|
| `python scripts/ops/rag_index.py --rebuild` | Rebuild full index from source files | $0 (no API calls) |
| `python scripts/ops/rag_index.py --query "text"` | Retrieve top-K relevant chunks | $0 (local scoring) |
| `python scripts/ops/rag_index.py --stats` | Show index metadata | $0 |

### Scoring Algorithm

The current retriever uses **TF-based token overlap** — NOT vector embeddings:

```
score(chunk, query) = |query_tokens ∩ chunk_tokens| / |query_tokens|
```

Where tokens are lowercase alphanumeric words extracted via `[a-z0-9_]+`.

**Pros**: Zero cost, zero latency, no API dependencies, fully offline.
**Cons**: No semantic understanding — `"authentication"` won't match `"login"` or `"credential"`.

### Chunking Strategy

| Parameter | Default | Configurable via |
|-----------|---------|------------------|
| Chunk size | 512 tokens (~2048 chars) | `--chunk-size` / `ragPolicy.chunkSize` |
| Overlap | 3 lines between chunks | Hardcoded in `chunk_file()` |
| Top-K results | 10 | `--top-k` / `ragPolicy.topK` |

**Why overlap?** Without it, a function that spans two chunks would be split in the middle. The 3-line overlap ensures context continuity at chunk boundaries.

### File Selection

**Indexed patterns**:
```
*.py  *.ts  *.tsx  *.js  *.jsx  *.go  *.rs  *.swift  *.kt  *.java
*.vue  *.css  *.scss  *.md  *.yaml  *.yml  *.json  *.toml
```

**Excluded directories**:
```
node_modules  .git  __pycache__  .venv  venv  dist  build  .next  target  .backlog-ops
```

### Index Format

**`chunks.jsonl`** — one JSON object per line:
```json
{
  "file": "src/auth/middleware.ts",
  "start_line": 42,
  "end_line": 78,
  "content": "export function validateToken(req: Request)...",
  "hash": "a3f2c1d4e5b6",
  "approx_tokens": 487
}
```

**`meta.json`** — index-level statistics:
```json
{
  "version": "1.0",
  "generated_at": "2026-02-18T10:00:00Z",
  "root": ".",
  "files_indexed": 342,
  "total_chunks": 1847,
  "chunk_size_tokens": 512,
  "total_approx_tokens": 894316
}
```

## Configuration

```json
{
  "llmOps": {
    "ragPolicy": {
      "enabled": true,
      "embeddingModel": "text-embedding-3-small",
      "vectorStore": "local-faiss",
      "indexPath": ".backlog-ops/rag-index",
      "chunkSize": 512,
      "topK": 10,
      "reindexCommand": "python scripts/ops/rag_index.py --rebuild"
    }
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Enable RAG pipeline |
| `embeddingModel` | string | `"text-embedding-3-small"` | Model for vector embeddings (future) |
| `vectorStore` | string | `"local-faiss"` | Backend: `local-faiss`, `qdrant`, `chromadb` |
| `indexPath` | string | `".backlog-ops/rag-index"` | Where to store index files |
| `chunkSize` | int | `512` | Approximate tokens per chunk |
| `topK` | int | `10` | Number of chunks to retrieve per query |
| `reindexCommand` | string | — | Shell command to rebuild the index |

## When to Use RAG

### Decision Matrix

| Codebase Size | Files | Recommended Approach |
|---------------|-------|---------------------|
| Small | <50 files | **Skip RAG** — read files directly. RAG overhead > benefit. |
| Medium | 50-500 files | **Optional** — RAG helps for ticket generation and planning. |
| Large | 500+ files | **Recommended** — significant token savings on every skill call. |
| Monorepo | 1000+ files | **Required** — reading everything would blow token budgets. |

### By Skill Phase

| Skill / Phase | RAG Useful? | Why |
|---------------|-------------|-----|
| `backlog-ticket` → Context Analysis | **Yes** | Find relevant code patterns without reading all files |
| `backlog-implementer` → PLAN gate | **Yes** | Discover affected modules and patterns |
| `backlog-implementer` → REVIEW gate | **Maybe** | Find similar patterns for consistency checks |
| `backlog-refinement` → Code Refs | **No** | Use glob/grep for exact file existence checks |
| `backlog-init` → Stack Detection | **No** | Use deterministic manifest checks |
| Config/template generation | **No** | Static content, no codebase context needed |

### RAG vs. Grep: Choosing the Right Tool

| Need | Use RAG | Use Grep/Glob |
|------|---------|---------------|
| "Find code related to authentication" | ✓ | |
| "Does `src/auth.ts` exist?" | | ✓ |
| "Find all files importing `express`" | | ✓ |
| "What patterns does the codebase use for error handling?" | ✓ | |
| "Count occurrences of `TODO`" | | ✓ |
| "Find code similar to this payment flow" | ✓ | |

## Token Savings Analysis

### Example: Ticket Generation for Large Codebase

**Without RAG** (reading 5 full files for context):
```
5 files × 400 lines avg × 4 tokens/line = 8,000 input tokens
```

**With RAG** (top-10 chunks):
```
10 chunks × 512 tokens = 5,120 input tokens
But typically only 3-5 chunks are highly relevant:
5 chunks × 512 tokens = 2,560 input tokens
```

**Savings**: ~68% input token reduction.

At Sonnet 4 pricing ($3/1M input tokens), saving 5,440 tokens per call:
- 100 calls/day → saves ~$1.63/day
- 2,000 calls/month → saves ~$32.64/month

## Limitations of Current Implementation

### 1. No Semantic Understanding

The TF-based scorer matches exact tokens only. It **cannot** find:
- Synonyms: `"login"` ≠ `"authenticate"` ≠ `"sign in"`
- Abbreviations: `"auth"` won't match `"authentication"` (different tokens)
- Conceptual similarity: `"payment processing"` won't find a `"billing"` module

**Mitigation**: Use specific, code-like query terms (`"validateToken"`, `"authMiddleware"`) rather than natural language.

### 2. No Embedding Vectors (Yet)

The `embeddingModel` config field is defined but **not yet wired**. The roadmap:

1. **Current (v1.0)**: TF-based token overlap — free, fast, offline
2. **Planned (v1.1)**: Optional embedding via `text-embedding-3-small` — $0.02/1M tokens, semantic matching
3. **Planned (v1.2)**: Local embedding via `all-MiniLM-L6-v2` — free, offline, semantic

### 3. No Incremental Indexing

`--rebuild` reindexes everything from scratch. For large codebases this can take seconds but produces unnecessary churn. A future `--update` flag would only reindex changed files (tracked via git diff or file mtimes).

### 4. Static Chunk Boundaries

Chunks are split by character count, not by code structure. A function definition might be split mid-statement. Future improvement: AST-aware chunking for Python, TypeScript, and Go.

## Operations

### Rebuild Index

```bash
# Full rebuild
python scripts/ops/rag_index.py --rebuild

# Custom root and chunk size
python scripts/ops/rag_index.py --rebuild --root ./src --chunk-size 256
```

### Query Index

```bash
# Interactive query
python scripts/ops/rag_index.py --query "authentication middleware"

# JSON output for piping to other tools
python scripts/ops/rag_index.py --query "payment processing" --json

# Limit results
python scripts/ops/rag_index.py --query "database connection" --top-k 5
```

### Check Index Health

```bash
# Show index stats
python scripts/ops/rag_index.py --stats

# Output:
# {
#   "version": "1.0",
#   "generated_at": "2026-02-18T10:00:00Z",
#   "files_indexed": 342,
#   "total_chunks": 1847,
#   "total_approx_tokens": 894316
# }
```

### Reindex Schedule

| Trigger | Action |
|---------|--------|
| After major refactor | `--rebuild` (full) |
| Weekly maintenance | `--rebuild` via `make refresh` |
| Before batch operations | `--rebuild` if `meta.json` age > 24h |
| CI/CD pipeline | Add to post-merge hook |

## Integration with Skills

Skills should call RAG **before** making LLM requests when working with large codebases:

```python
# Pseudocode for skill integration
if config.ragPolicy.enabled and file_count > 50:
    chunks = rag_query(task_description, top_k=config.ragPolicy.topK)
    context = format_chunks_for_llm(chunks)
else:
    context = read_relevant_files_directly()

llm_response = call_llm(system_prompt + context + task)
```

## Related Documentation

- [ADR-005: RAG-Augmented Context](../architecture/adr/ADR-005-rag-augmented-context.md) — Architecture decision
- [Token Optimization Playbook](../tutorials/token-optimization-playbook.md) — Layer 7: RAG
- [Scripts Catalog](scripts-catalog.md) — `rag_index.py` entry
- [Config Reference](backlog-config-v1.1.md) — `ragPolicy` section
