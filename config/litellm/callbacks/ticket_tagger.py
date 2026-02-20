# config/litellm/callbacks/ticket_tagger.py
import json
import os
from pathlib import Path

try:
    from litellm.integrations.custom_logger import CustomLogger
except ImportError:
    # Fallback for testing without LiteLLM installed
    class CustomLogger:
        pass

CONTEXT_FILE = Path(
    os.environ.get(
        "BACKLOG_CONTEXT_FILE",
        str(Path.home() / ".backlog-toolkit" / "current-context.json")
    )
)

class TicketTagger(CustomLogger):
    def _read_context(self) -> dict:
        try:
            path = Path(os.environ.get("BACKLOG_CONTEXT_FILE", str(CONTEXT_FILE)))
            if path.exists():
                return json.loads(path.read_text())
        except Exception:
            pass
        return {}

    def log_pre_api_call(self, model, messages, kwargs):
        ctx = self._read_context()
        if not ctx:
            return
        tags = []
        for key, prefix in [
            ("ticket_id", "ticket"),
            ("gate",      "gate"),
            ("project",   "project"),
            ("agent_type","agent"),
            ("skill",     "skill"),
        ]:
            val = ctx.get(key)
            if val:
                tags.append(f"{prefix}:{val}")
        if tags:
            kwargs.setdefault("metadata", {})
            kwargs["metadata"]["tags"] = tags
