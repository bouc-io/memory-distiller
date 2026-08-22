"""
Assignment Config Client for memory-distiller (GAP 6 Phase 4).

Fetches the resolved LLM assignment config for the 'memory_distiller' use-case
from admin-api-server. Returns None on any failure so the caller can fall back
to env-var OllamaLLMClient (internal bouc.io Ollama, unchanged pre-GAP-6 behaviour).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import requests

from llm_client import LLMClient, OllamaLLMClient
from llm_client_factory import create_llm_client

logger = logging.getLogger(__name__)

VERIFY_SSL = os.getenv("VERIFY_SSL", "true").lower() == "true"


def fetch_assignment_config(
    use_case: str,
    auth_header: Optional[str],
    admin_api_url: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    GET /v1/config/llm-assignment/{use_case} from admin-api-server.
    Uses the caller's Bearer token so the admin API resolves the correct org assignment.

    Returns the provider config dict, or None if:
    - ADMIN_API_URL is not configured
    - No assignment is found for this org (404)
    - The request fails for any reason (graceful degradation)
    """
    if not admin_api_url:
        logger.debug(f"ADMIN_API_URL not set — skipping assignment config fetch for '{use_case}'")
        return None

    if not auth_header:
        logger.debug(f"No auth_header — skipping assignment config fetch for '{use_case}'")
        return None

    url = f"{admin_api_url.rstrip('/')}/v1/config/llm-assignment/{use_case}"
    headers = {"Authorization": auth_header}

    try:
        response = requests.get(url, headers=headers, timeout=5, verify=VERIFY_SSL)
        if response.status_code == 404:
            logger.debug(f"No LLM assignment found for use-case '{use_case}' — using env-var Ollama fallback")
            return None
        response.raise_for_status()
        raw = response.json()
        # The admin API returns a nested structure:
        #   { model, enable_reasoning, provider: { id, name, provider, api_endpoint, api_key } }
        # Flatten to the shape expected by create_llm_client (provider is a string key).
        provider_info = raw.get("provider")
        if not provider_info:
            logger.debug(f"Assignment has no provider configured for '{use_case}' — using env-var Ollama fallback")
            return None
        config = {
            "provider": provider_info.get("provider"),
            "api_endpoint": provider_info.get("api_endpoint") or "",
            "api_key": provider_info.get("api_key"),
            "model": raw.get("model") or "",
            "enable_reasoning": raw.get("enable_reasoning", False),
        }
        logger.info(f"LLM assignment config fetched: use_case={use_case} provider={config['provider']} model={config['model']}")
        return config
    except Exception as e:
        logger.warning(f"Failed to fetch LLM assignment config for '{use_case}': {e} — using env-var Ollama fallback")
        return None


def create_llm_client_from_config(
    config: Optional[Dict[str, Any]],
    auth_header: Optional[str] = None,
) -> LLMClient:
    """
    Create an LLMClient from the resolved assignment config.
    If config is None (no assignment found or fetch failed), returns an OllamaLLMClient
    that reads from env vars (OLLAMA_BASE_URL + OLLAMA_MODEL) — the internal bouc.io fallback.
    The env-var OllamaLLMClient receives auth_header for cluster OAuth (unchanged behaviour).
    """
    if config is None:
        return OllamaLLMClient(config=None, auth_header=auth_header)
    return create_llm_client(config, auth_header=auth_header)
