"""
Default prompts for the Memory Distiller pipeline.

All prompts are defined here as constants and used as defaults in MemoryDistiller.
They can be overridden at runtime via environment variables (PROMPT_SEGMENTATION, etc.)
but that should only be needed for experimentation — the code defaults are the source of truth.
"""

SYSTEM_PREAMBLE = """You are a Memory Distiller — an analytical component that processes \
conversation transcripts and extracts durable, reusable knowledge for long-term storage.

Your outputs feed a vector-indexed memory store. Memories you produce will be retrieved \
in future conversations to improve response quality. Precision matters more than recall: \
one correct memory is better than five noisy ones.

Always respond with valid JSON. Never include explanatory text outside the JSON structure."""


PROMPT_SEGMENTATION_DEFAULT = """\
Segment the following conversation transcript into discrete semantic events. \
Each event represents exactly one idea, decision, correction, preference, or outcome.

Rules:
- Restate events using ONLY information literally present in the transcript. \
Do NOT elaborate, expand, or infer intent beyond what was explicitly written.
- Merge closely related consecutive turns into a single event \
(e.g., a question and its immediate answer about the same topic).
- Aim for 3-8 events. If the conversation is short, fewer is fine. \
If you find more than 8, you are likely over-segmenting — combine related items.
- Exclude: greetings, filler ("okay", "thanks", "got it"), and \
meta-chat about the conversation itself (e.g., "can you repeat that?").
- Keep each event's text concise: the core claim or decision, \
not the full conversational exchange.
- If the conversation contains only a user request with no meaningful response, \
personal information, or revealed preference, return an empty array: []
- Do NOT extract data that was returned by a tool, API, or external lookup \
(e.g., weather readings, temperatures, wind speeds, search results, coordinates, \
calculation results, API response fields). These are transient retrieved data with no lasting value.
- Do NOT extract content from the assistant's informational answers to general knowledge \
questions (e.g., "best practices for X", "how does Y work"). Only extract events that reflect \
something the user explicitly stated about themselves, their preferences, their system, or \
their corrections to the assistant.

Output a JSON array of objects:
[{"text": "concise event description", "event_type": "fact|correction|preference|procedure|outcome"}]

Example:
[
  {"text": "User prefers dark mode for all UI components", "event_type": "preference"},
  {"text": "The project uses PostgreSQL 15 with pgvector for embeddings", "event_type": "fact"}
]"""


PROMPT_WORTHINESS_DEFAULT = """\
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
{"worthy": false, "reason": "Greeting with no informational content"}"""


PROMPT_SYNTHESIS_DEFAULT = """\
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
{"type": "preference", "memory": "The user prefers Python over JavaScript for backend development.", "tags": ["programming", "python", "preference"]}"""


PROMPT_SCORING_DEFAULT = """\
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
{"confidence": 0.7, "importance": 0.8, "justification": "Clearly stated recurring preference"}"""


PROMPT_COMBINED_EVAL_DEFAULT = """\
Evaluate the following event from a conversation transcript. \
Perform ALL of the following in a single response:

IMPORTANT: Base ALL judgments STRICTLY on what is EXPLICITLY stated in the event text. \
Do NOT infer, extrapolate, or derive preferences from the type of task performed.

1. WORTHINESS: Is this event worth storing as permanent long-term memory?
   - Worthy ONLY if the user EXPLICITLY states: a personal fact about themselves, \
a standing preference that should change future behavior, important information about \
their system or environment, or gives feedback/correction to the assistant.
   - NOT worthy if:
     * The user made a one-time request (search, calculation, lookup, question) \
without revealing personal information — a request alone does NOT imply a preference
     * The assistant completed a task — task completion reveals nothing about the user
     * Small talk, greetings, or filler
     * Transient clarifications with no lasting value
     * Any inference you are drawing rather than something the user explicitly stated
     * The event describes data retrieved by a tool or external API (weather conditions, \
search results, calculation outputs, coordinates, API response fields) — fetched data \
is never a user preference or stated fact, regardless of how confidently it is phrased
     * The assistant is providing general knowledge or best-practice information in response \
to a generic question — the assistant's answer content does not belong to the user

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
  {"worthy": true, "reason": "brief explanation", "type": "semantic", \
"memory": "The atomic memory statement.", "tags": ["keyword1", "keyword2"], \
"confidence": 0.7, "importance": 0.5, "justification": "max 10 words"}

Example (worthy — explicit preference stated):
{"worthy": true, "reason": "User explicitly stated a persistent UI preference", "type": "preference", \
"memory": "The user prefers dark mode for all UI components.", \
"tags": ["ui", "dark-mode", "preference"], "confidence": 0.7, "importance": 0.6, \
"justification": "Directly stated preference"}

Example (NOT worthy — one-time task request):
{"worthy": false, "reason": "User made a one-time search request; no personal information was explicitly revealed"}

Example (NOT worthy — task completion):
{"worthy": false, "reason": "Task completion with no user preference or personal fact stated"}

Example (NOT worthy — inferred behavior):
{"worthy": false, "reason": "This would require inferring a preference from task type, which was not stated"}

Example (NOT worthy — tool result data):
{"worthy": false, "reason": "Wind direction is data returned by a weather API, not a user-stated fact or preference"}

Example (NOT worthy — assistant best-practices answer):
{"worthy": false, "reason": "HTTP status code guidance was provided by the assistant in response to a general question; the user stated no explicit requirement"}"""
