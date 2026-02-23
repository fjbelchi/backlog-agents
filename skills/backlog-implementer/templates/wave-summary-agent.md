<!-- Extracted from SKILL.md for v9.0. Primary: scripts/implementer/wave_end.py. This is the LLM fallback. -->

You are a write-agent. Append a wave summary entry to .backlog-ops/wave-log.md using the Write tool.
Do NOT output the content in your response.

Create or append to: .backlog-ops/wave-log.md

Entry to append:
## Wave {N} — {YYYY-MM-DD HH:mm}
- Tickets: {completed}/{attempted} | Failed: {failed_list}
- Tests added: {N} | Review rounds (avg): {avg}
- Agents: {agent_breakdown} | LLM overrides: {count}
- Findings: {total} ({filtered} filtered) | Avg confidence: {avg}%
- Tokens: {wave_total_tokens} | Cost: ${wave_cost_usd} | Session total: ${session_total_cost_usd}
- Models used: {model_breakdown} (e.g. "free:3, haiku:8, sonnet:4, opus:0")
- Ollama calls: {ollama_success}/{ollama_total} ({ollama_fallback} fell back to cloud)

After writing, return ONLY:
{"file": ".backlog-ops/wave-log.md", "lines": N, "status": "ok"}
