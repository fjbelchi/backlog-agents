import json, os, sys, pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "config", "litellm", "callbacks"))


def _reload_tagger():
    import importlib
    if "ticket_tagger" in sys.modules:
        del sys.modules["ticket_tagger"]
    import ticket_tagger
    return ticket_tagger


def test_tags_injected_when_context_file_exists(tmp_path):
    ctx = {
        "ticket_id": "FEAT-001", "gate": "implement",
        "project": "my-api", "agent_type": "backend",
        "skill": "backlog-implementer"
    }
    ctx_file = tmp_path / "current-context.json"
    ctx_file.write_text(json.dumps(ctx))
    with patch.dict(os.environ, {"BACKLOG_CONTEXT_FILE": str(ctx_file)}):
        mod = _reload_tagger()
        tagger = mod.TicketTagger()
        kwargs = {}
        tagger.log_pre_api_call("claude", [], kwargs)
    assert "metadata" in kwargs
    tags = kwargs["metadata"]["tags"]
    assert "ticket:FEAT-001" in tags
    assert "gate:implement" in tags
    assert "project:my-api" in tags
    assert "agent:backend" in tags
    assert "skill:backlog-implementer" in tags


def test_no_tags_when_file_missing(tmp_path):
    with patch.dict(os.environ, {"BACKLOG_CONTEXT_FILE": str(tmp_path / "missing.json")}):
        mod = _reload_tagger()
        tagger = mod.TicketTagger()
        kwargs = {}
        tagger.log_pre_api_call("claude", [], kwargs)
    assert "metadata" not in kwargs


def test_no_tags_when_empty_context(tmp_path):
    ctx_file = tmp_path / "current-context.json"
    ctx_file.write_text("{}")
    with patch.dict(os.environ, {"BACKLOG_CONTEXT_FILE": str(ctx_file)}):
        mod = _reload_tagger()
        tagger = mod.TicketTagger()
        kwargs = {}
        tagger.log_pre_api_call("claude", [], kwargs)
    assert kwargs.get("metadata", {}).get("tags", []) == []


def test_partial_context_only_present_tags(tmp_path):
    ctx = {"ticket_id": "BUG-007"}  # only ticket_id set
    ctx_file = tmp_path / "current-context.json"
    ctx_file.write_text(json.dumps(ctx))
    with patch.dict(os.environ, {"BACKLOG_CONTEXT_FILE": str(ctx_file)}):
        mod = _reload_tagger()
        tagger = mod.TicketTagger()
        kwargs = {}
        tagger.log_pre_api_call("claude", [], kwargs)
    tags = kwargs["metadata"]["tags"]
    assert tags == ["ticket:BUG-007"]


def test_existing_metadata_preserved(tmp_path):
    ctx = {"ticket_id": "TASK-003", "gate": "lint"}
    ctx_file = tmp_path / "current-context.json"
    ctx_file.write_text(json.dumps(ctx))
    with patch.dict(os.environ, {"BACKLOG_CONTEXT_FILE": str(ctx_file)}):
        mod = _reload_tagger()
        tagger = mod.TicketTagger()
        kwargs = {"metadata": {"user": "test-user"}}
        tagger.log_pre_api_call("claude", [], kwargs)
    assert kwargs["metadata"]["user"] == "test-user"
    assert "ticket:TASK-003" in kwargs["metadata"]["tags"]


def test_malformed_json_handled_gracefully(tmp_path):
    ctx_file = tmp_path / "current-context.json"
    ctx_file.write_text("not valid json {{{")
    with patch.dict(os.environ, {"BACKLOG_CONTEXT_FILE": str(ctx_file)}):
        mod = _reload_tagger()
        tagger = mod.TicketTagger()
        kwargs = {}
        tagger.log_pre_api_call("claude", [], kwargs)
    assert "metadata" not in kwargs
