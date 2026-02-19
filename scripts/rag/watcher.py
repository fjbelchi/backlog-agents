#!/usr/bin/env python3
"""
RAG File Watcher — always-on host-side watcher that indexes file changes
into the project-aware RAG server.

Usage:
    python3 scripts/rag/watcher.py --watch /path/to/project
    python3 scripts/rag/watcher.py  # defaults to CWD
"""

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

# Make scripts.rag importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("Error: watchdog not installed. Run: pip install watchdog")
    sys.exit(1)

from rag.client import RagClient

CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".md"}
IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache", "dist", "build"}


def _get_project(watch_dir: str) -> str:
    """Walk up from watch_dir to find backlog.config.json and return project.name."""
    path = Path(watch_dir).resolve()
    for p in [path] + list(path.parents):
        cfg = p / "backlog.config.json"
        if cfg.exists():
            try:
                return json.loads(cfg.read_text())["project"]["name"]
            except (KeyError, json.JSONDecodeError, OSError):
                pass
    return path.name


def _should_ignore(path: str) -> bool:
    parts = Path(path).parts
    return any(part in IGNORE_DIRS for part in parts)


class _ChangeHandler(FileSystemEventHandler):
    def __init__(self, client: RagClient, debounce: float = 2.0):
        self.client = client
        self.debounce = debounce
        self._pending: dict = {}  # path -> action
        self._lock = threading.Lock()

    def _schedule(self, path: str, action: str = "upsert") -> None:
        with self._lock:
            self._pending[path] = action
        t = threading.Timer(self.debounce, self._flush, args=[path])
        t.daemon = True
        t.start()

    def _flush(self, path: str) -> None:
        with self._lock:
            action = self._pending.pop(path, None)
        if not action:
            return
        try:
            if action == "upsert":
                doc_type = "ticket" if "backlog/data" in path.replace(os.sep, "/") else "code"
                self.client.upsert_file(path, type=doc_type)
                print(f"[watcher] indexed: {path}")
        except Exception as e:
            print(f"[watcher] error indexing {path}: {e}")

    def on_created(self, event) -> None:
        if not event.is_directory and Path(event.src_path).suffix in CODE_EXTS:
            if not _should_ignore(event.src_path):
                self._schedule(event.src_path)

    def on_modified(self, event) -> None:
        if not event.is_directory and Path(event.src_path).suffix in CODE_EXTS:
            if not _should_ignore(event.src_path):
                self._schedule(event.src_path)


def start_watcher(watch_dir: str, debounce_seconds: float = 2.0) -> Observer:
    """Start watching watch_dir. Returns the Observer (already started)."""
    project = _get_project(watch_dir)
    client = RagClient(project=project)
    handler = _ChangeHandler(client, debounce=debounce_seconds)
    observer = Observer()
    observer.schedule(handler, watch_dir, recursive=True)
    observer.start()
    print(f"[watcher] watching {watch_dir} -> project: {project}")
    return observer


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG file watcher for backlog toolkit")
    parser.add_argument("--watch", default=os.getcwd(), help="Directory to watch (default: CWD)")
    args = parser.parse_args()

    obs = start_watcher(args.watch)
    try:
        while obs.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        obs.stop()
    obs.join()
    print("[watcher] stopped")


if __name__ == "__main__":
    main()
