from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal

class Source(BaseModel):
    type: Literal["chat", "agent"]
    id: str

class Context(BaseModel):
    text: Optional[str] = None
    messages: Optional[List[Any]] = None
    tool_calls: Optional[List[Any]] = None

class Options(BaseModel):
    max_memories: int = 10

class DistillRequest(BaseModel):
    source: Source
    context: Optional[Context] = None
    metadata: Optional[Dict[str, Any]] = {}
    options: Optional[Options] = Field(default_factory=Options)

class MemoryObject(BaseModel):
    type: str # semantic, episodic, procedural
    content: str
    confidence: float
    importance: float
    tags: List[str] = []
    justification: Optional[str] = None

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
    memories: List[MemoryObject]
    stats: Stats
