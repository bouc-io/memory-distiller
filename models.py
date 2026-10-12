from typing import Any, Literal

from pydantic import BaseModel, Field


class Source(BaseModel):
    type: Literal["chat", "agent"]
    id: str


class Context(BaseModel):
    text: str | None = None
    messages: list[Any] | None = None
    tool_calls: list[Any] | None = None


class Options(BaseModel):
    max_memories: int = 10


class DistillRequest(BaseModel):
    source: Source
    context: Context | None = None
    metadata: dict[str, Any] | None = {}
    options: Options | None = Field(default_factory=Options)


class MemoryObject(BaseModel):
    type: str  # semantic, episodic, procedural
    content: str
    confidence: float
    importance: float
    tags: list[str] = []
    justification: str | None = None


class Stats(BaseModel):
    events_analyzed: int
    memories_emitted: int
    memories_filtered_low_confidence: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0


class DistillResponse(BaseModel):
    source: Source
    memories: list[MemoryObject]
    stats: Stats
