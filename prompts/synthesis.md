---
id: synthesis
title: Atomic memory synthesis
version: 1
stage: synthesis
role: system
note: Sequential pipeline only. Classifies into episodic|semantic|personal|preference|procedural, which main.py:map_category maps onto the Memory API's persona|preference|fact|context|instruction.
---
Rewrite the following event as a single, atomic, self-contained memory statement.

Requirements:
- Self-contained: understandable without the original conversation
- Declarative tone: state the fact, preference, or procedure directly
- No conversational references: never use "the user said" or "in this chat"
- Maximum 2 sentences
- Classify as one of: episodic, semantic, personal, preference, procedural

Respond with JSON:
{"type": "semantic", "memory": "The standalone memory statement.", "tags": ["relevant", "keywords"]}

Example:
{"type": "preference", "memory": "The user prefers Python over JavaScript for backend development.", "tags": ["programming", "python", "preference"]}
