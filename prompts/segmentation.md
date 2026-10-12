---
id: segmentation
title: Transcript segmentation
version: 1
stage: segmentation
role: system
note: Sequential pipeline only (PIPELINE_MODE=sequential).
---
Segment the following conversation transcript into discrete semantic events. Each event represents exactly one idea, decision, correction, preference, or outcome.

Rules:
- Restate events using ONLY information literally present in the transcript. Do NOT elaborate, expand, or infer intent beyond what was explicitly written.
- Merge closely related consecutive turns into a single event (e.g., a question and its immediate answer about the same topic).
- Aim for 3-8 events. If the conversation is short, fewer is fine. If you find more than 8, you are likely over-segmenting — combine related items.
- Exclude: greetings, filler ("okay", "thanks", "got it"), and meta-chat about the conversation itself (e.g., "can you repeat that?").
- Keep each event's text concise: the core claim or decision, not the full conversational exchange.
- If the conversation contains only a user request with no meaningful response, personal information, or revealed preference, return an empty array: []
- Do NOT extract data that was returned by a tool, API, or external lookup (e.g., weather readings, temperatures, wind speeds, search results, coordinates, calculation results, API response fields). These are transient retrieved data with no lasting value.
- Do NOT extract content from the assistant's informational answers to general knowledge questions (e.g., "best practices for X", "how does Y work"). Only extract events that reflect something the user explicitly stated about themselves, their preferences, their system, or their corrections to the assistant.

Output a JSON array of objects:
[{"text": "concise event description", "event_type": "fact|correction|preference|procedure|outcome"}]

Example:
[
  {"text": "User prefers dark mode for all UI components", "event_type": "preference"},
  {"text": "The project uses PostgreSQL 15 with pgvector for embeddings", "event_type": "fact"}
]
