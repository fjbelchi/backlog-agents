#!/usr/bin/env python3
"""
RAG Server for Backlog Toolkit
Provides code search and retrieval via HTTP API
"""

import os
import sys
import argparse
import logging
from typing import Optional, Dict, Any
from pathlib import Path

try:
    from flask import Flask, jsonify, request
    import chromadb
    from sentence_transformers import SentenceTransformer
except ImportError as e:
    print(f"Error: Missing dependencies. Install with:")
    print(f"  pip install flask chromadb sentence-transformers")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# Per-project ChromaDB base path — can be overridden by env var or test monkeypatch
BASE_PATH = os.environ.get("RAG_BASE_PATH", os.path.expanduser("~/.backlog-toolkit/rag/chroma"))

# Per-project state: project_name -> client / collection
_clients: dict = {}
_collections: dict = {}

# Embedding model — loaded lazily on first use
_embedder: Optional[SentenceTransformer] = None


def _get_embedder() -> SentenceTransformer:
    """Return the embedding model, loading it on first call."""
    global _embedder
    if _embedder is None:
        logger.info("Loading embedding model...")
        _embedder = SentenceTransformer('all-MiniLM-L6-v2')
    return _embedder


def _get_project(request_data: dict) -> str:
    """Resolve the project name from request header or body, defaulting to 'default'."""
    return (
        request.headers.get("X-Project")
        or (request_data or {}).get("project")
        or "default"
    )


def _get_collection(project: str):
    """Return (or lazily create) the ChromaDB collection for the given project."""
    if project not in _clients:
        path = os.path.join(BASE_PATH, project)
        Path(path).mkdir(parents=True, exist_ok=True)
        _clients[project] = chromadb.PersistentClient(path=path)
        _collections[project] = _clients[project].get_or_create_collection(
            name="codebase",
            metadata={"description": f"Index for project {project}"}
        )
    return _collections[project]


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "projects_loaded": list(_clients.keys())
    })


@app.route('/search', methods=['POST'])
def search():
    """Search for relevant code snippets"""
    try:
        data = request.get_json()
        query = data.get('query')
        n_results = data.get('n_results', 5)

        if not query:
            return jsonify({"error": "query is required"}), 400

        project = _get_project(data)
        col = _get_collection(project)

        # Embed query
        query_embedding = _get_embedder().encode(query).tolist()

        # Search collection — clamp n_results to available docs
        count = col.count()
        if count == 0:
            return jsonify({"query": query, "project": project, "results": {"documents": [[]], "metadatas": [[]], "ids": [[]], "distances": [[]]}})

        safe_n = min(n_results, count)
        results = col.query(
            query_embeddings=[query_embedding],
            n_results=safe_n
        )

        return jsonify({
            "query": query,
            "project": project,
            "results": results
        })

    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/index', methods=['POST'])
def index():
    """Index code snippets"""
    try:
        data = request.get_json()
        documents = data.get('documents', [])
        metadatas = data.get('metadatas', [])
        ids = data.get('ids', [])

        if not documents:
            return jsonify({"error": "documents is required"}), 400

        project = _get_project(data)
        col = _get_collection(project)

        # Generate IDs if not provided
        if not ids:
            ids = [f"doc_{i}" for i in range(len(documents))]

        # Embed documents
        embeddings = _get_embedder().encode(documents).tolist()

        # Upsert to collection (idempotent — same ID overwrites existing entry)
        col.upsert(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas if metadatas else None,
            ids=ids
        )

        return jsonify({
            "indexed": len(documents),
            "project": project
        })

    except Exception as e:
        logger.error(f"Index error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/stats', methods=['GET'])
def stats():
    """Get collection statistics for the default project (or X-Project header)"""
    try:
        project = _get_project({})
        col = _get_collection(project)
        return jsonify({
            "project": project,
            "collection_name": col.name,
            "document_count": col.count(),
            "metadata": col.metadata
        })
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return jsonify({"error": str(e)}), 500


def main():
    parser = argparse.ArgumentParser(description="RAG Server for Backlog Toolkit")
    parser.add_argument('--port', type=int, default=8001, help='Port to run on')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind to')
    parser.add_argument('--db-path', help='ChromaDB base path (overrides RAG_BASE_PATH env var)')
    args = parser.parse_args()

    if args.db_path:
        global BASE_PATH
        BASE_PATH = args.db_path

    # Start server — per-project collections are created lazily on first request
    logger.info(f"Starting RAG server on {args.host}:{args.port}")
    logger.info(f"ChromaDB base path: {BASE_PATH}")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == '__main__':
    main()
