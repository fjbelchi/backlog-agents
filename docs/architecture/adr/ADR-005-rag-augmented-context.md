# ADR-005: RAG-Augmented Context for Token Reduction

## Status
Accepted

## Context

Large codebases (500+ files) generate excessive input tokens when skills read entire files for context. A typical 2000-line file consumes ~20K tokens. Most of that content is irrelevant to the current task.

## Decision

Introduce optional RAG (Retrieval-Augmented Generation) as a context optimization layer. Instead of reading full files, skills retrieve only the most relevant code chunks via vector similarity search.

### Architecture

```
source files → chunker (512 tokens) → embeddings → vector index (.backlog-ops/rag-index/)
                                                          ↓
skill query → embedding → similarity search → top-K chunks → LLM context
```

### Implementation Layers

1. **Indexer** (`scripts/ops/rag_index.py`): Splits source files into chunks, generates embeddings, stores in local FAISS or Qdrant.
2. **Retriever**: Called by skills before LLM calls. Returns top-K relevant chunks for a given query.
3. **Context assembler**: Formats retrieved chunks with file paths and line numbers for the LLM.

### When RAG is Used

- Ticket generation (Phase 1.4: Analyze Codebase Context)
- Implementation planning (Gate 1: PLAN)
- Code review (Gate 4: relevant pattern lookup)

### When RAG is NOT Used

- Small projects (<50 files): full context is cheaper than RAG overhead
- Exact-match lookups (grep/glob is better)
- Config/template generation

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

## Consequences

- Token input reduction of 60-80% for large codebases
- Adds ~2s latency per retrieval (acceptable for non-interactive)
- Requires periodic reindexing (on significant code changes)
- Embedding cost is minimal (~$0.01 per 1M tokens with text-embedding-3-small)
- Falls back to glob/grep if index is stale or missing

## Metrics

- Track `rag_chunks_retrieved` and `rag_index_freshness` in usage ledger
- Compare token usage with vs without RAG for same operations
