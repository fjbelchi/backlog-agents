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


@app.route('/projects', methods=['GET'])
def list_projects():
    """List all indexed projects with document counts."""
    base = Path(BASE_PATH)
    projects = []
    if base.exists():
        for d in sorted(base.iterdir()):
            if d.is_dir():
                col = _get_collection(d.name)
                try:
                    code_ids = col.get(where={"type": "code"})["ids"]
                    ticket_ids = col.get(where={"type": "ticket"})["ids"]
                except Exception:
                    code_ids, ticket_ids = [], []
                projects.append({
                    "name": d.name,
                    "count": col.count(),
                    "code_count": len(code_ids),
                    "ticket_count": len(ticket_ids),
                })
    return jsonify({"projects": projects})


@app.route('/projects/<name>', methods=['DELETE'])
def delete_project(name):
    """Delete a project's index and all its data."""
    import shutil
    if name in _clients:
        del _clients[name]
        del _collections[name]
    path = os.path.join(BASE_PATH, name)
    if os.path.exists(path):
        shutil.rmtree(path)
    return jsonify({"deleted": name})


@app.route('/projects/<name>/stats', methods=['GET'])
def project_stats(name):
    """Get statistics for a specific project."""
    col = _get_collection(name)
    return jsonify({"name": name, "count": col.count(), "metadata": col.metadata})


@app.route('/projects/<name>/init', methods=['POST'])
def init_project(name):
    """Pre-initialize a project collection without indexing any documents."""
    _get_collection(name)
    return jsonify({"initialized": name})


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


UI_HTML = """<!DOCTYPE html>
<html><head><title>RAG UI</title>
<style>body{font-family:monospace;padding:20px;max-width:900px}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #ccc;padding:6px 10px;text-align:left}
th{background:#f5f5f5}.result{background:#f9f9f9;padding:8px;margin:4px 0;border-left:3px solid #666}
input{margin:0 4px;padding:4px}button{padding:4px 12px}</style>
</head><body>
<h2>RAG Server</h2>
<h3>Projects</h3>
<div id="projects">Loading...</div>
<h3>Search</h3>
<form id="sf">
  Project: <input id="proj" placeholder="project-name" size="20">
  Query: <input id="q" size="40" placeholder="authentication logic">
  N: <input id="n" value="5" size="3">
  <button type="submit">Search</button>
</form>
<div id="results"></div>
<script>
fetch('/projects').then(r=>r.json()).then(d=>{
  const rows=d.projects.map(p=>`<tr><td>${p.name}</td><td>${p.code_count}</td><td>${p.ticket_count}</td><td>${p.count}</td></tr>`).join('');
  document.getElementById('projects').innerHTML=`<table><tr><th>Project</th><th>Code</th><th>Tickets</th><th>Total</th></tr>${rows||'<tr><td colspan=4>No projects indexed yet</td></tr>'}</table>`;
});
document.getElementById('sf').addEventListener('submit',e=>{
  e.preventDefault();
  fetch('/search',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({project:document.getElementById('proj').value||'default',
      query:document.getElementById('q').value,n_results:parseInt(document.getElementById('n').value)||5})
  }).then(r=>r.json()).then(d=>{
    const docs=(d.results&&d.results.documents&&d.results.documents[0])||[];
    const metas=(d.results&&d.results.metadatas&&d.results.metadatas[0])||[];
    document.getElementById('results').innerHTML=docs.length?docs.map((doc,i)=>
      `<div class="result"><b>${(metas[i]||{}).file||''}</b> [${(metas[i]||{}).type||''}]<pre>${doc.replace(/</g,'&lt;').slice(0,400)}</pre></div>`
    ).join(''):'<p>No results</p>';
  });
});
</script></body></html>"""


@app.route('/ui', methods=['GET'])
def ui():
    """Serve a minimal HTML dashboard for browsing projects and running searches."""
    return UI_HTML, 200, {'Content-Type': 'text/html; charset=utf-8'}


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
