#!/usr/bin/env bash
# RAG client shell wrapper — sourceable functions for scripts and Makefile targets
# Usage: source scripts/rag/client.sh

RAG_BASE_URL="${RAG_BASE_URL:-http://localhost:8001}"
# Resolve script directory: BASH_SOURCE works in bash; zsh uses $0 when sourced
_rag_self="${BASH_SOURCE[0]:-}"
if [[ -z "$_rag_self" || "$_rag_self" == "bash" ]]; then
  # zsh fallback: use $0 expanded to absolute path
  _rag_self="${(%):-%x}" 2>/dev/null || _rag_self="$0"
fi
_RAG_CLIENT_DIR="$(cd "$(dirname "$_rag_self")" 2>/dev/null && pwd)"

rag_detect_project() {
    local dir="${1:-$(pwd)}"
    while [ "$dir" != "/" ]; do
        if [ -f "$dir/backlog.config.json" ]; then
            local name
            name="$(python3 -c "import json,sys; print(json.load(open('$dir/backlog.config.json'))['project']['name'])" 2>/dev/null)"
            if [ -n "$name" ]; then
                echo "$name"
                return 0
            fi
        fi
        dir="$(dirname "$dir")"
    done
    basename "$(pwd)"
}

rag_search() {
    local query="$1"
    local n="${2:-5}"
    local project
    project="$(rag_detect_project)"
    curl -s -X POST "$RAG_BASE_URL/search" \
        -H "Content-Type: application/json" \
        -H "X-Project: $project" \
        -d "{\"project\":\"$project\",\"query\":$(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$query"),\"n_results\":$n}"
}

rag_index_dir() {
    local dir="${1:-.}"
    local project
    project="$(rag_detect_project)"
    echo "[rag] indexing $dir → project: $project"
    find "$dir" -type f \( \
        -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o \
        -name "*.js" -o -name "*.jsx" -o -name "*.go" -o \
        -name "*.rs" -o -name "*.java" -o -name "*.md" \
    \) ! -path "*/.git/*" ! -path "*/node_modules/*" ! -path "*/__pycache__/*" \
    | while read -r f; do
        python3 "$_RAG_CLIENT_DIR/client.py" upsert "$f" --project "$project" 2>/dev/null
    done
    echo "[rag] done indexing $dir"
}

rag_upsert_file() {
    local file="$1"
    local project
    project="$(rag_detect_project)"
    python3 "$_RAG_CLIENT_DIR/client.py" upsert "$file" --project "$project"
}

rag_clear() {
    local project="${1:-$(rag_detect_project)}"
    curl -s -X DELETE "$RAG_BASE_URL/projects/$project"
}

rag_status() {
    local project
    project="$(rag_detect_project)"
    curl -s "$RAG_BASE_URL/projects/$project/stats"
}
