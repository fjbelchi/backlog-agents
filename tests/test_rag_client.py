import json
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Make the scripts/rag package importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_detect_project_from_config(tmp_path):
    config = tmp_path / "backlog.config.json"
    config.write_text(json.dumps({"project": {"name": "my-api"}}))
    with patch("os.getcwd", return_value=str(tmp_path)):
        # Re-import to pick up the patched getcwd
        if "scripts.rag.client" in sys.modules:
            del sys.modules["scripts.rag.client"]
        from scripts.rag.client import RagClient
        c = RagClient()
        assert c.project == "my-api"


def test_detect_project_fallback(tmp_path):
    with patch("os.getcwd", return_value=str(tmp_path)):
        if "scripts.rag.client" in sys.modules:
            del sys.modules["scripts.rag.client"]
        from scripts.rag.client import RagClient
        c = RagClient()
        assert c.project == tmp_path.name


def test_explicit_project_overrides_detection(tmp_path):
    config = tmp_path / "backlog.config.json"
    config.write_text(json.dumps({"project": {"name": "from-config"}}))
    with patch("os.getcwd", return_value=str(tmp_path)):
        from scripts.rag.client import RagClient
        c = RagClient(project="explicit-proj")
        assert c.project == "explicit-proj"


def test_search_sends_project():
    from scripts.rag.client import RagClient
    c = RagClient(project="test-proj", base_url="http://localhost:9999")
    mock_response = MagicMock()
    mock_response.json.return_value = {"results": {"documents": [[]]}}
    with patch("requests.post", return_value=mock_response) as mock_post:
        c.search("auth logic")
        call_kwargs = mock_post.call_args
        body = call_kwargs[1]["json"] if call_kwargs[1] else call_kwargs[0][1]
        assert body["project"] == "test-proj"
        assert body["query"] == "auth logic"


def test_search_with_filter():
    from scripts.rag.client import RagClient
    c = RagClient(project="proj", base_url="http://localhost:9999")
    mock_response = MagicMock()
    mock_response.json.return_value = {"results": {}}
    with patch("requests.post", return_value=mock_response) as mock_post:
        c.search("tickets", filter={"type": "ticket"})
        body = mock_post.call_args[1]["json"]
        assert body["filter"] == {"type": "ticket"}


def test_upsert_file_reads_and_posts(tmp_path):
    src = tmp_path / "auth.py"
    src.write_text("def login(): pass")
    from scripts.rag.client import RagClient
    c = RagClient(project="proj", base_url="http://localhost:9999")
    mock_response = MagicMock()
    mock_response.json.return_value = {"indexed": 1}
    with patch("requests.post", return_value=mock_response) as mock_post:
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = c.upsert_file(str(src))
        body = mock_post.call_args[1]["json"]
        assert body["project"] == "proj"
        assert len(body["documents"]) == 1
        assert "login" in body["documents"][0]
        assert body["ids"][0].startswith("proj::")
