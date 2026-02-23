<!-- Extracted from SKILL.md for v9.0. Primary: scripts/implementer/micro_reflect.py. This is the LLM fallback. -->

Analyze this wave's outcomes and tag playbook bullets.

## Wave Results
- Tickets: {completed}/{attempted}
- Gates failed: {gate_failures_with_reasons}
- Escalations: {fast_path_escalations}
- Models used: {model_breakdown}
- Cost: ${wave_cost}

## Current Playbook Bullets Used This Wave
{bullets_referenced_with_ids}

## Instructions
1. Tag each referenced bullet: helpful, harmful, or neutral
2. If a gate failed, identify root cause and propose 1 new bullet (ADD)
3. If fast-path escalated, explain why classifier was wrong
4. Max 3 tags + 1 new bullet per wave

Return JSON:
{"bullet_tags": [{"id": "strat-00001", "tag": "helpful"}],
 "new_bullets": [{"section": "Common Mistakes", "content": "..."}],
 "reasoning": "..."}
