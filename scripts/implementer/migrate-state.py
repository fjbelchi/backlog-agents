#!/usr/bin/env python3
"""Migrate or initialize implementer state to v6.1 schema.

Usage: python3 migrate-state.py
Reads/creates .claude/implementer-state.json with all required fields.
Do NOT use `cat file | python3 > file` — that truncates before reading.
"""

import json
import os

STATE_FILE = ".claude/implementer-state.json"
os.makedirs(".claude", exist_ok=True)

state = {}
try:
    with open(STATE_FILE) as f:
        content = f.read().strip()
        if content:
            state = json.loads(content)
except (FileNotFoundError, json.JSONDecodeError):
    pass  # start fresh

state.setdefault("version", "6.0")
state.setdefault("lastRunTimestamp", None)
state.setdefault("lastCycle", 0)
state.setdefault("currentWave", None)
stats = state.setdefault("stats", {})
stats.setdefault("totalTicketsCompleted", 0)
stats.setdefault("totalTicketsFailed", 0)
stats.setdefault("totalTicketsInvestigated", 0)
stats.setdefault("totalReviewRounds", 0)
stats.setdefault("totalTestsAdded", 0)
stats.setdefault("totalCommits", 0)
stats.setdefault("totalWavesCompleted", 0)
stats.setdefault("avgReviewRoundsPerTicket", 0)
stats.setdefault("ticketsByType", {})
stats.setdefault("totalTokensUsed", 0)
stats.setdefault("totalCostUsd", 0)
stats.setdefault("agentRoutingStats", {
    "frontend": 0, "backend": 0, "devops": 0,
    "ml-engineer": 0, "test-engineer": 0,
    "general-purpose": 0, "llmOverrides": 0
})
stats.setdefault("reviewStats", {
    "totalFindings": 0, "filteredByConfidence": 0, "avgConfidence": 0
})
local = stats.setdefault("localModelStats", {})
local.setdefault("totalAttempts", 0)
local.setdefault("successCount", 0)
local.setdefault("escalatedToCloud", 0)
local.setdefault("failuresByType", {})
local.setdefault("avgQualityScore", 0)
state["version"] = "6.1"

with open(STATE_FILE, "w") as f:
    json.dump(state, f, indent=2)
print("State ready:", STATE_FILE)
