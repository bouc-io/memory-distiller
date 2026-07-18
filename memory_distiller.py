import os
import json
import logging
from typing import List, Dict, Any, Optional, Tuple

from prompts import (
    SYSTEM_PREAMBLE,
    PROMPT_SEGMENTATION_DEFAULT,
    PROMPT_WORTHINESS_DEFAULT,
    PROMPT_SYNTHESIS_DEFAULT,
    PROMPT_SCORING_DEFAULT,
    PROMPT_COMBINED_EVAL_DEFAULT,
)
from llm_client import LLMClient

logger = logging.getLogger(__name__)

class MemoryDistiller:
    def __init__(self, llm_client: LLMClient, config: Dict[str, Any]):
        """
        llm_client: injected provider client (resolved from assignment config at request time).
        config: non-LLM runtime configuration (pipeline_mode, prompts, thresholds, etc.).
        """
        self.llm_client = llm_client
        self.confidence_threshold = float(config.get("CONFIDENCE_THRESHOLD", 0.5))
        self.pipeline_mode = config.get("PIPELINE_MODE", "combined")
        self.system_preamble = config.get("SYSTEM_PREAMBLE") or SYSTEM_PREAMBLE
        self.prompts = {
            "segmentation": config.get("PROMPT_SEGMENTATION") or PROMPT_SEGMENTATION_DEFAULT,
            "worthiness": config.get("PROMPT_WORTHINESS") or PROMPT_WORTHINESS_DEFAULT,
            "synthesis": config.get("PROMPT_SYNTHESIS") or PROMPT_SYNTHESIS_DEFAULT,
            "scoring": config.get("PROMPT_SCORING") or PROMPT_SCORING_DEFAULT,
            "combined_eval": config.get("PROMPT_COMBINED_EVAL") or PROMPT_COMBINED_EVAL_DEFAULT,
        }

    def _call_llm(self, prompt: str, context: str, json_mode: bool = True) -> Tuple[Any, Dict[str, int]]:
        """Internal LLM call: constructs messages and delegates to the injected llm_client."""
        messages = [
            {"role": "system", "content": f"{self.system_preamble}\n\n{prompt}"},
            {"role": "user", "content": f"Context:\n{context}"},
        ]
        logger.debug(f"Calling LLM with prompt preview: {prompt[:50]}...")
        try:
            result, usage = self.llm_client.chat(messages, json_mode=json_mode, think=False)
            return result, usage
        except Exception as e:
            logger.error(f"LLM Call failed: {e}")
            raise

    def distill(self, full_context: str, metadata: Dict[str, Any] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        logger.info("Starting distillation process.")

        # Minimum context guard — skip distillation on trivially short input
        MIN_CONTEXT_CHARS = 150
        if len(full_context.strip()) < MIN_CONTEXT_CHARS:
            logger.warning(f"Context too short ({len(full_context)} chars) — skipping distillation.")
            return [], {
                "events_analyzed": 0, "memories_emitted": 0, "memories_filtered_low_confidence": 0,
                "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "llm_calls": 0,
            }

        # Local token accumulator (thread-safe: one per call, not on self)
        prompt_tokens = 0
        completion_tokens = 0
        llm_calls = 0

        def _add_usage(usage: Dict[str, int]) -> None:
            nonlocal prompt_tokens, completion_tokens, llm_calls
            prompt_tokens     += usage.get("prompt_tokens", 0)
            completion_tokens += usage.get("completion_tokens", 0)
            llm_calls         += 1

        # Step 1: Segmentation
        logger.debug(f"Input context preview: {full_context[:100]}...")
        logger.debug(f"Full context ({len(full_context)} chars):\n{full_context}")
        events, seg_usage = self.segment_events(full_context)
        _add_usage(seg_usage)
        logger.info(f"Segmented into {len(events)} events.")
        if logger.isEnabledFor(logging.DEBUG):
            for i, ev in enumerate(events):
                logger.debug(f"Event {i+1}: {ev.get('text', '')[:50]}...")

        stats = {
            "events_analyzed": len(events),
            "memories_emitted": 0
        }

        candidate_memories = []

        if self.pipeline_mode == "combined":
            logger.info("Using combined pipeline mode (single-call evaluation)")
            for event in events:
                memory, ev_usage = self.evaluate_event(event, metadata)
                _add_usage(ev_usage)
                if memory is not None:
                    logger.debug(f"Combined eval produced memory: {memory.get('content', '')[:50]}...")
                    candidate_memories.append(memory)
                else:
                    logger.debug(f"Event filtered by combined eval: {event.get('text', '')[:50]}...")
        else:
            logger.info("Using sequential pipeline mode (multi-call evaluation)")
            for event in events:
                # Step 2: Worthiness
                worthy, worth_usage = self.is_memory_worthy(event)
                _add_usage(worth_usage)
                if worthy:
                    logger.debug(f"Event deemed worthy: {event.get('text', '')[:50]}...")
                    # Step 3: Synthesis
                    memory, syn_usage = self.synthesize_memory(event, metadata)
                    _add_usage(syn_usage)
                    logger.debug(f"Synthesized memory: {memory}")

                    # Step 4: Scoring
                    scored_memory, score_usage = self.score_memory(memory, event)
                    _add_usage(score_usage)
                    logger.debug(f"Scored memory: {scored_memory}")

                    candidate_memories.append(scored_memory)
                else:
                    logger.debug(f"Event deemed NOT worthy: {event.get('text', '')[:50]}...")

        # Step 5: Deduplication
        deduped_memories = self.deduplicate(candidate_memories)

        # Step 6: Confidence threshold filtering
        final_memories = [
            m for m in deduped_memories
            if m.get("confidence", 0) >= self.confidence_threshold
        ]
        filtered_count = len(deduped_memories) - len(final_memories)
        if filtered_count > 0:
            logger.info(f"Filtered {filtered_count} low-confidence memories (threshold: {self.confidence_threshold})")

        stats["memories_emitted"] = len(final_memories)
        stats["memories_filtered_low_confidence"] = filtered_count
        stats["prompt_tokens"]     = prompt_tokens
        stats["completion_tokens"] = completion_tokens
        stats["total_tokens"]      = prompt_tokens + completion_tokens
        stats["llm_calls"]         = llm_calls
        logger.info(
            f"Distillation complete. {len(final_memories)} memories produced. "
            f"Tokens: {prompt_tokens} prompt + {completion_tokens} completion = {prompt_tokens + completion_tokens} total ({llm_calls} LLM calls)."
        )

        return final_memories, stats

    def segment_events(self, full_context: str) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        result, usage = self._call_llm(self.prompts["segmentation"], full_context)
        logger.debug(f"LLM Segmentation Result: {result}")
        if isinstance(result, list):
            return result, usage
        if isinstance(result, dict):
            if "text" in result or "event_type" in result:
                return [result], usage
            for key in result:
                if isinstance(result[key], list):
                    return result[key], usage
        logger.warning("Could not parse events list from LLM response.")
        return [], usage

    def is_memory_worthy(self, event: Dict[str, Any]) -> Tuple[bool, Dict[str, int]]:
        text = event.get("text", "")
        if not text:
            return False, {"prompt_tokens": 0, "completion_tokens": 0}
        if not isinstance(text, str):
            text = str(text)

        result, usage = self._call_llm(self.prompts["worthiness"], text)
        if not isinstance(result, dict):
            logger.warning(f"LLM Worthiness returned non-dict: {result}")
            return False, usage

        logger.debug(f"LLM Worthiness Result for '{text[:20]}...': {result}")
        return bool(result.get("worthy", False)), usage

    def synthesize_memory(self, event: Dict[str, Any], metadata: Dict[str, Any] = None) -> Tuple[Dict[str, Any], Dict[str, int]]:
        text = event.get("text", "")
        if not isinstance(text, str):
            text = str(text)

        result, usage = self._call_llm(self.prompts["synthesis"], text)
        if not isinstance(result, dict):
            logger.warning(f"LLM Synthesis returned non-dict: {result}")
            result = {}

        logger.debug(f"LLM Synthesis Result for '{text[:20]}...': {result}")

        mem_content = result.get("memory", text)
        if not isinstance(mem_content, str):
            mem_content = str(mem_content)

        tags = result.get("tags", [])
        if not isinstance(tags, list):
            tags = []

        return {
            "type": str(result.get("type", "semantic")),
            "content": mem_content,
            "tags": tags,
            "metadata": metadata or {}
        }, usage

    def score_memory(self, memory: Dict[str, Any], event: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, int]]:
        content = memory.get("content", "")
        if not isinstance(content, str):
            content = str(content)

        result, usage = self._call_llm(self.prompts["scoring"], content)
        if not isinstance(result, dict):
            logger.warning(f"LLM Scoring returned non-dict: {result}")
            result = {}

        logger.debug(f"LLM Scoring Result for '{content[:20]}...': {result}")

        try:
            confidence = float(result.get("confidence", 0.5))
        except (ValueError, TypeError):
            confidence = 0.5

        try:
            importance = float(result.get("importance", 0.5))
        except (ValueError, TypeError):
            importance = 0.5

        justification = result.get("justification", "")
        if not isinstance(justification, str):
            justification = str(justification)

        memory["confidence"] = confidence
        memory["importance"] = importance
        memory["justification"] = justification
        return memory, usage

    def evaluate_event(self, event: Dict[str, Any], metadata: Dict[str, Any] = None) -> Tuple[Optional[Dict[str, Any]], Dict[str, int]]:
        """Combined worthiness + synthesis + scoring in a single LLM call.
        Returns (memory_dict, usage) if worthy, or (None, usage) if not worthy."""
        text = event.get("text", "")
        if not text:
            return None, {"prompt_tokens": 0, "completion_tokens": 0}
        if not isinstance(text, str):
            text = str(text)

        result, usage = self._call_llm(self.prompts["combined_eval"], text)
        if not isinstance(result, dict):
            logger.warning(f"Combined eval returned non-dict: {result}")
            return None, usage

        logger.debug(f"Combined eval result for '{text[:30]}...': {result}")

        if not result.get("worthy", False):
            logger.debug(f"Event deemed NOT worthy (combined): {text[:50]}...")
            return None, usage

        mem_content = result.get("memory", text)
        if not isinstance(mem_content, str):
            mem_content = str(mem_content)

        tags = result.get("tags", [])
        if not isinstance(tags, list):
            tags = []

        try:
            confidence = float(result.get("confidence", 0.5))
        except (ValueError, TypeError):
            confidence = 0.5

        try:
            importance = float(result.get("importance", 0.5))
        except (ValueError, TypeError):
            importance = 0.5

        justification = result.get("justification", "")
        if not isinstance(justification, str):
            justification = str(justification)

        return {
            "type": str(result.get("type", "semantic")),
            "content": mem_content,
            "tags": tags,
            "metadata": metadata or {},
            "confidence": confidence,
            "importance": importance,
            "justification": justification,
        }, usage

    def deduplicate(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        unique_memories = []
        seen_content = set()
        
        for mem in memories:
            content = mem.get("content", "").strip()
            if content not in seen_content:
                seen_content.add(content)
                unique_memories.append(mem)
            else:
                logger.debug(f"Deduplicated (dropped) memory: {content[:50]}...")
        
        return unique_memories
