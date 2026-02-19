# scripts/rag/client.py
import json
import os
import requests
from pathlib import Path


class RagClient:
    def __init__(self, project: str = None, base_url: str = None):
        self.base_url = base_url or os.environ.get("RAG_BASE_URL", "http://localhost:8001")
        self.project = project or self._detect_project()

    def _detect_project(self) -> str:
        """Walk up from CWD looking for backlog.config.json. Returns project.name or CWD basename."""
        path = Path(os.getcwd())
        for p in [path] + list(path.parents):
            cfg = p / "backlog.config.json"
            if cfg.exists():
                try:
                    data = json.loads(cfg.read_text())
                    return data["project"]["name"]
                except (KeyError, json.JSONDecodeError, OSError):
                    pass
        return path.name

    def search(self, query: str, n: int = 5, filter: dict = None) -> dict:
        payload = {"project": self.project, "query": query, "n_results": n}
        if filter:
            payload["filter"] = filter
        r = requests.post(f"{self.base_url}/search", json=payload)
        return r.json().get("results", {})

    def index_files(self, paths: list, type: str = "code") -> dict:
        docs, ids, metas = [], [], []
        cwd = Path(os.getcwd())
        for path in paths:
            p = Path(path)
            if not p.exists():
                continue
            try:
                rel = str(p.relative_to(cwd)) if p.is_absolute() else str(p)
            except ValueError:
                rel = str(p)
            content = p.read_text(errors="ignore")[:2000]
            docs.append(content)
            ids.append(f"{self.project}::{rel}::0")
            metas.append({"type": type, "file": rel, "project": self.project})
        if not docs:
            return {"indexed": 0}
        r = requests.post(f"{self.base_url}/index", json={
            "project": self.project,
            "documents": docs,
            "ids": ids,
            "metadatas": metas,
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


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    proj = None
    for i, a in enumerate(sys.argv):
        if a == "--project" and i + 1 < len(sys.argv):
            proj = sys.argv[i + 1]
            break
    c = RagClient(project=proj)
    if cmd == "upsert" and len(sys.argv) > 2:
        target = sys.argv[2]
        doc_type = "ticket" if "backlog/data" in target else "code"
        print(c.upsert_file(target, type=doc_type))
    elif cmd == "stats":
        print(c.stats())
    elif cmd == "clear":
        print(c.clear())
    else:
        print(f"Unknown command: {cmd}. Use: upsert <file>, stats, clear")
