import json
import os
import sys
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_get_project_from_config(tmp_path):
    cfg = tmp_path / "backlog.config.json"
    cfg.write_text(json.dumps({"project": {"name": "watch-test"}}))
    from scripts.rag.watcher import _get_project
    assert _get_project(str(tmp_path)) == "watch-test"


def test_get_project_fallback(tmp_path):
    from scripts.rag.watcher import _get_project
    result = _get_project(str(tmp_path))
    assert result == tmp_path.name


def test_should_ignore_git(tmp_path):
    from scripts.rag.watcher import _should_ignore
    assert _should_ignore(str(tmp_path / ".git" / "config"))
    assert _should_ignore(str(tmp_path / "node_modules" / "pkg" / "index.js"))
    assert not _should_ignore(str(tmp_path / "src" / "main.py"))


def test_watcher_indexes_new_file(tmp_path):
    """Watcher should call upsert_file when a new .py file is created."""
    cfg = tmp_path / "backlog.config.json"
    cfg.write_text(json.dumps({"project": {"name": "watch-test"}}))

    # Ensure module is already imported before patching so reload is not needed.
    from scripts.rag import watcher as w

    upserted = []

    with patch.object(w, "RagClient") as MockClient:
        instance = MockClient.return_value
        instance.upsert_file.side_effect = lambda p, **kw: upserted.append(p)

        obs = w.start_watcher(str(tmp_path), debounce_seconds=0.1)
        time.sleep(0.3)  # let observer start

        (tmp_path / "main.py").write_text("def hello(): pass")
        time.sleep(0.8)  # wait for debounce + flush

        obs.stop()
        obs.join()

    assert any("main.py" in str(p) for p in upserted), f"upserted={upserted}"


def test_watcher_indexes_ticket(tmp_path):
    """Files in backlog/data should be indexed as type=ticket."""
    cfg = tmp_path / "backlog.config.json"
    cfg.write_text(json.dumps({"project": {"name": "ticket-test"}}))
    (tmp_path / "backlog" / "data").mkdir(parents=True)

    from scripts.rag import watcher as w

    types_seen = []

    with patch.object(w, "RagClient") as MockClient:
        instance = MockClient.return_value
        instance.upsert_file.side_effect = lambda p, type="code", **kw: types_seen.append(type)

        obs = w.start_watcher(str(tmp_path), debounce_seconds=0.1)
        time.sleep(0.3)

        (tmp_path / "backlog" / "data" / "BUG-001.md").write_text("# BUG-001")
        time.sleep(0.8)

        obs.stop()
        obs.join()

    assert "ticket" in types_seen, f"types_seen={types_seen}"
