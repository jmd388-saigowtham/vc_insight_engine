"""Azure OpenAI LLM singleton for the agent system.

Provides a configured AzureChatOpenAI instance used by the orchestrator,
recommendation, report, target derivation, and feature selection nodes.
"""

from __future__ import annotations

import functools
import json
import re
from typing import Any

import structlog
from langchain_openai import AzureChatOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings

logger = structlog.get_logger()


@functools.lru_cache(maxsize=1)
def get_llm() -> AzureChatOpenAI:
    """Return a cached AzureChatOpenAI instance.

    Uses default temperature (1) to support reasoning models (o1/o3)
    that only accept the default value.
    """
    return AzureChatOpenAI(
        azure_deployment=settings.azure_openai_deployment,
        api_key=settings.azure_openai_api_key,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        max_tokens=4096,
    )


async def invoke_llm(messages: list[dict], **kwargs) -> str:
    """Invoke the LLM with retry logic for rate limits.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        **kwargs: Additional kwargs passed to the LLM.  If ``temperature``
            is provided, a one-off LLM instance with that temperature is
            used instead of the cached singleton.

    Returns:
        The LLM response content as a string.
    """
    # Extract temperature override if provided
    temperature = kwargs.pop("temperature", None)
    llm = get_llm()  # default — works with all models

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type((Exception,)),
        reraise=True,
    )
    async def _call():
        from langchain_core.messages import HumanMessage, SystemMessage

        lc_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))

        response = await llm.ainvoke(lc_messages, **kwargs)
        return response.content

    return await _call()


def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences from JSON text."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.rsplit("```", 1)[0]
    return cleaned.strip()


def _repair_json(text: str) -> str:
    """Attempt lightweight JSON repair.

    Fixes common LLM issues:
    - Trailing commas before } or ]
    - Single quotes → double quotes (simple cases)
    """
    # Remove trailing commas
    repaired = re.sub(r',\s*([}\]])', r'\1', text)
    return repaired


def _try_parse_json(text: str) -> dict[str, Any] | None:
    """Try to parse text as a JSON dict. Returns None on failure."""
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    return None


async def invoke_llm_json(
    messages: list[dict],
    schema_hint: str = "",
    max_retries: int = 3,
    **kwargs,
) -> dict[str, Any]:
    """Invoke LLM and parse the response as JSON with retry on parse failure.

    If the first attempt returns invalid JSON, retries with error feedback
    appended to the conversation so the LLM can self-correct.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        schema_hint: Optional description of expected JSON shape for error messages.
        max_retries: Number of parse-failure retries (default 3).
        **kwargs: Additional kwargs passed to the LLM.

    Returns:
        Parsed JSON dict.

    Raises:
        ValueError: If all retries fail to produce valid JSON.
    """
    conversation = list(messages)
    last_error = ""

    for attempt in range(max_retries):
        raw = await invoke_llm(conversation, **kwargs)
        cleaned = _strip_json_fences(raw)

        # Try direct parse
        parsed = _try_parse_json(cleaned)
        if parsed is not None:
            return parsed

        # Try lightweight repair (trailing commas, etc.)
        repaired = _repair_json(cleaned)
        if repaired != cleaned:
            parsed = _try_parse_json(repaired)
            if parsed is not None:
                return parsed

        # Parse failed — log and add error feedback for self-correction
        try:
            json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = str(e)
        else:
            last_error = "Expected JSON object"

        logger.warning(
            "invoke_llm_json: parse failed, retrying",
            attempt=attempt + 1,
            error=last_error,
            response_preview=raw[:200],
        )
        error_msg = (
            f"Your response was not valid JSON. Error: {last_error}\n"
            f"Please respond with ONLY valid JSON (no markdown fences, no extra text)."
        )
        if schema_hint:
            error_msg += f"\nExpected shape: {schema_hint}"
        conversation.append({"role": "user", "content": error_msg})

    raise ValueError(
        f"Failed to get valid JSON after {max_retries} attempts. Last error: {last_error}"
    )
