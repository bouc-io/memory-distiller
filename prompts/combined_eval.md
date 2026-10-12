---
id: combined_eval
title: Combined worthiness, synthesis and scoring
version: 1
stage: combined
role: system
note: Default pipeline (PIPELINE_MODE=combined). Does worthiness, synthesis and scoring in one call. Stricter than the standalone worthiness prompt: worthy only on an explicit user statement.
---
Evaluate the following event from a conversation transcript. Perform ALL of the following in a single response:

IMPORTANT: Base ALL judgments STRICTLY on what is EXPLICITLY stated in the event text. Do NOT infer, extrapolate, or derive preferences from the type of task performed.

1. WORTHINESS: Is this event worth storing as permanent long-term memory?
   - Worthy ONLY if the user EXPLICITLY states: a personal fact about themselves, a standing preference that should change future behavior, important information about their system or environment, or gives feedback/correction to the assistant.
   - NOT worthy if:
     * The user made a one-time request (search, calculation, lookup, question) without revealing personal information — a request alone does NOT imply a preference
     * The assistant completed a task — task completion reveals nothing about the user
     * Small talk, greetings, or filler
     * Transient clarifications with no lasting value
     * Any inference you are drawing rather than something the user explicitly stated
     * The event describes data retrieved by a tool or external API (weather conditions, search results, calculation outputs, coordinates, API response fields) — fetched data is never a user preference or stated fact, regardless of how confidently it is phrased
     * The assistant is providing general knowledge or best-practice information in response to a generic question — the assistant's answer content does not belong to the user

2. If worthy, SYNTHESIZE an atomic memory:
   - Self-contained, declarative, no conversational references, max 2 sentences
   - Classify as: episodic, semantic, personal, preference, or procedural
   - Extract relevant keyword tags

3. If worthy, SCORE the memory:
   Confidence (0.0-1.0):
     0.3=inferred, 0.5=mentioned once, 0.7=clearly stated, 0.9=confirmed/repeated
   Importance (0.0-1.0):
     0.3=incidental, 0.5=topic-specific, 0.7=broadly applicable, 0.9=core/critical

Respond with JSON.
If NOT worthy:
  {"worthy": false, "reason": "brief explanation"}

If worthy:
  {"worthy": true, "reason": "brief explanation", "type": "semantic", "memory": "The atomic memory statement.", "tags": ["keyword1", "keyword2"], "confidence": 0.7, "importance": 0.5, "justification": "max 10 words"}

Example (worthy — explicit preference stated):
{"worthy": true, "reason": "User explicitly stated a persistent UI preference", "type": "preference", "memory": "The user prefers dark mode for all UI components.", "tags": ["ui", "dark-mode", "preference"], "confidence": 0.7, "importance": 0.6, "justification": "Directly stated preference"}

Example (NOT worthy — one-time task request):
{"worthy": false, "reason": "User made a one-time search request; no personal information was explicitly revealed"}

Example (NOT worthy — task completion):
{"worthy": false, "reason": "Task completion with no user preference or personal fact stated"}

Example (NOT worthy — inferred behavior):
{"worthy": false, "reason": "This would require inferring a preference from task type, which was not stated"}

Example (NOT worthy — tool result data):
{"worthy": false, "reason": "Wind direction is data returned by a weather API, not a user-stated fact or preference"}

Example (NOT worthy — assistant best-practices answer):
{"worthy": false, "reason": "HTTP status code guidance was provided by the assistant in response to a general question; the user stated no explicit requirement"}
