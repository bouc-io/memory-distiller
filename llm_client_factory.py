"""
LLM Client Factory for memory-distiller (GAP 6 Phase 4).

Routes provider config dict → concrete LLMClient:
  anthropic          → AnthropicLLMClient
  openai/azure/google→ OpenAICompatLLMClient
  custom             → OpenAICompatLLMClient (same protocol, distinct value)
  boucio/ollama      → OllamaLLMClient (with optional cluster auth_header)
  default/None       → OllamaLLMClient from env vars (internal bouc.io fallback)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from llm_client import LLMClient, OllamaLLMClient, OpenAICompatLLMClient, AnthropicLLMClient


def create_llm_client(config: Dict[str, Any], auth_header: Optional[str] = None) -> LLMClient:
    """Create the appropriate LLMClient for a fully-populated provider config dict."""
    provider = config.get("provider", "ollama")

    if provider == "anthropic":
        return AnthropicLLMClient(config)
    elif provider in ("openai", "azure", "google", "custom"):
        return OpenAICompatLLMClient(config)
    else:
        # boucio, ollama, or unknown → native Ollama NDJSON format
        return OllamaLLMClient(config, auth_header=auth_header)
