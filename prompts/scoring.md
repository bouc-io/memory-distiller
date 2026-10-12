---
id: scoring
title: Confidence and importance scoring
version: 1
stage: scoring
role: system
note: Sequential pipeline only. The rubric reserves 0.9 importance for core/critical items and its worked example scores 0.8, so map_importance's >=0.9 'critical' tier is rarely populated in practice.
---
Assign a confidence score and an importance score to the memory below.

Confidence (0.0-1.0) — How likely is this memory to be correct and stable?
  0.3 = inferred from indirect evidence or vague phrasing
  0.5 = mentioned once without explicit confirmation
  0.7 = clearly and directly stated by the user
  0.9 = confirmed, repeated, or reinforced across multiple turns

Importance (0.0-1.0) — How much should this memory influence future behavior?
  0.3 = incidental detail, rarely relevant
  0.5 = useful context for specific topics
  0.7 = broadly applicable preference or fact
  0.9 = core identity, critical instruction, or safety-relevant

Respond with JSON:
{"confidence": 0.0, "importance": 0.0, "justification": "max 10 words"}

Example:
{"confidence": 0.7, "importance": 0.8, "justification": "Clearly stated recurring preference"}
