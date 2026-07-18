import os
import re
import logging
import requests
from requests.exceptions import RequestException, ReadTimeout, ConnectTimeout
from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from fastapi.responses import Response
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

from memory_distiller import MemoryDistiller
from models import DistillRequest, DistillResponse, MemoryObject, Stats, Source
from assignment_config_client import fetch_assignment_config, create_llm_client_from_config
import telemetry

# Load environment variables
load_dotenv()

# Configure OpenTelemetry (OTLP traces + metrics) before the app handles traffic.
# No-op unless OTEL_EXPORTER_OTLP_ENDPOINT is set. See telemetry.py.
telemetry.setup_otlp()

# Configure Logging
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
VERIFY_SSL = os.getenv("VERIFY_SSL", "true").lower() == "true"

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("main")

app = FastAPI(title="Memory Distiller API")
# Auto-instrument FastAPI request handling for traces (no-op unless OTLP enabled).
telemetry.instrument_app(app)

# Initialize Distiller
GLOBAL_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "60"))

# Non-LLM distiller configuration (pipeline behaviour, prompts, thresholds).
# LLM client is resolved per-request from the assignment config endpoint.
DISTILLER_CONFIG = {
    "CONFIDENCE_THRESHOLD": os.getenv("CONFIDENCE_THRESHOLD", "0.5"),
    "PIPELINE_MODE": os.getenv("PIPELINE_MODE", "combined"),
    # Prompt overrides — None means use built-in defaults from prompts.py
    "PROMPT_SEGMENTATION": os.getenv("PROMPT_SEGMENTATION"),
    "PROMPT_WORTHINESS": os.getenv("PROMPT_WORTHINESS"),
    "PROMPT_SYNTHESIS": os.getenv("PROMPT_SYNTHESIS"),
    "PROMPT_SCORING": os.getenv("PROMPT_SCORING"),
    "PROMPT_COMBINED_EVAL": os.getenv("PROMPT_COMBINED_EVAL"),
    "SYSTEM_PREAMBLE": os.getenv("SYSTEM_PREAMBLE"),
}

# Admin API URL for LLM assignment config resolution (GAP 6)
ADMIN_API_URL = os.getenv("ADMIN_API_URL")

prompt_overrides = [k for k in ["PROMPT_SEGMENTATION", "PROMPT_WORTHINESS", "PROMPT_SYNTHESIS",
                                 "PROMPT_SCORING", "PROMPT_COMBINED_EVAL", "SYSTEM_PREAMBLE"]
                    if DISTILLER_CONFIG.get(k)]
if prompt_overrides:
    logger.info(f"Using env var overrides for: {', '.join(prompt_overrides)}")
else:
    logger.info("Using all built-in default prompts from prompts.py")

MEMORY_API_URL = os.getenv("MEMORY_API_URL")
CHATBOT_API_URL = os.getenv("CHATBOT_API_URL")
AGENT_API_URL = os.getenv("AGENT_API_URL")

# Memory processing mode:
#   off                — skip everything; no memories written
#   distiller          — LLM distillation only (default, existing behaviour)
#   neuralese          — raw segment embedding only; no LLM distillation call
#   neuralese-distiller — both paths run in sequence
MEMORY_MODE = os.getenv("MEMORY_MODE", "distiller")

def map_importance(score: float) -> str:
    """Maps 0.0-1.0 score to critical|high|medium|low"""
    if score >= 0.9: return "critical"
    if score >= 0.7: return "high"
    if score >= 0.4: return "medium"
    return "low"

def map_category(mem_type: str) -> str:
    """Maps distiller type to Memory API category"""
    # Distiller types: semantic, episodic, procedural, personal, preference
    # Memory API categories: persona, preference, fact, context, instruction
    mapping = {
        "semantic": "fact",
        "episodic": "context",
        "procedural": "instruction",
        "personal": "persona",
        "preference": "preference"
    }
    return mapping.get(mem_type, "fact") # Default to fact

def fetch_transcript(source_type: str, source_id: str, auth_token: Optional[str] = None) -> str:
    try:
        url = ""
        if source_type == "chat":
            if not CHATBOT_API_URL: raise ValueError("CHATBOT_API_URL is not configured.")
            url = f"{CHATBOT_API_URL}/v1/chats/{source_id}/messages"
        elif source_type == "agent":
             if not AGENT_API_URL: raise ValueError("AGENT_API_URL is not configured.")
             url = f"{AGENT_API_URL}/v1/assignments/{source_id}/messages"
        else:
            raise ValueError(f"Unknown source type: {source_type}")

        logger.info(f"Fetching transcript from {url}")
        
        headers = {}
        if auth_token:
            headers["Authorization"] = auth_token

        response = requests.get(url, params={"limit": 100}, headers=headers, timeout=GLOBAL_TIMEOUT, verify=VERIFY_SSL) # limit 100 as reasonable default
        response.raise_for_status()
        data = response.json()
        
        messages = data.get("data", [])
        # Sort by creation time if not sorted
        # messages.sort(key=lambda x: x['created_at']) 
        
        transcript_lines = []
        for msg in messages:
            role = msg.get("role", "unknown").capitalize()
            content = msg.get("content") or ""
            tool_calls = msg.get("tool_calls") or []

            if content:
                transcript_lines.append(f"{role}: {content}")
            for tc in tool_calls:
                fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                name = fn.get("name", "")
                args = fn.get("arguments", "")
                if name:
                    transcript_lines.append(f"{role} [tool_call]: {name}({args})")

        return "\n".join(transcript_lines)

    except ReadTimeout:
        logger.error("Source API request timed out")
        raise HTTPException(status_code=504, detail={
            "error_code": "SOURCE_TIMEOUT",
            "message": "Timed out fetching transcript from source API."
        })
    except ConnectTimeout:
        logger.error("Source API connection timed out")
        raise HTTPException(status_code=504, detail={
            "error_code": "SOURCE_TIMEOUT",
            "message": "Timed out connecting to source API."
        })
    except RequestException as e:
        logger.error(f"Source API request failed: {e}")
        raise HTTPException(status_code=502, detail={
            "error_code": "SOURCE_ERROR",
            "message": f"Failed to fetch transcript from source API: {str(e)}"
        })
    except Exception as e:
        logger.error(f"Failed to fetch transcript: {e}")
        raise HTTPException(status_code=500, detail={
            "error_code": "INTERNAL_ERROR",
            "message": f"Unexpected error fetching transcript: {str(e)}"
        })

def post_memories_to_api(memories: List[MemoryObject], source_metadata: Dict[str, Any], distillation_model: str, auth_token: Optional[str] = None):
    """Synchronous — uses requests library. Safe to call from a sync background task."""
    if not MEMORY_API_URL:
        logger.info("No MEMORY_API_URL configured. Skipping post to API.")
        return

    target_url = f"{MEMORY_API_URL}/v1/memories"

    headers = {}
    if auth_token:
        headers["Authorization"] = auth_token

    for mem in memories:
        payload = {
            "content": mem.content,
            "category": map_category(mem.type),
            "importance": map_importance(mem.importance),
            "tags": mem.tags,
            "source": "inferred",
            "distillation_model": distillation_model,
            "metadata": {
                "source_type": "inferred",
                "distilled_from_source": True,
                "confidence": mem.confidence,
                "justification": mem.justification,
                **source_metadata
            }
        }

        try:
            logger.debug(f"Posting memory to {target_url}: {payload}")
            response = requests.post(target_url, json=payload, headers=headers, timeout=GLOBAL_TIMEOUT, verify=VERIFY_SSL)
            response.raise_for_status()
            logger.info(f"Successfully posted memory to API.")
            telemetry.record_memories_stored(map_category(mem.type))
        except Exception as e:
            logger.error(f"Failed to post memory to API: {e}")


def segment_transcript(transcript: str, chunk_size: int = 600) -> List[str]:
    """
    Split a raw transcript into ~150-token semantic chunks (approx 600 chars)
    by sentence boundaries. Used by the neuralese path.
    Filters out chunks shorter than 50 chars (too small to embed meaningfully).
    """
    sentences = re.split(r'(?<=[.!?])\s+', transcript.strip())
    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= chunk_size:
            current = (current + " " + sentence).strip() if current else sentence
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return [c for c in chunks if len(c) >= 50]


def post_neuralese_chunks_to_api(
    chunks: List[str],
    source_metadata: Dict[str, Any],
    auth_token: Optional[str] = None
):
    """
    Posts raw transcript segments (neuralese memories) to the Memory API.
    The memory-api-server generates embeddings from the raw text, storing them
    as memory_type='neuralese' with session_shared=True so they are available
    across sessions for the same user/org.
    """
    if not MEMORY_API_URL:
        logger.info("No MEMORY_API_URL configured. Skipping neuralese chunk upload.")
        return

    target_url = f"{MEMORY_API_URL}/v1/memories"
    headers = {}
    if auth_token:
        headers["Authorization"] = auth_token

    for chunk in chunks:
        payload = {
            "content": chunk,
            "category": "context",
            "importance": "low",
            "tags": ["neuralese", "raw-segment"],
            "source": "inferred",
            "memory_type": "neuralese",
            "session_shared": True,
            "metadata": {
                "neuralese": True,
                "raw_segment": True,
                **source_metadata
            }
        }
        try:
            response = requests.post(
                target_url, json=payload, headers=headers,
                timeout=GLOBAL_TIMEOUT, verify=VERIFY_SSL
            )
            response.raise_for_status()
            logger.info("Successfully posted neuralese chunk to API.")
        except Exception as e:
            logger.error(f"Failed to post neuralese chunk to API: {e}")


def run_distillation_task(request: DistillRequest, authorization: Optional[str]):
    """
    Synchronous background task. Branches on MEMORY_MODE:
      off                — return immediately, no memories written
      distiller          — LLM distillation pipeline only (existing behaviour)
      neuralese          — raw segment embedding only (no LLM distillation call)
      neuralese-distiller — both paths run in sequence

    FastAPI executes sync background tasks in a threadpool, so this never
    blocks the event loop regardless of LLM call duration.
    """
    try:
        # ── Short-circuit for "off" mode ──────────────────────────────────────
        if MEMORY_MODE == "off":
            logger.info(f"MEMORY_MODE=off — skipping distillation for source {request.source.id}")
            return

        # ── Fetch / validate context ──────────────────────────────────────────
        context_text = ""
        if request.context and request.context.text:
            context_text = request.context.text
        else:
            logger.info("Context text missing, fetching from source...")
            context_text = fetch_transcript(request.source.type, request.source.id, authorization)
            logger.info(f"Fetched {len(context_text)} chars of context.")

            # Skip if only the user's initial request was fetched (no agent response present)
            non_user_lines = [l for l in context_text.splitlines() if not l.startswith("User:")]
            if not non_user_lines:
                logger.warning(f"Context for {request.source.id} has no agent response — skipping distillation.")
                return

        if not context_text:
            logger.error(f"No context available for distillation of source {request.source.id}")
            return

        # ── Distiller path ────────────────────────────────────────────────────
        if MEMORY_MODE in ("distiller", "neuralese-distiller"):
            # Resolve LLM provider from admin assignment config (org → global override chain).
            # Falls back to env-var OllamaLLMClient (internal bouc.io Ollama) on any failure.
            llm_config = fetch_assignment_config("memory_distiller", authorization, ADMIN_API_URL)
            llm_client = create_llm_client_from_config(llm_config, auth_header=authorization)
            logger.info(f"LLM client resolved: provider={getattr(llm_client, 'provider', type(llm_client).__name__)}")

            distiller = MemoryDistiller(llm_client, DISTILLER_CONFIG)
            raw_memories, raw_stats = distiller.distill(context_text, request.metadata)

            memories = [
                MemoryObject(
                    type=m.get("type", "semantic"),
                    content=m.get("content", ""),
                    confidence=m.get("confidence", 0.0),
                    importance=m.get("importance", 0.0),
                    tags=m.get("tags", []),
                    justification=m.get("justification")
                ) for m in raw_memories
            ]

            if request.options and request.options.max_memories:
                memories = memories[:request.options.max_memories]

            logger.info(
                f"Distillation complete for source {request.source.id}: "
                f"{len(memories)} memories emitted, {raw_stats.get('llm_calls', 0)} LLM calls"
            )

            model_name = llm_config.get("model") if llm_config else os.getenv("OLLAMA_MODEL", "qwen3.5:2b")
            post_memories_to_api(memories, request.metadata, model_name, authorization)

        # ── Neuralese path (new) ──────────────────────────────────────────────
        if MEMORY_MODE in ("neuralese", "neuralese-distiller"):
            chunks = segment_transcript(context_text)
            logger.info(
                f"Neuralese segmentation for source {request.source.id}: "
                f"{len(chunks)} chunks from {len(context_text)} chars"
            )
            post_neuralese_chunks_to_api(chunks, request.metadata, authorization)

        telemetry.record_request("completed")

    except Exception:
        logger.exception(f"Background distillation failed for source {request.source.id}")
        telemetry.record_request("failed")

@app.on_event("startup")
async def startup_event():
    logger.info("Starting Memory Distiller Service V1.5")
    logger.info(f"Debug Mode: {DEBUG}")
    logger.info(f"Memory Mode: {MEMORY_MODE}")
    logger.info(f"Pipeline Mode: {DISTILLER_CONFIG['PIPELINE_MODE']}")
    logger.info(f"Admin API URL: {ADMIN_API_URL or '(not set — using env-var Ollama fallback)'}")
    logger.info(f"Memory API URL: {MEMORY_API_URL}")
    logger.info(f"Chatbot API URL: {CHATBOT_API_URL}")
    logger.info(f"Agent API URL: {AGENT_API_URL}")

@app.post("/v1/distill", status_code=202)
async def distill_endpoint(
    request: DistillRequest,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None)
):
    """
    Accepts a distillation request and returns 202 immediately.
    All LLM processing runs in the background via run_distillation_task,
    which FastAPI executes in a threadpool so it never blocks the event loop.
    """
    logger.info(f"Accepted distillation request for source {request.source.id}")
    telemetry.record_request("accepted")
    background_tasks.add_task(run_distillation_task, request, authorization)
    return {"status": "accepted", "source_id": str(request.source.id)}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/metrics")
def metrics():
    """Prometheus scrape endpoint (direct-scrape path; see telemetry.py)."""
    body, content_type = telemetry.metrics_response()
    return Response(content=body, media_type=content_type)
