---
id: worthiness
title: Memory worthiness decision
version: 1
stage: worthiness
role: system
note: Sequential pipeline only. Its criteria are materially MORE PERMISSIVE than the combined_eval prompt's: this one accepts anything whose loss would reduce future quality, while combined_eval requires an explicit user statement. Switching PIPELINE_MODE therefore changes what gets remembered, not just how many LLM calls are made. Preserved verbatim; converging them changes behaviour.
---
Decide whether the following event is worth storing as a permanent long-term memory.

An event IS memory-worthy if at least ONE holds:
- Forgetting it would reduce the quality of future interactions
- It encodes reusable knowledge (facts, preferences, procedures)
- It is user-specific or system-shaping (changes how the assistant should behave)

An event is NOT memory-worthy if:
- It is small talk, greetings, or filler
- It is only relevant to this one conversation and has no future value
- It is a transient clarification question with no lasting answer

Respond with JSON:
{"worthy": true, "reason": "brief explanation"}

Example (worthy):
{"worthy": true, "reason": "User stated a persistent preference for concise answers"}

Example (not worthy):
{"worthy": false, "reason": "Greeting with no informational content"}
