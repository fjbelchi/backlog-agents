# Project-Aware RAG — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the RAG server and surrounding infrastructure to support per-project ChromaDB isolation, project auto-detection, always-on file watching, and explicit RAG integration hooks in all backlog skills.

**Architecture:** Single RAG Docker container with per-project ChromaDB paths under `/data/chroma/{project_name}/`. A RagClient helper (Python + Shell) auto-detects the active project from `backlog.config.json` walking up from CWD. An always-on host-side file watcher indexes code and ticket changes in real time.

**Tech Stack:** Python 3.11, Flask, ChromaDB, sentence-transformers, watchdog, bash

---

### Task 1: Refactor RAG server — project-aware paths + upsert

**Files:**
- Modify: `scripts/rag/server.py`
- Create: `tests/test_rag_server.py`

**Step 1: Write failing test**

```python
# tests/test_rag_server.py
import pytest, sys
sys.path.insert(0, "scripts/rag")
import server
server.app.config["TESTING"] = True

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "BASE_PATH", str(tmp_path))
    server._clients.clear()
    with server.app.test_client() as c:
        yield c

def test_project_isolation(client):
    client.post("/index", json={
        "project": "alpha",
        "documents": ["def login(): pass"],
        "ids": ["alpha::auth.py::0"],
        "metadatas": [{"type": "code", "file": "auth.py"}]
    })
    client.post("/index", json={
        "project": "beta",
        "documents": ["def checkout(): pass"],
        "ids": ["beta::shop.py::0"],
        "metadatas": [{"type": "code", "file": "shop.py"}]
    })
    r = client.post("/search", json={"project": "alpha", "query": "login", "n_results": 5})
    docs = r.get_json()["results"]["documents"][0]
    assert any("login" in d for d in docs)
    assert not any("checkout" in d for d in docs)
```

**Step 2: Run to verify it fails**

```bash
pip install pytest flask chromadb sentence-transformers
pytest tests/test_rag_server.py::test_project_isolation -v
# Expected: AttributeError or AssertionError (no BASE_PATH or _clients)
```

**Step 3: Implement changes in server.py**

Replace the global `db_client`/`collection` pattern with per-project clients:

```python
import os
from pathlib import Path

BASE_PATH = os.environ.get("RAG_BASE_PATH", os.path.expanduser("~/.backlog-toolkit/rag/chroma"))
_clients: dict = {}   # project_name -> chromadb.PersistentClient
_collections: dict = {}  # project_name -> Collection

def _get_project(request_data: dict) -> str:
    return (
        request.headers.get("X-Project")
        or (request_data or {}).get("project")
        or "default"
    )

def _get_collection(project: str):
    if project not in _clients:
        path = os.path.join(BASE_PATH, project)
        Path(path).mkdir(parents=True, exist_ok=True)
        _clients[project] = chromadb.PersistentClient(path=path)
        _collections[project] = _clients[project].get_or_create_collection(
            name="codebase",
            metadata={"description": f"Index for project {project}"}
        )
    return _collections[project]
```

Update `/index` to use `upsert()`:
```python
@app.route('/index', methods=['POST'])
def index():
    data = request.get_json()
    project = _get_project(data)
    col = _get_collection(project)
    embeddings = embedder.encode(data["documents"]).tolist()
    col.upsert(
        documents=data["documents"],
        embeddings=embeddings,
        metadatas=data.get("metadatas"),
        ids=data["ids"]
    )
    return jsonify({"indexed": len(data["documents"]), "project": project})
```

Update `/search` and `/health` similarly to use `_get_project()` and `_get_collection()`.

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_rag_server.py::test_project_isolation -v
# Expected: PASSED
```

**Step 5: Commit**

```bash
git add scripts/rag/server.py tests/test_rag_server.py
git commit -m "feat(rag): project-aware ChromaDB paths + upsert deduplication"
```

---

### Task 2: Add /projects endpoints to RAG server

**Files:**
- Modify: `scripts/rag/server.py`
- Modify: `tests/test_rag_server.py`

**Step 1: Write failing tests**

```python
def test_list_projects(client):
    client.post("/index", json={"project": "proj-a", "documents": ["x"], "ids": ["proj-a::f::0"], "metadatas": [{"type":"code"}]})
    r = client.get("/projects")
    assert r.status_code == 200
    names = [p["name"] for p in r.get_json()["projects"]]
    assert "proj-a" in names

def test_delete_project(client):
    client.post("/index", json={"project": "to-delete", "documents": ["x"], "ids": ["to-delete::f::0"], "metadatas": [{"type":"code"}]})
    r = client.delete("/projects/to-delete")
    assert r.status_code == 200
    r2 = client.get("/projects")
    names = [p["name"] for p in r2.get_json()["projects"]]
    assert "to-delete" not in names
```

**Step 2: Run to verify they fail**

```bash
pytest tests/test_rag_server.py::test_list_projects tests/test_rag_server.py::test_delete_project -v
# Expected: 404 Not Found
```

**Step 3: Implement endpoints**

```python
@app.route('/projects', methods=['GET'])
def list_projects():
    base = Path(BASE_PATH)
    projects = []
    if base.exists():
        for d in base.iterdir():
            if d.is_dir():
                col = _get_collection(d.name)
                meta = col.metadata or {}
                projects.append({
                    "name": d.name,
                    "count": col.count(),
                    "code_count": len(col.get(where={"type": "code"})["ids"]),
                    "ticket_count": len(col.get(where={"type": "ticket"})["ids"]),
                })
    return jsonify({"projects": projects})

@app.route('/projects/<name>', methods=['DELETE'])
def delete_project(name):
    import shutil
    path = os.path.join(BASE_PATH, name)
    if name in _clients:
        del _clients[name]
        del _collections[name]
    if os.path.exists(path):
        shutil.rmtree(path)
    return jsonify({"deleted": name})

@app.route('/projects/<name>/stats', methods=['GET'])
def project_stats(name):
    col = _get_collection(name)
    return jsonify({"name": name, "count": col.count(), "metadata": col.metadata})

@app.route('/projects/<name>/init', methods=['POST'])
def init_project(name):
    _get_collection(name)  # creates if not exists
    return jsonify({"initialized": name})
```

**Step 4: Run tests**

```bash
pytest tests/test_rag_server.py -v
# Expected: all PASSED
```

**Step 5: Commit**

```bash
git add scripts/rag/server.py tests/test_rag_server.py
git commit -m "feat(rag): add /projects CRUD endpoints"
```

---

### Task 3: Add /ui mini HTML endpoint

**Files:**
- Modify: `scripts/rag/server.py`
- Modify: `tests/test_rag_server.py`

**Step 1: Write failing test**

```python
def test_ui_endpoint(client):
    r = client.get("/ui")
    assert r.status_code == 200
    html = r.data.decode()
    assert "<form" in html
    assert "<table" in html
    assert "X-Project" in html or "project" in html
```

**Step 2: Verify it fails**

```bash
pytest tests/test_rag_server.py::test_ui_endpoint -v
# Expected: 404
```

**Step 3: Implement /ui**

```python
UI_HTML = """<!DOCTYPE html>
<html><head><title>RAG UI</title>
<style>body{font-family:monospace;padding:20px;max-width:900px}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #ccc;padding:6px 10px;text-align:left}
th{background:#f5f5f5}.result{background:#f9f9f9;padding:8px;margin:4px 0;border-left:3px solid #666}</style>
</head><body>
<h2>RAG Server</h2>
<h3>Projects</h3>
<div id="projects">Loading...</div>
<h3>Search</h3>
<form id="sf">
  Project: <input id="proj" placeholder="project-name">
  Query: <input id="q" size="40" placeholder="authentication logic">
  N: <input id="n" value="5" size="3">
  <button type="submit">Search</button>
</form>
<div id="results"></div>
<script>
fetch('/projects').then(r=>r.json()).then(d=>{
  const rows = d.projects.map(p=>`<tr><td>${p.name}</td><td>${p.code_count}</td><td>${p.ticket_count}</td></tr>`).join('');
  document.getElementById('projects').innerHTML = `<table><tr><th>Project</th><th>Code</th><th>Tickets</th></tr>${rows}</table>`;
});
document.getElementById('sf').addEventListener('submit',e=>{
  e.preventDefault();
  fetch('/search',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({project:document.getElementById('proj').value,
      query:document.getElementById('q').value,n_results:parseInt(document.getElementById('n').value)})
  }).then(r=>r.json()).then(d=>{
    const docs = (d.results&&d.results.documents&&d.results.documents[0])||[];
    const metas = (d.results&&d.results.metadatas&&d.results.metadatas[0])||[];
    document.getElementById('results').innerHTML = docs.map((doc,i)=>
      `<div class="result"><b>${(metas[i]||{}).file||''}</b><pre>${doc.slice(0,300)}</pre></div>`
    ).join('');
  });
});
</script></body></html>"""

@app.route('/ui', methods=['GET'])
def ui():
    return UI_HTML, 200, {'Content-Type': 'text/html'}
```

**Step 4: Run tests**

```bash
pytest tests/test_rag_server.py -v
# Expected: all PASSED
```

**Step 5: Commit**

```bash
git add scripts/rag/server.py tests/test_rag_server.py
git commit -m "feat(rag): add /ui mini HTML dashboard"
```

---

### Task 4: Create RagClient Python class

**Files:**
- Create: `scripts/rag/client.py`
- Create: `tests/test_rag_client.py`

**Step 1: Write failing tests**

```python
# tests/test_rag_client.py
import json, pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

def test_detect_project_from_config(tmp_path):
    config = tmp_path / "backlog.config.json"
    config.write_text(json.dumps({"project": {"name": "my-api"}}))
    with patch("os.getcwd", return_value=str(tmp_path)):
        from scripts.rag.client import RagClient
        c = RagClient()
        assert c.project == "my-api"

def test_detect_project_fallback(tmp_path):
    with patch("os.getcwd", return_value=str(tmp_path)):
        from scripts.rag.client import RagClient
        c = RagClient()
        assert c.project == tmp_path.name

def test_search_sends_project(tmp_path):
    with patch("os.getcwd", return_value=str(tmp_path)):
        from scripts.rag.client import RagClient
        c = RagClient(project="test-proj")
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(json=lambda: {"results": []})
            c.search("auth logic")
            body = mock_post.call_args[1]["json"]
            assert body["project"] == "test-proj"
            assert body["query"] == "auth logic"
```

**Step 2: Verify they fail**

```bash
pytest tests/test_rag_client.py -v
# Expected: ModuleNotFoundError (file doesn't exist)
```

**Step 3: Implement client.py**

```python
# scripts/rag/client.py
import json, os, requests
from pathlib import Path

class RagClient:
    def __init__(self, project: str = None, base_url: str = None):
        self.base_url = base_url or os.environ.get("RAG_BASE_URL", "http://localhost:8001")
        self.project = project or self._detect_project()

    def _detect_project(self) -> str:
        path = Path(os.getcwd())
        for p in [path] + list(path.parents):
            cfg = p / "backlog.config.json"
            if cfg.exists():
                try:
                    return json.loads(cfg.read_text())["project"]["name"]
                except (KeyError, json.JSONDecodeError):
                    pass
        return path.name

    def search(self, query: str, n: int = 5, filter: dict = None) -> list:
        r = requests.post(f"{self.base_url}/search", json={
            "project": self.project, "query": query,
            "n_results": n, **({"filter": filter} if filter else {})
        })
        return r.json().get("results", {})

    def index_files(self, paths: list, type: str = "code") -> dict:
        docs, ids, metas = [], [], []
        for path in paths:
            p = Path(path)
            if not p.exists(): continue
            rel = str(p.relative_to(Path(os.getcwd())) if p.is_absolute() else p)
            docs.append(p.read_text(errors="ignore")[:2000])
            ids.append(f"{self.project}::{rel}::0")
            metas.append({"type": type, "file": rel, "project": self.project})
        if not docs:
            return {"indexed": 0}
        r = requests.post(f"{self.base_url}/index", json={
            "project": self.project, "documents": docs, "ids": ids, "metadatas": metas
        })
        return r.json()

    def upsert_file(self, path: str, type: str = "code") -> dict:
        return self.index_files([path], type=type)

    def clear(self) -> dict:
        r = requests.delete(f"{self.base_url}/projects/{self.project}")
        return r.json()

    def stats(self) -> dict:
        r = requests.get(f"{self.base_url}/projects/{self.project}/stats")
        return r.json()
```

**Step 4: Run tests**

```bash
pytest tests/test_rag_client.py -v
# Expected: all PASSED
```

**Step 5: Commit**

```bash
git add scripts/rag/client.py tests/test_rag_client.py
git commit -m "feat(rag): add RagClient Python class with project auto-detection"
```

---

### Task 5: Create shell wrapper + Makefile targets

**Files:**
- Create: `scripts/rag/client.sh`
- Modify: `Makefile`

**Step 1: Create client.sh**

```bash
# scripts/rag/client.sh
#!/usr/bin/env bash
RAG_BASE_URL="${RAG_BASE_URL:-http://localhost:8001}"

rag_detect_project() {
    local dir="${1:-$(pwd)}"
    while [ "$dir" != "/" ]; do
        if [ -f "$dir/backlog.config.json" ]; then
            python3 -c "import json,sys; print(json.load(open('$dir/backlog.config.json'))['project']['name'])" 2>/dev/null && return
        fi
        dir="$(dirname "$dir")"
    done
    basename "$(pwd)"
}

rag_search() {
    local query="$1" n="${2:-5}" project
    project="$(rag_detect_project)"
    curl -s -X POST "$RAG_BASE_URL/search" \
        -H "Content-Type: application/json" \
        -H "X-Project: $project" \
        -d "{\"project\":\"$project\",\"query\":\"$query\",\"n_results\":$n}"
}

rag_index_dir() {
    local dir="${1:-.}" project
    project="$(rag_detect_project)"
    find "$dir" -type f \( -name "*.py" -o -name "*.ts" -o -name "*.js" -o -name "*.go" -o -name "*.rs" -o -name "*.md" \) | while read -r f; do
        python3 "$(dirname "${BASH_SOURCE[0]}")/client.py" upsert "$f" --project "$project" 2>/dev/null
    done
    echo "Indexed $dir for project: $project"
}

rag_upsert_file() {
    local file="$1" project
    project="$(rag_detect_project)"
    python3 "$(dirname "${BASH_SOURCE[0]}")/client.py" upsert "$file" --project "$project"
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
```

**Step 2: Add CLI entrypoint to client.py**

Add at the bottom of `scripts/rag/client.py`:

```python
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    proj = next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == "--project"), None)
    c = RagClient(project=proj)
    if cmd == "upsert" and len(sys.argv) > 2:
        print(c.upsert_file(sys.argv[2]))
    elif cmd == "stats":
        print(c.stats())
    elif cmd == "clear":
        print(c.clear())
```

**Step 3: Add Makefile targets**

Find the `validate-docs` section in `Makefile` and add before it:

```makefile
## ─── RAG ────────────────────────────────────────────────────────────
rag-status: ## Show RAG index stats for current project
	@source scripts/rag/client.sh && rag_status | python3 -m json.tool

rag-index: ## Index project files into RAG (make rag-index DIR=./src)
	@source scripts/rag/client.sh && rag_index_dir "$(or $(DIR),.)"

rag-search: ## Search RAG (make rag-search QUERY="auth logic")
	@test -n "$(QUERY)" || (echo "Usage: make rag-search QUERY=\"auth logic\"" && exit 1)
	@source scripts/rag/client.sh && rag_search "$(QUERY)" | python3 -m json.tool

rag-clear: ## Clear RAG index for current project (make rag-clear [PROJECT=name])
	@source scripts/rag/client.sh && rag_clear "$(PROJECT)"
```

**Step 4: Verify manually**

```bash
# Verify syntax
bash -n scripts/rag/client.sh && echo "Shell: OK"
python3 -m py_compile scripts/rag/client.py && echo "Python: OK"
```

**Step 5: Commit**

```bash
chmod +x scripts/rag/client.sh
git add scripts/rag/client.sh scripts/rag/client.py Makefile
git commit -m "feat(rag): add shell client wrapper and Makefile rag-* targets"
```

---

### Task 6: Create file watcher

**Files:**
- Create: `scripts/rag/watcher.py`
- Create: `tests/test_watcher.py`

**Step 1: Write failing test**

```python
# tests/test_watcher.py
import json, time, threading
from pathlib import Path
from unittest.mock import patch, MagicMock

def test_watcher_indexes_new_file(tmp_path):
    cfg = tmp_path / "backlog.config.json"
    cfg.write_text(json.dumps({"project": {"name": "watch-test"}}))
    upserted = []
    with patch("scripts.rag.watcher.RagClient") as MockClient:
        instance = MockClient.return_value
        instance.upsert_file.side_effect = lambda p, **kw: upserted.append(p)
        import scripts.rag.watcher as w
        obs = w.start_watcher(str(tmp_path), debounce_seconds=0.1)
        time.sleep(0.3)
        (tmp_path / "main.py").write_text("def hello(): pass")
        time.sleep(0.5)
        obs.stop()
        obs.join()
    assert any("main.py" in str(p) for p in upserted)
```

**Step 2: Verify it fails**

```bash
pip install watchdog
pytest tests/test_watcher.py -v
# Expected: ModuleNotFoundError
```

**Step 3: Implement watcher.py**

```python
# scripts/rag/watcher.py
#!/usr/bin/env python3
import os, sys, time, json, signal, argparse, threading
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rag.client import RagClient
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

CODE_EXTS = {".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".java", ".md"}

def _get_project(watch_dir: str) -> str:
    path = Path(watch_dir)
    for p in [path] + list(path.parents):
        cfg = p / "backlog.config.json"
        if cfg.exists():
            try:
                return json.loads(cfg.read_text())["project"]["name"]
            except Exception:
                pass
    return path.name

class _Handler(FileSystemEventHandler):
    def __init__(self, client: RagClient, debounce: float = 2.0):
        self.client = client
        self.debounce = debounce
        self._pending: dict = {}
        self._lock = threading.Lock()

    def _schedule(self, path: str, deleted: bool = False):
        with self._lock:
            self._pending[path] = ("delete" if deleted else "upsert")
        threading.Timer(self.debounce, self._flush, args=[path]).start()

    def _flush(self, path: str):
        with self._lock:
            action = self._pending.pop(path, None)
        if not action:
            return
        try:
            if action == "upsert":
                ext = Path(path).suffix
                t = "ticket" if "backlog/data" in path else "code"
                self.client.upsert_file(path, type=t)
                print(f"[watcher] indexed: {path}")
        except Exception as e:
            print(f"[watcher] error: {e}")

    def on_modified(self, event):
        if not event.is_directory and Path(event.src_path).suffix in CODE_EXTS:
            self._schedule(event.src_path)

    def on_created(self, event):
        if not event.is_directory and Path(event.src_path).suffix in CODE_EXTS:
            self._schedule(event.src_path)

def start_watcher(watch_dir: str, debounce_seconds: float = 2.0) -> Observer:
    project = _get_project(watch_dir)
    client = RagClient(project=project)
    handler = _Handler(client, debounce=debounce_seconds)
    observer = Observer()
    observer.schedule(handler, watch_dir, recursive=True)
    observer.start()
    print(f"[watcher] watching {watch_dir} → project: {project}")
    return observer

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", default=os.getcwd())
    args = parser.parse_args()
    obs = start_watcher(args.watch)
    try:
        while obs.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        obs.stop()
    obs.join()

if __name__ == "__main__":
    main()
```

**Step 4: Run test**

```bash
pytest tests/test_watcher.py -v
# Expected: PASSED
```

**Step 5: Commit**

```bash
git add scripts/rag/watcher.py tests/test_watcher.py
git commit -m "feat(rag): add always-on file watcher with debounce and project auto-detection"
```

---

### Task 7: Auto-start watcher in claude-with-services.sh

**Files:**
- Modify: `claude-with-services.sh`

**Step 1: Read current file**

Current `claude-with-services.sh` calls `start-services.sh` then launches `claude`. There is no watcher start or PID tracking.

**Step 2: Add watcher lifecycle**

Replace the content after `"$SCRIPT_DIR/scripts/services/start-services.sh"` succeeds:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WATCHER_PID_FILE="/tmp/backlog-rag-watcher.pid"

# Kill watcher on exit
cleanup() {
    if [ -f "$WATCHER_PID_FILE" ]; then
        pid="$(cat "$WATCHER_PID_FILE")"
        kill "$pid" 2>/dev/null && echo "Watcher stopped (PID $pid)"
        rm -f "$WATCHER_PID_FILE"
    fi
}
trap cleanup EXIT INT TERM

# Start services
"$SCRIPT_DIR/scripts/services/start-services.sh"

# Start file watcher in background
echo "Starting RAG file watcher..."
python3 "$SCRIPT_DIR/scripts/rag/watcher.py" --watch "$(pwd)" &
echo $! > "$WATCHER_PID_FILE"
echo "Watcher started (PID $(cat "$WATCHER_PID_FILE")) — watching $(pwd)"

echo ""
echo "Starting Claude Code..."
echo ""

if command -v claude &> /dev/null; then
    claude "$@"
else
    echo "Error: claude command not found"
    echo "Install with: npm install -g @anthropic-ai/claude-code"
    exit 1
fi
```

**Step 3: Verify syntax**

```bash
bash -n claude-with-services.sh && echo "Syntax OK"
```

**Step 4: Commit**

```bash
git add claude-with-services.sh
git commit -m "feat(rag): auto-start file watcher in claude-with-services.sh"
```

---

### Task 8: Integrate RAG into backlog-init SKILL.md

**Files:**
- Modify: `skills/backlog-init/SKILL.md`

**Step 1: Find the final step**

The last step in `backlog-init/SKILL.md` is "Step 6: Report Success". Add a new step before it.

**Step 2: Add RAG init step**

Find the line `## Step 6: Report Success` (or equivalent last step) and insert before it:

```markdown
## Step N: Initialize RAG Index

Check if `llmOps.ragPolicy.enabled` is `true` in the generated `backlog.config.json`.

If enabled:
1. Check RAG server health: `curl -sf http://localhost:8001/health`
2. If reachable, run initial index:
   ```bash
   source scripts/rag/client.sh
   rag_index_dir .
   # Also index any existing tickets
   [ -d backlog/data ] && rag_index_dir backlog/data
   ```
3. Log: `"✓ RAG index initialized for project {project.name} — $(rag_status | python3 -m json.tool)"`

If RAG server is unreachable: log a warning `"⚠ RAG server not reachable — skipping initial index. Run 'make rag-index' when services are up."` and continue without error.
```

**Step 3: Verify file is valid**

```bash
# Check the SKILL.md has the new step
grep -c "Initialize RAG Index" skills/backlog-init/SKILL.md
# Expected: 1
```

**Step 4: Commit**

```bash
git add skills/backlog-init/SKILL.md
git commit -m "feat(rag): add RAG init step to backlog-init skill"
```

---

### Task 9: Integrate RAG into backlog-ticket and backlog-refinement

**Files:**
- Modify: `skills/backlog-ticket/SKILL.md`
- Modify: `skills/backlog-refinement/SKILL.md`

**Step 1: Update backlog-ticket**

In `skills/backlog-ticket/SKILL.md`, find **Phase 1: Analysis → 1.1 Read Configuration** and add after it:

```markdown
### 1.1b RAG Context Enrichment (if enabled)

If `llmOps.ragPolicy.enabled` is `true` and RAG server is reachable:

```python
from scripts.rag.client import RagClient
rag = RagClient()
snippets = rag.search(ticket_description, n=5)
# Inject top snippets into the context section of the ticket
# and use them to pre-fill affectedFiles with real paths from metadata
```

This reduces hallucinated file paths and enriches `context` with real code references.
```

Then find the step that **writes the ticket file** and add after it:

```markdown
### Post-Save: Index Ticket in RAG

If `llmOps.ragPolicy.enabled`:
```python
rag.upsert_file(ticket_path, type="ticket")
# This makes the ticket searchable for sentinel deduplication and implementer recurring-pattern memory
```
```

**Step 2: Update backlog-refinement**

In `skills/backlog-refinement/SKILL.md`, find the **Code References** check section and add:

```markdown
#### RAG-Assisted Reference Check (if enabled)

If `llmOps.ragPolicy.enabled` and RAG server is reachable, for each function or class name extracted from ticket `affectedFiles` and `description`:

```python
rag = RagClient()
results = rag.search(function_name, n=3, filter={"type": "code"})
if not results.get("documents", [[]])[0]:
    flag_ticket(ticket_id, f"Code reference '{function_name}' not found in RAG index")
```

This is faster than grepping files manually and respects project isolation (only searches current project's index).
```

**Step 3: Verify**

```bash
grep -c "ragPolicy" skills/backlog-ticket/SKILL.md
grep -c "RAG-Assisted" skills/backlog-refinement/SKILL.md
# Expected: 1 each
```

**Step 4: Commit**

```bash
git add skills/backlog-ticket/SKILL.md skills/backlog-refinement/SKILL.md
git commit -m "feat(rag): integrate RAG context enrichment into ticket and refinement skills"
```

---

### Task 10: Enhance backlog-implementer — recurring patterns + post-file upsert

**Files:**
- Modify: `skills/backlog-implementer/SKILL.md`

**Step 1: Find Gate 1 PLAN RAG section**

In `SKILL.md`, find this block (around line 314):

```
**RAG**: if ragAvailable, query RAG with ticket description first; use returned snippets instead of full file reads.
```

**Step 2: Extend Gate 1 with recurring patterns query**

Replace that block with:

```markdown
**RAG**: if ragAvailable:
1. Query RAG with ticket description → use top-K snippets instead of full file reads:
   ```
   POST {ragPolicy.serverUrl}/search
   Body: {"project": project_name, "query": ticket.description, "n_results": ragPolicy.topK}
   ```
2. Query sentinel memory for recurring patterns in affected files:
   ```
   POST {ragPolicy.serverUrl}/search
   Body: {
     "project": project_name,
     "query": affected_files joined as string,
     "n_results": 3,
     "filter": {"found_by": "backlog-sentinel"}
   }
   ```
   If results found with similarity > 0.7, inject a **⚠️ Recurring Patterns** block at the TOP of the implementer prompt (before the ticket content):
   ```
   ⚠️ RECURRING PATTERNS — avoid these mistakes (from sentinel history):
   - {pattern.description} ({pattern.occurrences}× in {pattern.files})
   ```
   This costs $0 (RAG lookup) and prevents known failure modes before any code is written.

If RAG server is unreachable, fall back to direct file reads without error.
```

**Step 3: Add post-file upsert to Gate 2 IMPLEMENT**

Find the Gate 2 IMPLEMENT section and add after the subagent completes each file:

```markdown
**Post-file RAG sync**: After each file is written/modified by a subagent, if ragAvailable:
```bash
source scripts/rag/client.sh && rag_upsert_file "{modified_file_path}"
```
This keeps the index current during multi-file implementations so later tasks in the same wave can query the most recent code state.
```

**Step 4: Verify**

```bash
grep -c "Recurring Patterns" skills/backlog-implementer/SKILL.md
grep -c "Post-file RAG sync" skills/backlog-implementer/SKILL.md
# Expected: 1 each
```

**Step 5: Commit**

```bash
git add skills/backlog-implementer/SKILL.md
git commit -m "feat(rag): add recurring patterns injection and post-file upsert to implementer"
```

---

### Task 11: Write RAG server tests for /search with filter

**Files:**
- Modify: `tests/test_rag_server.py`

**Step 1: Add filter test**

```python
def test_search_filter_by_type(client):
    client.post("/index", json={
        "project": "filter-test",
        "documents": ["def login(): pass", "## BUG-001 Auth ticket"],
        "ids": ["filter-test::auth.py::0", "filter-test::BUG-001.md::0"],
        "metadatas": [{"type": "code"}, {"type": "ticket"}]
    })
    r = client.post("/search", json={
        "project": "filter-test",
        "query": "login",
        "n_results": 5,
        "filter": {"type": "code"}
    })
    docs = r.get_json()["results"]["documents"][0]
    assert all("def login" in d or "pass" in d for d in docs)
```

**Step 2: Implement filter support in /search**

In `server.py`, update the `/search` endpoint to pass `where` to ChromaDB:

```python
@app.route('/search', methods=['POST'])
def search():
    data = request.get_json()
    project = _get_project(data)
    col = _get_collection(project)
    query_embedding = embedder.encode(data["query"]).tolist()
    kwargs = {
        "query_embeddings": [query_embedding],
        "n_results": data.get("n_results", 5)
    }
    if data.get("filter"):
        kwargs["where"] = data["filter"]
    results = col.query(**kwargs)
    return jsonify({"query": data["query"], "results": results, "project": project})
```

**Step 3: Run all tests**

```bash
pytest tests/test_rag_server.py tests/test_rag_client.py tests/test_watcher.py -v
# Expected: all PASSED
```

**Step 4: Final commit**

```bash
git add scripts/rag/server.py tests/test_rag_server.py
git commit -m "feat(rag): add metadata filter support to /search endpoint"
```

---

## Verification Checklist

After all tasks complete, verify end-to-end:

```bash
# 1. Start services
./claude-with-services.sh &   # check /tmp/backlog-rag-watcher.pid exists

# 2. Open UI
open http://localhost:8001/ui  # should show projects table + search form

# 3. Index a project
cd /path/to/some-project
make rag-index

# 4. Search
make rag-search QUERY="authentication"

# 5. Verify isolation
cd /path/to/other-project
make rag-search QUERY="authentication"
# Should return different results from the other project

# 6. Run all tests
pytest tests/test_rag_server.py tests/test_rag_client.py tests/test_watcher.py -v
```
