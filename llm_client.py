"""
LLM Client abstractions for memory-distiller (GAP 6 Phase 4).

Three concrete implementations:
  OllamaLLMClient      — native /api/chat (internal bouc.io Ollama, existing behaviour)
  OpenAICompatLLMClient— /chat/completions SSE-less (openai, azure, google, custom)
  AnthropicLLMClient   — /v1/messages (x-api-key, system extraction, json prefill)
"""

from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Base interface
# ──────────────────────────────────────────────────────────────────────────────

class LLMClient(ABC):
    """
    Abstract base for all LLM provider clients.
    chat() returns (result, usage):
      - result: parsed JSON dict/list (if json_mode=True) or raw string
      - usage:  {"prompt_tokens": int, "completion_tokens": int}
    """

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        json_mode: bool = False,
        think: bool = False,
    ) -> Tuple[Any, Dict[str, int]]:
        ...


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _robust_json_parse(content: str) -> Any:
    """Strip markdown fences then parse JSON; falls back to brace-search extraction."""
    content = content.strip()
    if content.startswith("```"):
        parts = content.split("```")
        if len(parts) > 1:
            candidate = parts[1].strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            content = candidate
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start_idx = content.find("{")
        end_idx = content.rfind("}")
        if start_idx != -1 and end_idx != -1:
            try:
                return json.loads(content[start_idx : end_idx + 1])
            except json.JSONDecodeError:
                pass
        # Try list
        start_idx = content.find("[")
        end_idx = content.rfind("]")
        if start_idx != -1 and end_idx != -1:
            try:
                return json.loads(content[start_idx : end_idx + 1])
            except json.JSONDecodeError:
                pass
        return content  # last resort: return raw


# ──────────────────────────────────────────────────────────────────────────────
# Ollama (internal bouc.io)
# ──────────────────────────────────────────────────────────────────────────────

class OllamaLLMClient(LLMClient):
    """
    Direct Ollama /api/chat client — identical behaviour to the original call_llm().

    auth_header: full "Bearer <token>" string for cluster OAuth. None = no auth.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, auth_header: Optional[str] = None):
        cfg = config or {}
        self.base_url = cfg.get("api_endpoint") or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = cfg.get("model") or os.getenv("OLLAMA_MODEL", "qwen3.5:2b")
        self.timeout = int(os.getenv("OLLAMA_TIMEOUT", "180"))
        self.temperature = float(os.getenv("TEMPERATURE", "0.1"))
        self.verify_ssl = os.getenv("VERIFY_SSL", "true").lower() == "true"
        self.auth_header = auth_header  # cluster OAuth token passed at construction time

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        json_mode: bool = False,
        think: bool = False,
    ) -> Tuple[Any, Dict[str, int]]:
        url = f"{self.base_url}/api/chat"
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": self.temperature,
            "think": think,
        }
        if json_mode:
            payload["format"] = "json"

        headers: Dict[str, str] = {}
        if self.auth_header:
            headers["Authorization"] = self.auth_header

        logger.debug(f"OllamaLLMClient: POST {url} model={self.model}")
        response = requests.post(url, json=payload, headers=headers, timeout=self.timeout, verify=self.verify_ssl)
        response.raise_for_status()

        data = response.json()
        content = data.get("message", {}).get("content", "")
        usage = {
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
        }

        if json_mode:
            return _robust_json_parse(content), usage
        return content, usage


# ──────────────────────────────────────────────────────────────────────────────
# OpenAI-compatible (openai, azure, google, custom)
# ──────────────────────────────────────────────────────────────────────────────

class OpenAICompatLLMClient(LLMClient):
    """
    POST /chat/completions (non-streaming).
    Covers openai, azure, google (Gemini via OpenAI-compat API), and custom.

    json_mode → response_format: { type: "json_object" }
    think for o-series → reasoning_effort: "high" (detect by model prefix o1/o3)
    """

    def __init__(self, config: Dict[str, Any]):
        self.base_url = config["api_endpoint"].rstrip("/")
        self.model = config["model"]
        self.api_key = config.get("api_key") or ""
        self.provider = config.get("provider", "openai")
        self.timeout = int(os.getenv("OLLAMA_TIMEOUT", "180"))  # reuse timeout env var
        self.verify_ssl = os.getenv("VERIFY_SSL", "true").lower() == "true"

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        json_mode: bool = False,
        think: bool = False,
    ) -> Tuple[Any, Dict[str, int]]:
        url = f"{self.base_url}/chat/completions"

        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.provider == "azure":
            headers["api-key"] = self.api_key
        else:
            headers["Authorization"] = f"Bearer {self.api_key}"

        body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if think and re.match(r"^o[13]", self.model):
            body["reasoning_effort"] = "high"

        logger.debug(f"OpenAICompatLLMClient: POST {url} model={self.model}")
        response = requests.post(url, json=body, headers=headers, timeout=self.timeout, verify=self.verify_ssl)
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"] or ""
        usage_data = data.get("usage", {})
        usage = {
            "prompt_tokens": usage_data.get("prompt_tokens", 0),
            "completion_tokens": usage_data.get("completion_tokens", 0),
        }

        if json_mode:
            return _robust_json_parse(content), usage
        return content, usage


# ──────────────────────────────────────────────────────────────────────────────
# Anthropic
# ──────────────────────────────────────────────────────────────────────────────

class AnthropicLLMClient(LLMClient):
    """
    POST /v1/messages (non-streaming).

    json_mode — Anthropic has no native JSON mode; we prefill the assistant turn
                with "{" to force JSON output, then strip the prefill from the result.
    think     — Enable extended thinking if config.enable_reasoning is True.
    """

    THINKING_BUDGET = 8000

    def __init__(self, config: Dict[str, Any]):
        self.base_url = config["api_endpoint"].rstrip("/")
        self.model = config["model"]
        self.api_key = config.get("api_key") or ""
        self.enable_reasoning = bool(config.get("enable_reasoning", False))
        self.timeout = int(os.getenv("OLLAMA_TIMEOUT", "180"))
        self.verify_ssl = os.getenv("VERIFY_SSL", "true").lower() == "true"

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        json_mode: bool = False,
        think: bool = False,
    ) -> Tuple[Any, Dict[str, int]]:
        # Extract system messages to top-level system field
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        chat_messages = [m for m in messages if m["role"] != "system"]
        system_content = "\n\n".join(system_parts) if system_parts else None

        # JSON mode: prefill assistant turn with "{"
        if json_mode:
            chat_messages = list(chat_messages) + [{"role": "assistant", "content": "{"}]

        body: Dict[str, Any] = {
            "model": self.model,
            "messages": chat_messages,
            "max_tokens": 8096,
            "stream": False,
        }
        if system_content:
            body["system"] = system_content
        if think and self.enable_reasoning:
            body["thinking"] = {"type": "enabled", "budget_tokens": self.THINKING_BUDGET}

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        logger.debug(f"AnthropicLLMClient: POST {self.base_url}/v1/messages model={self.model}")
        response = requests.post(
            f"{self.base_url}/v1/messages",
            json=body,
            headers=headers,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        response.raise_for_status()

        data = response.json()
        # Collect text from text content blocks (skip thinking blocks)
        text_parts = [
            block["text"]
            for block in data.get("content", [])
            if block.get("type") == "text"
        ]
        content = "".join(text_parts)

        # Re-attach the "{" prefill if json_mode
        if json_mode:
            content = "{" + content

        usage_data = data.get("usage", {})
        usage = {
            "prompt_tokens": usage_data.get("input_tokens", 0),
            "completion_tokens": usage_data.get("output_tokens", 0),
        }

        if json_mode:
            return _robust_json_parse(content), usage
        return content, usage
