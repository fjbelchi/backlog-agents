# LangChain Stack Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this design.

**Goal:** Add an independent LangChain ecosystem stack alongside the existing infrastructure for observability (LangFuse), improved RAG (LangChain), and agent experimentation (LangGraph).

**Architecture:** Separate docker-compose.langchain.yml that connects to the existing LiteLLM gateway. Two launcher scripts let users choose which stack to run.

---

## Problem

The current stack (LiteLLM + Flask RAG + PostgreSQL) works but lacks:
- Observability: no tracing, no cost dashboards, no per-request visibility
- RAG quality: basic chunking, no reranking, no multi-query retrieval
- Agent experimentation: no playground for testing LangGraph workflows

## Solution

Add a second Docker Compose file with 4 services that complement (not replace) the existing stack.

## Architecture

```
docker-compose.yml (existing, unchanged)
├── postgres        :5432
├── litellm         :8000  ←── shared gateway
├── rag (flask)     :8001  ←── original RAG (still available)
└── memgraph        :7687  (profile: phase2)

docker-compose.langchain.yml (new)
├── langfuse-db     :5433  (dedicated postgres for LangFuse)
├── langfuse        :3001  (observability UI + API)
├── rag-langchain   :8002  (improved RAG via LangChain)
└── langgraph-dev   :8003  (LangGraph playground)
```

Connections:
- rag-langchain → LiteLLM :8000 (for embeddings/LLM calls if needed)
- langgraph-dev → LiteLLM :8000 (for all LLM calls)
- LiteLLM → LangFuse :3001 (sends traces via callback)
- LangFuse → langfuse-db :5433 (stores traces)

## Files to Create

### 1. docker-compose.langchain.yml

Services:

**langfuse-db**: postgres:16-alpine
- Port 5433
- Volume: langfuse-pgdata
- Env: POSTGRES_USER=langfuse, POSTGRES_PASSWORD=langfuse_pass, POSTGRES_DB=langfuse

**langfuse**: langfuse/langfuse:latest (or ghcr.io/langfuse/langfuse:2)
- Port 3001 → 3000 internal
- Depends on langfuse-db healthy
- Env: DATABASE_URL=postgresql://langfuse:langfuse_pass@langfuse-db:5432/langfuse, NEXTAUTH_URL=http://localhost:3001, NEXTAUTH_SECRET=changeme-langfuse-secret, SALT=changeme-langfuse-salt, TELEMETRY_ENABLED=false

**rag-langchain**: builds from docker/rag-langchain/Dockerfile
- Port 8002
- Volume: chromadata-langchain
- Env: LITELLM_BASE_URL=http://host.docker.internal:8000, RAG_DB_PATH=/data/chroma
- The Dockerfile installs: langchain, langchain-community, langchain-anthropic, chromadb, sentence-transformers, flask, langfuse
- The server exposes same API as the current Flask RAG (/search, /health, /index) but uses LangChain internals: RecursiveCharacterTextSplitter for better chunking, multi-query retrieval, optional reranking

**langgraph-dev**: builds from docker/langgraph/Dockerfile
- Port 8003
- Env: LITELLM_BASE_URL=http://host.docker.internal:8000, LANGFUSE_HOST=http://langfuse:3000, LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY from env
- Simple LangGraph playground server for experimenting with agent graphs

### 2. docker/rag-langchain/Dockerfile

FROM python:3.11-slim
Install: langchain langchain-community chromadb sentence-transformers flask langfuse
Copy server script
Bake embedding model into image
Expose 8002

### 3. docker/langgraph/Dockerfile

FROM python:3.11-slim
Install: langgraph langchain langchain-anthropic langfuse
Copy playground script
Expose 8003

### 4. .env.langchain (template, committed)

```
# LangFuse
LANGFUSE_SECRET_KEY=sk-lf-changeme
LANGFUSE_PUBLIC_KEY=pk-lf-changeme
NEXTAUTH_SECRET=changeme-langfuse-secret
LANGFUSE_SALT=changeme-langfuse-salt

# LangFuse DB
LANGFUSE_POSTGRES_USER=langfuse
LANGFUSE_POSTGRES_PASSWORD=langfuse_pass
LANGFUSE_POSTGRES_DB=langfuse
```

### 5. claude-with-langchain.sh

```bash
#!/usr/bin/env bash
# Start both stacks and launch Claude Code with LangChain RAG
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Start existing stack
"$SCRIPT_DIR/scripts/services/start-services.sh"

# Start LangChain stack
echo "[langchain] Starting LangChain services..."
docker compose -f "$SCRIPT_DIR/docker-compose.langchain.yml" --env-file "$SCRIPT_DIR/.env.langchain.local" up -d

# Wait for LangFuse
echo "[langchain] Waiting for LangFuse..."
until curl -sf http://localhost:3001/api/public/health > /dev/null 2>&1; do sleep 2; done
echo "[langchain] LangFuse ready at http://localhost:3001"

# Wait for RAG-LangChain
until curl -sf http://localhost:8002/health > /dev/null 2>&1; do sleep 2; done
echo "[langchain] RAG-LangChain ready at http://localhost:8002"

# Override RAG URL to use LangChain RAG
export RAG_BASE_URL=http://localhost:8002

# Start RAG file watcher
python3 "$SCRIPT_DIR/scripts/rag/watcher.py" --watch "$(pwd)" &

echo ""
echo "┌─────────────────────────────────────────┐"
echo "│  LangChain Stack Active                 │"
echo "│  LangFuse:      http://localhost:3001   │"
echo "│  RAG-LangChain: http://localhost:8002   │"
echo "│  LangGraph:     http://localhost:8003   │"
echo "│  LiteLLM:       http://localhost:8000   │"
echo "└─────────────────────────────────────────┘"

claude "$@"
```

## Files to Modify

### 6. config/litellm/proxy-config.docker.yaml

Add LangFuse callback to litellm_settings:
```yaml
litellm_settings:
  success_callback: ["langfuse"]
  langfuse_host: "http://langfuse:3000"  # or use env vars
```

But ONLY when running with langchain stack. Solution: the callback env vars (LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY) are only set when claude-with-langchain.sh runs. LiteLLM auto-detects LangFuse when these env vars exist. No config file change needed.

### 7. .gitignore

Add: .env.langchain.local

### 8. Makefile

Add targets:
```makefile
langchain-up:    ## Start LangChain stack
langchain-down:  ## Stop LangChain stack
langchain-logs:  ## Tail LangChain logs
langchain-ps:    ## Show LangChain service status
```

## What stays unchanged

- docker-compose.yml — no changes
- claude-with-services.sh — no changes
- All skills — no changes (RAG URL comes from env var)
- scripts/rag/client.sh — already uses RAG_BASE_URL env var
- backlog.config.json — no changes needed

## Verification

1. docker compose -f docker-compose.langchain.yml up -d
2. curl http://localhost:3001/api/public/health — LangFuse healthy
3. curl http://localhost:8002/health — RAG-LangChain healthy
4. curl http://localhost:8003/health — LangGraph healthy
5. Open LangFuse at http://localhost:3001, create account
6. Make a LiteLLM request with LANGFUSE env vars → verify trace appears in LangFuse
7. Test RAG search: curl -X POST http://localhost:8002/search -d '{"query": "test", "n_results": 5}'
8. ./claude-with-langchain.sh — full stack starts, Claude Code uses LangChain RAG
9. ./claude-with-services.sh — original stack only, LangChain stack not started

## Implementation Checklist

- [ ] Create docker-compose.langchain.yml with 4 services
- [ ] Create docker/rag-langchain/Dockerfile
- [ ] Create docker/rag-langchain/server.py (Flask server with LangChain)
- [ ] Create docker/langgraph/Dockerfile
- [ ] Create docker/langgraph/playground.py (LangGraph dev server)
- [ ] Create .env.langchain template file
- [ ] Create claude-with-langchain.sh launcher script
- [ ] Update .gitignore to exclude .env.langchain.local
- [ ] Add Makefile targets for langchain stack
- [ ] Test full stack startup and integration
- [ ] Verify LangFuse traces appear
- [ ] Verify RAG-LangChain produces better results
- [ ] Document setup instructions in README or tutorial

## Benefits

1. **Observability**: Full trace visibility for every LLM call via LangFuse
2. **Cost tracking**: Per-request cost analysis and dashboards
3. **RAG quality**: Better chunking, multi-query retrieval, optional reranking
4. **Agent experimentation**: LangGraph playground for testing workflows
5. **Non-invasive**: Existing stack remains unchanged, users can choose
6. **Composable**: Can run both stacks simultaneously if needed

## Migration Path

Phase 1 (this design):
- Add LangChain stack alongside existing stack
- Users opt-in via claude-with-langchain.sh
- No breaking changes

Phase 2 (future):
- Evaluate LangChain RAG vs Flask RAG performance
- If LangChain RAG superior, consider making it default
- Keep Flask RAG as fallback option

## Questions & Decisions

**Q: Why not replace the existing RAG?**
A: Conservative approach. Test LangChain stack in production before committing.

**Q: Why separate Postgres for LangFuse?**
A: Isolation. LangFuse schema is complex and version-dependent. Avoid conflicts with existing DB.

**Q: Can both stacks run simultaneously?**
A: Yes. Different ports, isolated volumes. claude-with-langchain.sh starts both.

**Q: What if LangFuse adds overhead?**
A: LiteLLM callbacks are async and non-blocking. Minimal impact. Can disable via env var.

**Q: How to handle LangFuse auth in production?**
A: Generate strong NEXTAUTH_SECRET and SALT. Use secrets management (AWS Secrets Manager, etc).

## References

- LangFuse docs: https://langfuse.com/docs
- LangChain docs: https://python.langchain.com/docs
- LangGraph docs: https://langchain-ai.github.io/langgraph
- LiteLLM LangFuse integration: https://docs.litellm.ai/docs/observability/langfuse_integration
