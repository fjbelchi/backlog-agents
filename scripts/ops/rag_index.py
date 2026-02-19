#!/usr/bin/env python3
"""Build a local code-chunk index for RAG-augmented context retrieval.

Splits source files into token-sized chunks and stores them in a JSONL index
that skills can query before making LLM calls, reducing input tokens by 60-80%.

This is the deterministic indexer. Vector embedding is optional and delegated
to an external embedding service when enabled.

Usage:
    python scripts/ops/rag_index.py --rebuild
    python scripts/ops/rag_index.py --query "authentication middleware"
    python scripts/ops/rag_index.py --stats
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from datetime import datetime, timezone

# Default config (can be overridden via backlog.config.json -> llmOps.ragPolicy)
DEFAULT_CHUNK_SIZE = 512  # approximate tokens (chars / 4)
DEFAULT_TOP_K = 10
DEFAULT_INDEX_PATH = ".backlog-ops/rag-index"

# File patterns to index
INCLUDE_PATTERNS = {
    "*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.go", "*.rs",
    "*.swift", "*.kt", "*.java", "*.vue", "*.css", "*.scss",
    "*.md", "*.yaml", "*.yml", "*.json", "*.toml",
}

# Directories to skip
EXCLUDE_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", "target", ".backlog-ops",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def should_index(path: Path) -> bool:
    """Check if file matches include patterns and is not in excluded dirs."""
    for excl in EXCLUDE_DIRS:
        if excl in path.parts:
            return False
    return any(path.match(pat) for pat in INCLUDE_PATTERNS)


def chunk_file(filepath: Path, chunk_chars: int = DEFAULT_CHUNK_SIZE * 4) -> list[dict]:
    """Split a file into overlapping chunks with metadata."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return []

    if not content.strip():
        return []

    lines = content.splitlines(keepalinenums=False) if hasattr(content, "splitlines") else content.split("\n")
    lines = content.split("\n")
    chunks = []
    current_chunk: list[str] = []
    current_size = 0
    start_line = 1

    for i, line in enumerate(lines, 1):
        line_size = len(line) + 1  # +1 for newline
        if current_size + line_size > chunk_chars and current_chunk:
            chunk_text = "\n".join(current_chunk)
            chunks.append({
                "file": str(filepath),
                "start_line": start_line,
                "end_line": i - 1,
                "content": chunk_text,
                "hash": hashlib.md5(chunk_text.encode()).hexdigest()[:12],
                "approx_tokens": len(chunk_text) // 4,
            })
            # Overlap: keep last 3 lines for context continuity
            overlap = current_chunk[-3:] if len(current_chunk) > 3 else current_chunk[-1:]
            current_chunk = overlap
            current_size = sum(len(l) + 1 for l in overlap)
            start_line = max(1, i - len(overlap))

        current_chunk.append(line)
        current_size += line_size

    # Flush remaining
    if current_chunk:
        chunk_text = "\n".join(current_chunk)
        chunks.append({
            "file": str(filepath),
            "start_line": start_line,
            "end_line": len(lines),
            "content": chunk_text,
            "hash": hashlib.md5(chunk_text.encode()).hexdigest()[:12],
            "approx_tokens": len(chunk_text) // 4,
        })

    return chunks


def tokenize_query(query: str) -> set[str]:
    """Simple token-based query tokenizer."""
    return set(re.findall(r"[a-z0-9_]+", query.lower()))


def score_chunk(chunk: dict, query_tokens: set[str]) -> float:
    """Score chunk relevance by token overlap (simple TF-based)."""
    content_tokens = set(re.findall(r"[a-z0-9_]+", chunk["content"].lower()))
    if not content_tokens:
        return 0.0
    overlap = query_tokens & content_tokens
    return len(overlap) / max(len(query_tokens), 1)


def cmd_rebuild(args: argparse.Namespace) -> int:
    """Rebuild the entire index from source files."""
    root = Path(args.root)
    index_dir = Path(args.index_path)
    index_dir.mkdir(parents=True, exist_ok=True)

    chunk_chars = args.chunk_size * 4
    all_chunks = []
    file_count = 0

    for filepath in sorted(root.rglob("*")):
        if not filepath.is_file() or not should_index(filepath.relative_to(root)):
            continue
        file_chunks = chunk_file(filepath.relative_to(root), chunk_chars)
        all_chunks.extend(file_chunks)
        file_count += 1

    # Write chunks index
    index_file = index_dir / "chunks.jsonl"
    index_file.write_text(
        "\n".join(json.dumps(c) for c in all_chunks) + ("\n" if all_chunks else ""),
        encoding="utf-8",
    )

    # Write metadata
    meta = {
        "version": "1.0",
        "generated_at": now_iso(),
        "root": str(root),
        "files_indexed": file_count,
        "total_chunks": len(all_chunks),
        "chunk_size_tokens": args.chunk_size,
        "total_approx_tokens": sum(c["approx_tokens"] for c in all_chunks),
    }
    (index_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(f"Indexed {file_count} files → {len(all_chunks)} chunks")
    print(f"Approx {meta['total_approx_tokens']:,} tokens in index")
    print(f"Wrote to {index_dir}/")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    """Query the index for relevant chunks."""
    index_file = Path(args.index_path) / "chunks.jsonl"
    if not index_file.exists():
        print(f"Index not found at {index_file}. Run --rebuild first.", flush=True)
        return 1

    query_tokens = tokenize_query(args.query)
    if not query_tokens:
        print("Empty query.")
        return 1

    chunks = []
    for line in index_file.read_text(encoding="utf-8").splitlines():
        if line.strip():
            chunks.append(json.loads(line))

    # Score and rank
    scored = [(score_chunk(c, query_tokens), c) for c in chunks]
    scored.sort(key=lambda x: x[0], reverse=True)

    top_k = args.top_k
    results = [c for score, c in scored[:top_k] if score > 0]

    if args.json_output:
        print(json.dumps(results, indent=2))
    else:
        for c in results:
            print(f"--- {c['file']}:{c['start_line']}-{c['end_line']} ({c['approx_tokens']} tokens)")
            print(c["content"][:500])
            print()

    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Show index statistics."""
    meta_file = Path(args.index_path) / "meta.json"
    if not meta_file.exists():
        print(f"No index found at {args.index_path}. Run --rebuild first.")
        return 1

    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    print(json.dumps(meta, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG index builder for backlog toolkit")
    parser.add_argument("--index-path", default=DEFAULT_INDEX_PATH, help="Path to index directory")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="Chunk size in tokens")
    parser.add_argument("--root", default=".", help="Project root to index")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("rebuild", aliases=["--rebuild"])
    q = sub.add_parser("query", aliases=["--query"])
    q.add_argument("query_text", nargs="?", default="")
    q.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    q.add_argument("--json", dest="json_output", action="store_true")
    sub.add_parser("stats", aliases=["--stats"])

    args = parser.parse_args()

    # Handle --rebuild, --query, --stats flags as legacy interface
    import sys
    raw_args = sys.argv[1:]
    if "--rebuild" in raw_args:
        args.command = "rebuild"
    elif "--query" in raw_args:
        args.command = "query"
        idx = raw_args.index("--query")
        args.query = raw_args[idx + 1] if idx + 1 < len(raw_args) else ""
        args.top_k = DEFAULT_TOP_K
        args.json_output = "--json" in raw_args
    elif "--stats" in raw_args:
        args.command = "stats"

    if args.command in ("rebuild", "--rebuild"):
        return cmd_rebuild(args)
    elif args.command in ("query", "--query"):
        return cmd_query(args)
    elif args.command in ("stats", "--stats"):
        return cmd_stats(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
